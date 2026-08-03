#!/usr/bin/env python3
"""Step 2_1: Merge cleaned LRT polygons and the 100 m INSPIRE grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm

from common import atomic_write_csv, atomic_write_json


_WORKER_GRID: gpd.GeoDataFrame | None = None
_WORKER_LRT: gpd.GeoDataFrame | None = None
_WORKER_GRID_ID: str | None = None
_WORKER_SINDEX: Any = None
SUSI_MATRIX_SCHEMA_VERSION = "2026-08-03-centi-percent-abck-coastal-v3"


def atomic_write_parquet(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.part{path.suffix}")
    temporary.unlink(missing_ok=True)
    frame.to_parquet(
        temporary,
        index=False,
        compression="zstd",
    )
    temporary.replace(path)


def atomic_write_gpkg(
    frame: gpd.GeoDataFrame,
    path: Path,
    *,
    layer: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.part{path.suffix}")
    temporary.unlink(missing_ok=True)
    frame.to_file(
        temporary,
        layer=layer,
        driver="GPKG",
        engine="pyogrio",
    )
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError(f"Temporary GeoPackage is empty: {temporary}")
    temporary.replace(path)


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    section = config.get("lrt_grid_merge")
    if not isinstance(section, dict):
        raise KeyError("Missing 'lrt_grid_merge' section in config.json.")

    required = ["grid_gpkg", "lrt_gpkg", "output_csv"]
    missing = [key for key in required if not section.get(key)]
    if missing:
        raise KeyError(
            "Missing required lrt_grid_merge key(s): "
            + ", ".join(missing)
        )

    return config


def file_fingerprint(path: Path, hash_bytes: int = 1024 * 1024) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    stat = path.stat()
    digest = hashlib.sha256()

    with path.open("rb") as file:
        digest.update(file.read(hash_bytes))
        if stat.st_size > hash_bytes:
            file.seek(max(0, stat.st_size - hash_bytes))
            digest.update(file.read(hash_bytes))

    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "edge_sha256": digest.hexdigest(),
    }


def normalise_state(state: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(state)
    cleaned.pop("result", None)
    return cleaned


def should_skip(
    output_paths: list[Path],
    state_file: Path,
    expected_state: dict[str, Any],
    force: bool,
) -> bool:
    if force:
        return False
    if not all(path.is_file() for path in output_paths):
        return False
    if not state_file.is_file():
        return False

    try:
        with state_file.open("r", encoding="utf-8") as file:
            previous = json.load(file)
    except (OSError, json.JSONDecodeError):
        return False

    return normalise_state(previous) == expected_state


def read_inputs(
    grid_gpkg: Path,
    grid_layer: str,
    lrt_gpkg: Path,
    lrt_layer: str,
    grid_id_column: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    grid = gpd.read_file(
        grid_gpkg,
        layer=grid_layer,
        engine="pyogrio",
    )
    lrt = gpd.read_file(
        lrt_gpkg,
        layer=lrt_layer,
        engine="pyogrio",
    )

    if grid_id_column not in grid.columns:
        raise ValueError(
            f"Grid ID column '{grid_id_column}' not found. "
            f"Available columns: {list(grid.columns)}"
        )

    required_lrt = {
        "Formation",
        "conservation_status",
        "mapping_year",
        "LRT_code",
        "src_id",
        "geometry",
    }
    missing = required_lrt - set(lrt.columns)
    if missing:
        raise ValueError(
            "Missing required LRT columns: "
            + ", ".join(sorted(missing))
        )

    if grid.crs is None or lrt.crs is None:
        raise ValueError("Grid and LRT data must both have a CRS.")

    if grid.crs != lrt.crs:
        lrt = lrt.to_crs(grid.crs)

    grid = grid[[grid_id_column, "geometry"]].copy()
    lrt = lrt[
        [
            "src_id",
            "Formation",
            "conservation_status",
            "LRT_code",
            "mapping_year",
            "geometry",
        ]
    ].copy()

    lrt["mapping_year"] = pd.to_numeric(
        lrt["mapping_year"],
        errors="coerce",
    ).astype("Int64")

    return grid, lrt


def _intersect_chunk(bounds: tuple[int, int]) -> pd.DataFrame | None:
    global _WORKER_SINDEX

    if _WORKER_GRID is None or _WORKER_LRT is None or _WORKER_GRID_ID is None:
        raise RuntimeError("Step 2_1 worker was not initialised.")

    start, end = bounds
    grid_chunk = _WORKER_GRID.iloc[start:end].copy()
    if grid_chunk.empty:
        return None

    if _WORKER_SINDEX is None:
        _WORKER_SINDEX = _WORKER_LRT.sindex

    minx, miny, maxx, maxy = grid_chunk.total_bounds
    candidate_positions = list(
        _WORKER_SINDEX.intersection((minx, miny, maxx, maxy))
    )
    if not candidate_positions:
        return None

    lrt_candidates = _WORKER_LRT.iloc[candidate_positions].copy()
    intersection = gpd.overlay(
        grid_chunk,
        lrt_candidates,
        how="intersection",
        keep_geom_type=False,
    )
    if intersection.empty:
        return None

    intersection["intersection_area_m2"] = intersection.geometry.area
    intersection = intersection[
        intersection["intersection_area_m2"] > 0
    ].copy()
    if intersection.empty:
        return None

    return pd.DataFrame(
        intersection[
            [
                _WORKER_GRID_ID,
                "src_id",
                "Formation",
                "conservation_status",
                "LRT_code",
                "mapping_year",
                "intersection_area_m2",
            ]
        ]
    )


def _intersect_chunk_with_bounds(
    bounds: tuple[int, int],
) -> tuple[tuple[int, int], pd.DataFrame | None]:
    return bounds, _intersect_chunk(bounds)


def checkpoint_path(checkpoint_dir: Path, start: int, end: int) -> Path:
    return checkpoint_dir / f"chunk_{start:012d}_{end:012d}.pkl"


def read_checkpoint(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_pickle(path)
    except Exception:
        return None


def write_checkpoint(path: Path, frame: pd.DataFrame | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = pd.DataFrame() if frame is None else frame
    payload.to_pickle(temporary)
    temporary.replace(path)


def add_top3_metrics(
    ranked: pd.DataFrame,
    grid_id_column: str,
    label_column: str,
    value_column: str,
    rank_column: str,
    prefix: str,
) -> pd.DataFrame:
    top3 = ranked[ranked[rank_column] <= 3][
        [grid_id_column, rank_column, label_column, value_column]
    ].copy()

    label_wide = top3.pivot(
        index=grid_id_column,
        columns=rank_column,
        values=label_column,
    )
    value_wide = top3.pivot(
        index=grid_id_column,
        columns=rank_column,
        values=value_column,
    )

    result = pd.DataFrame(index=value_wide.index.union(label_wide.index))
    for rank in (1, 2, 3):
        result[f"{prefix}_top{rank}_label"] = label_wide.get(rank, pd.NA)
        result[f"{prefix}_top{rank}_pct"] = value_wide.get(rank, 0.0)

    pct_cols = [f"{prefix}_top{rank}_pct" for rank in (1, 2, 3)]
    result[pct_cols] = result[pct_cols].fillna(0.0)
    result[f"{prefix}_top3_sum_pct"] = result[pct_cols].sum(axis=1)

    denominator = result[f"{prefix}_top3_sum_pct"].replace(0, np.nan)
    for rank in (1, 2, 3):
        result[f"{prefix}_top{rank}_share_of_top3"] = (
            result[f"{prefix}_top{rank}_pct"] / denominator
        )

    top2 = result[f"{prefix}_top2_pct"].replace(0, np.nan)
    top3_pct = result[f"{prefix}_top3_pct"].replace(0, np.nan)
    result[f"{prefix}_top1_to_top2_ratio"] = (
        result[f"{prefix}_top1_pct"] / top2
    )
    result[f"{prefix}_top1_to_top3_ratio"] = (
        result[f"{prefix}_top1_pct"] / top3_pct
    )

    return result.reset_index().rename(columns={"index": grid_id_column})


def intersect_in_chunks(
    grid: gpd.GeoDataFrame,
    lrt: gpd.GeoDataFrame,
    grid_id_column: str,
    chunk_size: int,
    processes: int,
    maxtasksperchild: int | None,
    checkpoint_dir: Path | None = None,
) -> pd.DataFrame:
    global _WORKER_GRID, _WORKER_LRT, _WORKER_GRID_ID, _WORKER_SINDEX

    bounds = [
        (start, min(start + chunk_size, len(grid)))
        for start in range(0, len(grid), chunk_size)
    ]
    parts: list[pd.DataFrame] = []
    pending_bounds: list[tuple[int, int]] = []

    if checkpoint_dir is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        for start, end in bounds:
            saved = read_checkpoint(checkpoint_path(checkpoint_dir, start, end))
            if saved is None:
                pending_bounds.append((start, end))
            elif not saved.empty:
                parts.append(saved)
        print(
            "Chunk checkpoints loaded: "
            f"{len(bounds) - len(pending_bounds):,}/{len(bounds):,}; "
            f"pending: {len(pending_bounds):,}"
        )
    else:
        pending_bounds = bounds

    _WORKER_GRID = grid
    _WORKER_LRT = lrt
    _WORKER_GRID_ID = grid_id_column
    _WORKER_SINDEX = None

    use_parallel = processes > 1 and "fork" in mp.get_all_start_methods()
    started = time.monotonic()
    completed_new = 0

    if use_parallel:
        context = mp.get_context("fork")
        with context.Pool(
            processes=processes,
            maxtasksperchild=maxtasksperchild,
        ) as pool:
            iterator = pool.imap_unordered(
                _intersect_chunk_with_bounds,
                pending_bounds,
                chunksize=1,
            )
            for item_bounds, part in tqdm(
                iterator,
                total=len(pending_bounds),
                desc=f"Intersecting grid chunks ({processes} processes)",
            ):
                completed_new += 1
                if checkpoint_dir is not None:
                    start, end = item_bounds
                    write_checkpoint(checkpoint_path(checkpoint_dir, start, end), part)
                if part is not None:
                    parts.append(part)
                elapsed = time.monotonic() - started
                if completed_new and completed_new % max(1, processes) == 0:
                    rate = completed_new / elapsed if elapsed > 0 else 0.0
                    remaining = (
                        (len(pending_bounds) - completed_new) / rate
                        if rate > 0
                        else 0.0
                    )
                    print(
                        "Chunk ETA: "
                        f"{remaining / 60:.1f} min remaining "
                        f"({completed_new:,}/{len(pending_bounds):,} new)"
                    )
    else:
        for item in tqdm(
            pending_bounds,
            total=len(pending_bounds),
            desc="Intersecting grid chunks",
        ):
            part = _intersect_chunk(item)
            completed_new += 1
            if checkpoint_dir is not None:
                write_checkpoint(checkpoint_path(checkpoint_dir, item[0], item[1]), part)
            if part is not None:
                parts.append(part)
            elapsed = time.monotonic() - started
            rate = completed_new / elapsed if elapsed > 0 else 0.0
            remaining = (
                (len(pending_bounds) - completed_new) / rate
                if rate > 0
                else 0.0
            )
            print(
                "Chunk ETA: "
                f"{remaining / 60:.1f} min remaining "
                f"({completed_new:,}/{len(pending_bounds):,} new)"
            )

    _WORKER_GRID = None
    _WORKER_LRT = None
    _WORKER_GRID_ID = None
    _WORKER_SINDEX = None

    if not parts:
        raise RuntimeError("No intersections found between grid and LRT.")

    return pd.concat(parts, ignore_index=True)



def build_summary(
    intersections: pd.DataFrame,
    grid_id_column: str,
    cell_area_m2: float,
    disputed_threshold_pct: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    formation_area = (
        intersections.groupby(
            [grid_id_column, "Formation"],
            dropna=False,
            as_index=False,
        )["intersection_area_m2"]
        .sum()
    )

    formation_area["coverage_pct"] = (
        formation_area["intersection_area_m2"] / cell_area_m2 * 100
    )

    formation_counts = (
        formation_area.groupby(grid_id_column)["Formation"]
        .nunique(dropna=True)
        .rename("formation_count")
        .reset_index()
    )
    formation_counts["multiple_formations_in_cell"] = (
        formation_counts["formation_count"] > 1
    )

    ranked = formation_area.sort_values(
        [grid_id_column, "intersection_area_m2", "Formation"],
        ascending=[True, False, True],
    ).copy()
    ranked["formation_rank"] = (
        ranked.groupby(grid_id_column).cumcount() + 1
    )
    formation_top3 = add_top3_metrics(
        ranked=ranked,
        grid_id_column=grid_id_column,
        label_column="Formation",
        value_column="coverage_pct",
        rank_column="formation_rank",
        prefix="majority_formation",
    )

    top = ranked[ranked["formation_rank"] == 1].copy()
    second = ranked[ranked["formation_rank"] == 2][
        [grid_id_column, "coverage_pct"]
    ].rename(columns={"coverage_pct": "second_coverage_pct"})

    majority = top.merge(second, on=grid_id_column, how="left")
    majority["second_coverage_pct"] = (
        majority["second_coverage_pct"].fillna(0.0)
    )
    majority["majority_gap_pct"] = (
        majority["coverage_pct"] - majority["second_coverage_pct"]
    )
    majority["majority_disputed"] = (
        majority["majority_gap_pct"] <= disputed_threshold_pct
    )

    majority = majority.rename(
        columns={
            "Formation": "majority_formation",
            "covÛÞ·¶‰žËkºwµçAMÕÍ¤µ½µÁ…Ñ¥‰±”€ÄÀÀ´µ…ÑÉ¥àÁÉ½‘ÕÑÌ¥¹Ñ¼ÁÉ½•ÍÍ•½ÕÑÁÕÐ¸((€€€MÕÍ¤Ì¹½Ñ•‰½½¬ÍÑ½É•Ì•±°½Ù•É…”¥¸•¹Ñ¤µÁ•É•¹Ð¥¹Ñ••ÈÕ¹¥ÑÌè(€€€„™Õ±±ä½Ù•É•€ÄÀÀ´•±°¥ÌÉ•ÁÉ•Í•¹Ñ•…Ì€ÄÀÀÀÀ¸(€€€€ˆˆˆ(€€€½ÕÑÁÕÑ}‘¥È¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤((€€€¥à€ô¥¹Ñ•ÉÍ•Ñ¥½¹Ì¹½Áä ¤(€€€¥ál‰ÁÑ}½™}•±°‰t€ô€ (€€€€€€€¥ál‰¥¹Ñ•ÉÍ•Ñ¥½¹}…É•…}´È‰t€¼•±±}…É•…}´È€¨€ÄÀÀ¸À(€€€€¤(€€€¥à€ô¥à¹É•¹…µ”¡½±Õµ¹ÌõíÉ¥‘}¥‘}½±Õµ¸è€‰É¥‘}¥‰ô¤((€€€¥˜ÝÉ¥Ñ•}¥¹Ñ•ÉÍ•Ñ¥½¹Í}ÍØè(€€€€€€€…Ñ½µ¥}ÝÉ¥Ñ•}ÍØ¡¥à°½ÕÑÁÕÑ}‘¥È€¼€‰¥à¹ÍØˆ¤((€€€á}±ÉÐ€ô€ (€€€€€€€¥à¹É½ÕÁ‰ä¡l‰É¥‘}¥ˆ°€‰1IQ}½‘”ˆ°€‰½¹Í•ÉÙ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t¥l(€€€€€€€€€€€€‰ÁÑ}½™}•±°ˆ(€€€€€€€t(€€€€€€€€¹ÍÕ´ ¤(€€€€€€€€¹Õ¹ÍÑ…¬¡l‰1IQ}½‘”ˆ°€‰½¹Í•ÉÙ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t¤(€€€€€€€€¹™¥±±¹„ À¤(€€€€¤(€€€á}±ÉÐ¹½±Õµ¹Ì€ôm˜‰í½‘•õ}íÍÑ…ÑÕÍôˆ™½È½‘”°ÍÑ…ÑÕÌ¥¸á}±ÉÐ¹½±Õµ¹Ít(€€€á}±ÉÐ€ô€¡á}±ÉÐ€¨€ÄÀÀ¤¹É½Õ¹ ¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤((€€€±ÉÑ}ÍÑ…ÑÕÍ}½±Ì€ô±¥ÍÐ¡á}±ÉÐ¹½±Õµ¹Ì¤(€€€±ÉÑ}½‘•Ì€ôÍ½ÉÑ•¡í½±Õµ¸¹ÉÍÁ±¥Ð ‰|ˆ°€Ä¥lÁt™½È½±Õµ¸¥¸±ÉÑ}ÍÑ…ÑÕÍ}½±Íô¤(€€€¥˜±ÉÑ}½‘•Ìè(€€€€€€€±ÉÑ}ÁÉ•Í•¹”€ôÁ¹…Ñ…É…µ” (€€€€€€€€€€€ì(€€€€€€€€€€€€€€€½‘”èá}±ÉÑl(€€€€€€€€€€€€€€€€€€€l(€€€€€€€€€€€€€€€€€€€€€€€½±Õµ¸(€€€€€€€€€€€€€€€€€€€€€€€™½È½±Õµ¸¥¸±ÉÑ}ÍÑ…ÑÕÍ}½±Ì(€€€€€€€€€€€€€€€€€€€€€€€¥˜½±Õµ¸¹ÉÍÁ±¥Ð ‰|ˆ°€Ä¥lÁt€ôô½‘”(€€€€€€€€€€€€€€€€€€€t(€€€€€€€€€€€€€€€t(€€€€€€€€€€€€€€€€¹Ð À¤(€€€€€€€€€€€€€€€€¹…¹ä¡…á¥ÌôÄ¤(€€€€€€€€€€€€€€€™½È½‘”¥¸±ÉÑ}½‘•Ì(€€€€€€€€€€€ô°(€€€€€€€€€€€¥¹‘•àõá}±ÉÐ¹¥¹‘•à°(€€€€€€€€¤(€€€€€€€á}±ÉÑl‰¹}±ÉÑÌ‰t€ô±ÉÑ}ÁÉ•Í•¹”¹ÍÕ´¡…á¥ÌôÄ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€€€€‘•°±ÉÑ}ÁÉ•Í•¹”(€€€•±Í”è(€€€€€€€á}±ÉÑl‰¹}±ÉÑÌ‰t€ô¹À¹Õ¥¹ÐÄØ À¤((€€€á}™Ì€ô€ (€€€€€€€¥à¹É½ÕÁ‰ä¡l‰É¥‘}¥ˆ°€‰½Éµ…Ñ¥½¸ˆ°€‰½¹Í•ÉÙ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t¥l(€€€€€€€€€€€€‰ÁÑ}½™}•±°ˆ(€€€€€€€t(€€€€€€€€¹ÍÕ´ ¤(€€€€€€€€¹Õ¹ÍÑ…¬¡l‰½Éµ…Ñ¥½¸ˆ°€‰½¹Í•ÉÙ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t¤(€€€€€€€€¹™¥±±¹„ À¤(€€€€¤(€€€á}™Ì¹½±Õµ¹Ì€ôl(€€€€€€€˜‰í™½Éµ…Ñ¥½¹õ}íÍÑ…ÑÕÍôˆ™½È™½Éµ…Ñ¥½¸°ÍÑ…ÑÕÌ¥¸á}™Ì¹½±Õµ¹Ì(€€€t(€€€á}™Ì€ô€¡á}™Ì€¨€ÄÀÀ¤¹É½Õ¹ ¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤((€€€™½Éµ…Ñ¥½¹Ì€ôÍ½ÉÑ•¡í½±Õµ¸¹ÉÍÁ±¥Ð ‰|ˆ°€Ä¥lÁt™½È½±Õµ¸¥¸á}™Ì¹½±Õµ¹Íô¤(€€€™½È™½Éµ…Ñ¥½¸¥¸™½Éµ…Ñ¥½¹Ìè(€€€€€€€½±Õµ¹Ì€ôl(€€€€€€€€€€€½±Õµ¸(€€€€€€€€€€€™½È½±Õµ¸¥¸á}™Ì¹½±Õµ¹Ì(€€€€€€€€€€€¥˜½±Õµ¸¹ÍÑ…ÉÑÍÝ¥Ñ ¡˜‰í™½Éµ…Ñ¥½¹õ|ˆ¤(€€€€€€€t(€€€€€€€á}™Ím™½Éµ…Ñ¥½¹t€ô€ (€€€€€€€€€€€á}™Ím½±Õµ¹Ít¹ÍÕ´¡…á¥ÌôÄ¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€€€€€¤((€€€€Œ-••À½½½,Í¡…É•Ì™½È™½Éµ…Ñ¥½¹Ì¸½Éµ…Ñ¥½¸Ñ½Ñ…±ÌÑ¡•É•™½É”¥¹±Õ‘”,°(€€€€ŒÝ¡¥±”Ñ¡”µ…©½É¥ÑäÍÑ…ÑÕÌ‰•±½Ü‘•±¥‰•É…Ñ•±ä½¹Í¥‘•ÉÌ½½½¹±ä¸(€€€á}™Ì€ôá}™ÍmÍ½ÉÑ•¡á}™Ì¹½±Õµ¹Ì¥t(€€€¥˜€‰A•Éµ…¹•¹Ð±…¥•ÉÍ}ˆ¹½Ð¥¸á}™Ì¹½±Õµ¹Ìè(€€€€€€€á}™Íl‰A•Éµ…¹•¹Ð±…¥•ÉÍ}‰t€ô¹À¹Õ¥¹ÐÄØ À¤((€€€™½Éµ…Ñ¥½¹}½±Ì€ôl(€€€€€€€½±Õµ¸(€€€€€€€™½È½±Õµ¸¥¸á}™Ì¹½±Õµ¹Ì(€€€€€€€¥˜€‰|ˆ¹½Ð¥¸½±Õµ¸(€€€€€€€…¹½±Õµ¸(€€€€€€€¹½Ð¥¸l‰5…©½É¥Ñå}™½Éµ…Ñ¥½¸ˆ°€‰µ…©½É¥Ñå}™½Éµ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t(€€€t(€€€¹½¹é•É½}™½Éµ…Ñ¥½¸€ôá}™Ím™½Éµ…Ñ¥½¹}½±Ít¹Ð À¤¹…¹ä¡…á¥ÌôÄ¤(€€€á}™Ì€ôá}™Ì¹±½m¹½¹é•É½}™½Éµ…Ñ¥½¹t¹½Áä ¤(€€€á}±ÉÐ€ôá}±ÉÐ¹±½má}±ÉÐ¹¥¹‘•à¹¥¹Ñ•ÉÍ•Ñ¥½¸¡á}™Ì¹¥¹‘•à¥t¹½Áä ¤((€€€á}™Íl‰¹}™½Éµ…Ñ¥½¹Ì‰t€ô€ (€€€€€€€á}™Ím™½Éµ…Ñ¥½¹}½±Ít¹Ð À¤¹ÍÕ´¡…á¥ÌôÄ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€¤(€€€á}™Íl‰5…©½É¥Ñå}™½Éµ…Ñ¥½¸‰t€ôá}™Ím™½Éµ…Ñ¥½¹}½±Ít¹¥‘áµ…à¡…á¥ÌôÄ¤((€€€Ù…±Õ•Ì€ôá}™Ím™½Éµ…Ñ¥½¹}½±Ít¹Ñ½}¹ÕµÁä¡‘ÑåÁ”õ¹À¹™±½…ÐØÐ¤(€€€¥˜Ù…±Õ•Ì¹Í¡…Á•lÅt€øô€Èè(€€€€€€€Ñ½ÀÈ€ô¹À¹Á…ÉÑ¥Ñ¥½¸¡Ù…±Õ•Ì°€´È°…á¥ÌôÄ¥lè°€´Èét(€€€€€€€µ…©½É¥Ñå}Ù…±Õ”€ôÑ½ÀÈ¹µ…à¡…á¥ÌôÄ¤(€€€€€€€Í•½¹‘}Ù…±Õ”€ôÑ½ÀÈ¹µ¥¸¡…á¥ÌôÄ¤(€€€•±Í”è(€€€€€€€µ…©½É¥Ñå}Ù…±Õ”€ôÙ…±Õ•Ílè°€Át(€€€€€€€Í•½¹‘}Ù…±Õ”€ô¹À¹é•É½Ì¡±•¸¡á}™Ì¤°‘ÑåÁ”õ¹À¹™±½…ÐØÐ¤((€€€µ…©½É¥Ñå}‘•±Ñ„€ôµ…©½É¥Ñå}Ù…±Õ”€´Í•½¹‘}Ù…±Õ”(€€€á}™Íl‰µ…©½É¥Ñå}Ù…±Õ”‰t€ô€ (€€€€€€€¹À¹É¥¹Ð¡µ…©½É¥Ñå}Ù…±Õ”¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€¤(€€€á}™Íl‰Í•½¹‘}Ù…±Õ”‰t€ô€ (€€€€€€€¹À¹É¥¹Ð¡Í•½¹‘}Ù…±Õ”¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€¤(€€€á}™Íl‰µ…©½É¥Ñå}‘•±Ñ„‰t€ô€ (€€€€€€€¹À¹É¥¹Ð¡µ…©½É¥Ñå}‘•±Ñ„¤¹±¥À À°€ØÔÔÌÔ¤¹…ÍÑåÁ”¡¹À¹Õ¥¹ÐÄØ¤(€€€€¤(€€€á}™Íl‰µ…©½É¥Ñå}‘¥ÍÁÕÑ•‰t€ôá}™Íl‰µ…©½É¥Ñå}‘•±Ñ„‰t€ðô€ÈÀÀ((€€€…‰}½±Ì€ôl(€€€€€€€½±Õµ¸™½È½±Õµ¸¥¸á}™Ì¹½±Õµ¹Ì¥˜½±Õµ¸¹•¹‘ÍÝ¥Ñ   ‰}ˆ°€‰}ˆ°€‰}ˆ¤¤(€€€t(€€€±½¹œ€ôá}™Ím…‰}½±Ít¹ÍÑ…¬ ¤¹É•¹…µ” ‰Ù…±Õ”ˆ¤¹É•Í•Ñ}¥¹‘•à ¤(€€€ÍÑ…ÑÕÍ}½±Õµ¸€ô±½¹œ¹½±Õµ¹ÍlÅt(€€€ÍÁ±¥Ð€ô±½¹mÍÑ…ÑÕÍ}½±Õµ¹t¹…ÍÑåÁ”¡ÍÑÈ¤¹ÍÑÈ¹ÉÍÁ±¥Ð ‰|ˆ°¸ôÄ°•áÁ…¹õQÉÕ”¤(€€€±½¹l‰™½Éµ…Ñ¥½¸‰t€ôÍÁ±¥ÑlÁt(€€€±½¹l‰ÍÑ…ÑÕÌ‰t€ôÍÁ±¥ÑlÅt(€€€±½¹l‰5…©½É¥Ñå}™½Éµ…Ñ¥½¸‰t€ôá}™Ì¹±½l(€€€€€€€±½¹l‰É¥‘}¥‰t°€‰5…©½É¥Ñå}™½Éµ…Ñ¥½¸ˆ(€€€t¹Ù…±Õ•Ì(€€€±½¹œ€ô±½¹m±½¹l‰™½Éµ…Ñ¥½¸‰t€ôô±½¹l‰5…©½É¥Ñå}™½Éµ…Ñ¥½¸‰ut((€€€µ…©}ÍÑ…ÑÕÌ€ô€ (€€€€€€€±½¹m±½¹l‰Ù…±Õ”‰t€ø€Át(€€€€€€€€¹Í½ÉÑ}Ù…±Õ•Ì¡l‰É¥‘}¥ˆ°€‰Ù…±Õ”ˆ°€‰ÍÑ…ÑÕÌ‰t°…Í•¹‘¥¹œõmQÉÕ”°…±Í”°QÉÕ•t¤(€€€€€€€€¹‘É½Á}‘ÕÁ±¥…Ñ•Ì ‰É¥‘}¥ˆ¤(€€€€€€€€¹Í•Ñ}¥¹‘•à ‰É¥‘}¥ˆ¥l‰ÍÑ…ÑÕÌ‰t(€€€€¤(€€€á}™Íl‰µ…©½É¥Ñå}™½Éµ…Ñ¥½¹}ÍÑ…ÑÕÌ‰t€ôµ…©}ÍÑ…ÑÕÌ((€€€à€ôá}™Ì¹É•Í•Ñ}¥¹‘•à ¤¹µ•É” (€€€€€€€á}±ÉÐ¹É•Í•Ñ}¥¹‘•à ¤°(€€€€€€€½¸ô‰É¥‘}¥ˆ°(€€€€€€€¡½Üô‰¥¹¹•Èˆ°(€€€€¤(€€€á}™Í}½ÕÐ€ôá}™Ì¹É•Í•Ñ}¥¹‘•à ¤((€€€Ý¥Ñ¡}±ÉÑ}ÍØ€ô½ÕÑÁÕÑ}‘¥È€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥‘}Ý¥Ñ¡1IQ½‘”¹ÍØˆ(€€€Ý¥Ñ¡}±ÉÑ}Á…ÉÅÕ•Ð€ô½ÕÑÁÕÑ}‘¥È€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥‘}Ý¥Ñ¡1IQ½‘”¹Á…ÉÅÕ•Ðˆ(€€€™½Éµ…Ñ¥½¹}ÍØ€ô½ÕÑÁÕÑ}‘¥È€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥¹ÍØˆ((€€€…Ñ½µ¥}ÝÉ¥Ñ•}ÍØ¡à°Ý¥Ñ¡}±ÉÑ}ÍØ¤(€€€…Ñ½µ¥}ÝÉ¥Ñ•}Á…ÉÅÕ•Ð (€€€€€€€à°(€€€€€€€Ý¥Ñ¡}±ÉÑ}Á…ÉÅÕ•Ð°(€€€€¤(€€€…Ñ½µ¥}ÝÉ¥Ñ•}ÍØ¡á}™Í}½ÕÐ°™½Éµ…Ñ¥½¹}ÍØ¤((€€€É•ÑÕÉ¸ì(€€€€€€€€‰É½ÝÌˆè¥¹Ð¡±•¸¡à¤¤°(€€€€€€€€‰½±Õµ¹Í}Ý¥Ñ¡}±ÉÐˆè±¥ÍÐ¡à¹½±Õµ¹Ì¤°(€€€€€€€€‰½ÕÑÁÕÑ}‘¥ÈˆèÍÑÈ¡½ÕÑÁÕÑ}‘¥È¤°(€€€€€€€€‰Ý¥Ñ¡}±ÉÑ}ÍØˆèÍÑÈ¡Ý¥Ñ¡}±ÉÑ}ÍØ¤°(€€€€€€€€‰Ý¥Ñ¡}±ÉÑ}Á…ÉÅÕ•ÐˆèÍÑÈ¡Ý¥Ñ¡}±ÉÑ}Á…ÉÅÕ•Ð¤°(€€€€€€€€‰™½Éµ…Ñ¥½¹}ÍØˆèÍÑÈ¡™½Éµ…Ñ¥½¹}ÍØ¤°(€€€€€€€€‰¥á}ÍØˆèÍÑÈ¡½ÕÑÁÕÑ}‘¥È€¼€‰¥à¹ÍØˆ¤¥˜ÝÉ¥Ñ•}¥¹Ñ•ÉÍ•Ñ¥½¹Í}ÍØ•±Í”9½¹”°(€€€ô(()‘•˜ÝÉ¥Ñ•}ÍÑ…Ñ” (€€€ÍÑ…Ñ•}™¥±”èA…Ñ °(€€€•áÁ•Ñ•‘}ÍÑ…Ñ”è‘¥ÑmÍÑÈ°¹åt°(€€€½ÕÑÁÕÑ}É½ÝÌè¥¹Ð°(¤€´ø9½¹”è(€€€ÍÑ…Ñ”€ôì(€€€€€€€€¨©•áÁ•Ñ•‘}ÍÑ…Ñ”°(€€€€€€€€‰É•ÍÕ±Ðˆèì‰½ÕÑÁÕÑ}É½ÝÌˆè½ÕÑÁÕÑ}É½ÝÍô°(€€€ô(€€€…Ñ½µ¥}ÝÉ¥Ñ•}©Í½¸¡ÍÑ…Ñ•}™¥±”°ÍÑ…Ñ”¤(()‘•˜Á…ÉÍ•}…ÉÌ ¤€´ø…ÉÁ…ÉÍ”¹9…µ•ÍÁ…”è(€€€Á…ÉÍ•È€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È (€€€€€€€‘•ÍÉ¥ÁÑ¥½¸ô‰MÑ•À€É|Äèµ•É”±•…¹•1IQÌ…¹€ÄÀÀ´É¥¸ˆ(€€€€¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð (€€€€€€€€ˆ´µ½¹™¥œˆ°(€€€€€€€ÑåÁ”õA…Ñ °(€€€€€€€‘•™…Õ±ÐõA…Ñ ¡}}™¥±•}|¤¹É•Í½±Ù” ¤¹Á…É•¹ÑÍlÅt€¼€‰½¹™¥œ¹©Í½¸ˆ°(€€€€¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ™½É”ˆ°…Ñ¥½¸ô‰ÍÑ½É•}ÑÉÕ”ˆ¤(€€€É•ÑÕÉ¸Á…ÉÍ•È¹Á…ÉÍ•}…ÉÌ ¤(()‘•˜µ…¥¸ ¤€´ø¥¹Ðè(€€€…ÉÌ€ôÁ…ÉÍ•}…ÉÌ ¤((€€€ÑÉäè(€€€€€€€½¹™¥œ€ô±½…‘}½¹™¥œ¡…ÉÌ¹½¹™¥œ¤(€€€€€€€Í•ÑÑ¥¹Ì€ô½¹™¥l‰±ÉÑ}É¥‘}µ•É”‰t((€€€€€€€É¥‘}Á­œ€ôA…Ñ ¡Í•ÑÑ¥¹Íl‰É¥‘}Á­œ‰t¤(€€€€€€€É¥‘}±…å•È€ôÍ•ÑÑ¥¹Ì¹•Ð ‰É¥‘}±…å•Èˆ°€‰É¥ˆ¤(€€€€€€€É¥‘}¥‘}½±Õµ¸€ôÍ•ÑÑ¥¹Ì¹•Ð ‰É¥‘}¥‘}½±Õµ¸ˆ°€‰É¥‘}¥ˆ¤((€€€€€€€±ÉÑ}Á­œ€ôA…Ñ ¡Í•ÑÑ¥¹Íl‰±ÉÑ}Á­œ‰t¤(€€€€€€€±ÉÑ}±…å•È€ôÍ•ÑÑ¥¹Ì¹•Ð ‰±ÉÑ}±…å•Èˆ°€‰±ÉÐˆ¤((€€€€€€€½ÕÑÁÕÑ}ÍØ€ôA…Ñ ¡Í•ÑÑ¥¹Íl‰½ÕÑÁÕÑ}ÍØ‰t¤(€€€€€€€½ÕÑÁÕÑ}Á…ÉÅÕ•Ð€ô€ (€€€€€€€€€€€A…Ñ ¡Í•ÑÑ¥¹Íl‰½ÕÑÁÕÑ}Á…ÉÅÕ•Ð‰t¤(€€€€€€€€€€€¥˜Í•ÑÑ¥¹Ì¹•Ð ‰½ÕÑÁÕÑ}Á…ÉÅÕ•Ðˆ¤(€€€€€€€€€€€•±Í”9½¹”(€€€€€€€€¤((€€€€€€€½ÕÑÁÕÑ}É¥‘}Á­œ€ôA…Ñ  (€€€€€€€€€€€Í•ÑÑ¥¹Ì¹•Ð (€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}Á­œˆ°(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}ÍØ¹Á…É•¹Ð€¼€‰µ…©½É¥Ñå}™½Éµ…Ñ¥½¹}É¥¹Á­œˆ°(€€€€€€€€€€€€¤(€€€€€€€€¤(€€€€€€€½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ð€ôA…Ñ  (€€€€€€€€€€€Í•ÑÑ¥¹Ì¹•Ð (€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ðˆ°(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}ÍØ¹Á…É•¹Ð€¼€‰µ…©½É¥Ñå}™½Éµ…Ñ¥½¹}É¥¹Á…ÉÅÕ•Ðˆ°(€€€€€€€€€€€€¤(€€€€€€€€¤(€€€€€€€½ÕÑÁÕÑ}É¥‘}±…å•È€ôÍ•ÑÑ¥¹Ì¹•Ð (€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}±…å•Èˆ°(€€€€€€€€€€€€‰µ…©½É¥Ñå}™½Éµ…Ñ¥½¹|ÄÀÁ´ˆ°(€€€€€€€€¤((€€€€€€€½ÕÑÁÕÑ}Á…Ñ¡Ì€ôl(€€€€€€€€€€€½ÕÑÁÕÑ}ÍØ°(€€€€€€€€€€€½ÕÑÁÕÑ}É¥‘}Á­œ°(€€€€€€€€€€€½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ð°(€€€€€€€t(€€€€€€€¥˜½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¥Ì¹½Ð9½¹”è(€€€€€€€€€€€½ÕÑÁÕÑ}Á…Ñ¡Ì¹…ÁÁ•¹¡½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¤((€€€€€€€ÍÕÍ¥}Í•ÑÑ¥¹Ì€ôÍ•ÑÑ¥¹Ì¹•Ð ‰ÍÕÍ¥}½µÁ…Ñ¥‰±•}½ÕÑÁÕÑÌˆ°íô¤(€€€€€€€ÍÕÍ¥}•¹…‰±•€ô‰½½°¡ÍÕÍ¥}Í•ÑÑ¥¹Ì¹•Ð ‰•¹…‰±•ˆ°…±Í”¤¤(€€€€€€€ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È€ôA…Ñ  (€€€€€€€€€€€ÍÕÍ¥}Í•ÑÑ¥¹Ì¹•Ð (€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}‘¥Èˆ°(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}ÍØ¹Á…É•¹Ð€¼€‰ÍÕÍ¥}½µÁ…Ñ¥‰±”ˆ°(€€€€€€€€€€€€¤(€€€€€€€€¤(€€€€€€€ÍÕÍ¥}ÝÉ¥Ñ•}¥à€ô‰½½° (€€€€€€€€€€€ÍÕÍ¥}Í•ÑÑ¥¹Ì¹•Ð ‰ÝÉ¥Ñ•}¥¹Ñ•ÉÍ•Ñ¥½¹Í}ÍØˆ°…±Í”¤(€€€€€€€€¤(€€€€€€€¥˜ÍÕÍ¥}•¹…‰±•è(€€€€€€€€€€€½ÕÑÁÕÑ}Á…Ñ¡Ì¹•áÑ•¹ (€€€€€€€€€€€€€€€l(€€€€€€€€€€€€€€€€€€€ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥‘}Ý¥Ñ¡1IQ½‘”¹ÍØˆ°(€€€€€€€€€€€€€€€€€€€ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È(€€€€€€€€€€€€€€€€€€€€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥‘}Ý¥Ñ¡1IQ½‘”¹Á…ÉÅÕ•Ðˆ°(€€€€€€€€€€€€€€€€€€€ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È€¼€‰½Éµ…Ñ¥½¹}MÑ…ÑÕÍ}É¥¹ÍØˆ°(€€€€€€€€€€€€€€€t(€€€€€€€€€€€€¤(€€€€€€€€€€€¥˜ÍÕÍ¥}ÝÉ¥Ñ•}¥àè(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}Á…Ñ¡Ì¹…ÁÁ•¹¡ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È€¼€‰¥à¹ÍØˆ¤((€€€€€€€¡Õ¹­}Í¥é”€ô¥¹Ð¡Í•ÑÑ¥¹Ì¹•Ð ‰¡Õ¹­}Í¥é”ˆ°€ÄÀÁ|ÀÀÀ¤¤(€€€€€€€É…Ý}¡•­Á½¥¹Ñ}‘¥È€ôÍ•ÑÑ¥¹Ì¹•Ð ‰¡Õ¹­}¡•­Á½¥¹Ñ}‘¥Èˆ¤(€€€€€€€¡Õ¹­}¡•­Á½¥¹Ñ}É½½Ð€ô€ (€€€€€€€€€€€A…Ñ ¡É…Ý}¡•­Á½¥¹Ñ}‘¥È¤(€€€€€€€€€€€¥˜É…Ý}¡•­Á½¥¹Ñ}‘¥È(€€€€€€€€€€€•±Í”½ÕÑÁÕÑ}ÍØ¹Á…É•¹Ð€¼€‰}¡Õ¹­}¡•­Á½¥¹ÑÌˆ(€€€€€€€€¤(€€€€€€€•±±}…É•…}´È€ô™±½…Ð¡Í•ÑÑ¥¹Ì¹•Ð ‰•±±}…É•…}´Èˆ°€ÄÁ|ÀÀÀ¤¤(€€€€€€€‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐ€ô™±½…Ð (€€€€€€€€€€€Í•ÑÑ¥¹Ì¹•Ð ‰‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐˆ°€È¸À¤(€€€€€€€€¤((€€€€€€€…±±½…Ñ•‘}ÁÕÌ€ô¥¹Ð (€€€€€€€€€€€½Ì¹•¹Ù¥É½¸¹•Ð ‰M1UI5}AUM}AI}QM,ˆ°€ˆÄˆ¤(€€€€€€€€¤(€€€€€€€½¹™¥ÕÉ•‘}ÁÉ½•ÍÍ•Ì€ô¥¹Ð (€€€€€€€€€€€Í•ÑÑ¥¹Ì¹•Ð ‰ÁÉ½•ÍÍ•Ìˆ°…±±½…Ñ•‘}ÁÕÌ¤(€€€€€€€€¤(€€€€€€€ÁÉ½•ÍÍ•Ì€ôµ…à (€€€€€€€€€€€€Ä°(€€€€€€€€€€€µ¥¸¡½¹™¥ÕÉ•‘}ÁÉ½•ÍÍ•Ì°…±±½…Ñ•‘}ÁÕÌ¤°(€€€€€€€€¤(€€€€€€€É…Ý}µ…áÑ…Í­Ì€ôÍ•ÑÑ¥¹Ì¹•Ð ‰µ…áÑ…Í­ÍÁ•É¡¥±ˆ¤(€€€€€€€µ…áÑ…Í­ÍÁ•É¡¥±€ô€ (€€€€€€€€€€€¥¹Ð¡É…Ý}µ…áÑ…Í­Ì¤(€€€€€€€€€€€¥˜É…Ý}µ…áÑ…Í­Ì¥Ì¹½Ð9½¹”(€€€€€€€€€€€•±Í”9½¹”(€€€€€€€€¤((€€€€€€€¥˜€‰M1UI5})=	}%ˆ¹½Ð¥¸½Ì¹•¹Ù¥É½¸…¹½¹™¥ÕÉ•‘}ÁÉ½•ÍÍ•Ì€ø€Äè(€€€€€€€€€€€ÁÉ¥¹Ð (€€€€€€€€€€€€€€€€‰]I9%9è½ÕÑÍ¥‘”M±ÕÉ´ìMÑ•À€É|Ä¥ÌÉ•ÍÑÉ¥Ñ•€ˆ(€€€€€€€€€€€€€€€€‰Ñ¼½¹”ÁÉ½•ÍÌ¸ˆ°(€€€€€€€€€€€€€€€™¥±”õÍåÌ¹ÍÑ‘•ÉÈ°(€€€€€€€€€€€€¤((€€€€€€€ÍÑ…ÑÕÍ}‘¥È€ôA…Ñ ¡½¹™¥l‰ÍÑ…ÑÕÍ}‘¥È‰t¤(€€€€€€€ÍÑ…Ñ•}™¥±”€ôA…Ñ  (€€€€€€€€€€€Í•ÑÑ¥¹Ì¹•Ð (€€€€€€€€€€€€€€€€‰ÍÑ…Ñ•}™¥±”ˆ°(€€€€€€€€€€€€€€€ÍÑ…ÑÕÍ}‘¥È€¼€‰ÍÑ•Á|É|Å}±ÉÑ}É¥‘}µ•É•}ÍÑ…Ñ”¹©Í½¸ˆ°(€€€€€€€€€€€€¤(€€€€€€€€¤((€€€€€€€¥¹ÁÕÑ}ÍÑ…Ñ”€ôì(€€€€€€€€€€€€‰É¥‘}Á­œˆè™¥±•}™¥¹•ÉÁÉ¥¹Ð¡É¥‘}Á­œ¤°(€€€€€€€€€€€€‰±ÉÑ}Á­œˆè™¥±•}™¥¹•ÉÁÉ¥¹Ð¡±ÉÑ}Á­œ¤°(€€€€€€€ô(€€€€€€€¡•­Á½¥¹Ñ}Á…å±½…€ôì(€€€€€€€€€€€€‰¥¹ÁÕÑÌˆè¥¹ÁÕÑ}ÍÑ…Ñ”°(€€€€€€€€€€€€‰É¥‘}±…å•ÈˆèÉ¥‘}±…å•È°(€€€€€€€€€€€€‰É¥‘}¥‘}½±Õµ¸ˆèÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€€‰±ÉÑ}±…å•Èˆè±ÉÑ}±…å•È°(€€€€€€€€€€€€‰¡Õ¹­}Í¥é”ˆè¡Õ¹­}Í¥é”°(€€€€€€€ô(€€€€€€€¡•­Á½¥¹Ñ}¹…µ•ÍÁ…”€ô¡…Í¡±¥ˆ¹Í¡„ÈÔØ (€€€€€€€€€€€©Í½¸¹‘ÕµÁÌ (€€€€€€€€€€€€€€€¡•­Á½¥¹Ñ}Á…å±½…°(€€€€€€€€€€€€€€€Í½ÉÑ}­•åÌõQÉÕ”°(€€€€€€€€€€€€€€€Í•Á…É…Ñ½ÉÌô ˆ°ˆ°€ˆèˆ¤°(€€€€€€€€€€€€¤¹•¹½‘” ‰ÕÑ˜´àˆ¤(€€€€€€€€¤¹¡•á‘¥•ÍÐ ¥lèÄÙt(€€€€€€€¡Õ¹­}¡•­Á½¥¹Ñ}‘¥È€ô¡Õ¹­}¡•­Á½¥¹Ñ}É½½Ð€¼¡•­Á½¥¹Ñ}¹…µ•ÍÁ…”((€€€€€€€•áÁ•Ñ•‘}ÍÑ…Ñ”€ôì(€€€€€€€€€€€€‰¥¹ÁÕÑÌˆè¥¹ÁÕÑ}ÍÑ…Ñ”°(€€€€€€€€€€€€‰ÁÉ½•ÍÍ¥¹œˆèì(€€€€€€€€€€€€€€€€‰É¥‘}±…å•ÈˆèÉ¥‘}±…å•È°(€€€€€€€€€€€€€€€€‰É¥‘}¥‘}½±Õµ¸ˆèÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€€€€€€‰±ÉÑ}±…å•Èˆè±ÉÑ}±…å•È°(€€€€€€€€€€€€€€€€‰¡Õ¹­}Í¥é”ˆè¡Õ¹­}Í¥é”°(€€€€€€€€€€€€€€€€‰¡Õ¹­}¡•­Á½¥¹Ñ}É½½ÐˆèÍÑÈ¡¡Õ¹­}¡•­Á½¥¹Ñ}É½½Ð¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€‰¡Õ¹­}¡•­Á½¥¹Ñ}¹…µ•ÍÁ…”ˆè¡•­Á½¥¹Ñ}¹…µ•ÍÁ…”°(€€€€€€€€€€€€€€€€‰¡Õ¹­}¡•­Á½¥¹Ñ}‘¥ÈˆèÍÑÈ¡¡Õ¹­}¡•­Á½¥¹Ñ}‘¥È¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€‰•±±}…É•…}´Èˆè•±±}…É•…}´È°(€€€€€€€€€€€€€€€€‰‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐˆè‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐ°(€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}ÍØˆèÍÑÈ¡½ÕÑÁÕÑ}ÍØ¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}Á…ÉÅÕ•Ðˆè€ (€€€€€€€€€€€€€€€€€€€ÍÑÈ¡½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¹É•Í½±Ù” ¤¤(€€€€€€€€€€€€€€€€€€€¥˜½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¥Ì¹½Ð9½¹”(€€€€€€€€€€€€€€€€€€€•±Í”9½¹”(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}Á­œˆèÍÑÈ¡½ÕÑÁÕÑ}É¥‘}Á­œ¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•ÐˆèÍÑÈ¡½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ð¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}É¥‘}±…å•Èˆè½ÕÑÁÕÑ}É¥‘}±…å•È°(€€€€€€€€€€€€€€€€‰ÍÕÍ¥}µ…ÑÉ¥á}Í¡•µ…}Ù•ÉÍ¥½¸ˆèMUM%}5QI%a}M!5}YIM%=8°(€€€€€€€€€€€€€€€€‰ÍÕÍ¥}½µÁ…Ñ¥‰±•}½ÕÑÁÕÑÌˆèì(€€€€€€€€€€€€€€€€€€€€‰•¹…‰±•ˆèÍÕÍ¥}•¹…‰±•°(€€€€€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}‘¥ÈˆèÍÑÈ¡ÍÕÍ¥}½ÕÑÁÕÑ}‘¥È¹É•Í½±Ù” ¤¤°(€€€€€€€€€€€€€€€€€€€€‰ÝÉ¥Ñ•}¥¹Ñ•ÉÍ•Ñ¥½¹Í}ÍØˆèÍÕÍ¥}ÝÉ¥Ñ•}¥à°(€€€€€€€€€€€€€€€ô°(€€€€€€€€€€€ô°(€€€€€€€ô((€€€€€€€¥˜Í¡½Õ±‘}Í­¥À (€€€€€€€€€€€½ÕÑÁÕÑ}Á…Ñ¡Ì°(€€€€€€€€€€€ÍÑ…Ñ•}™¥±”°(€€€€€€€€€€€•áÁ•Ñ•‘}ÍÑ…Ñ”°(€€€€€€€€€€€…ÉÌ¹™½É”°(€€€€€€€€¤è(€€€€€€€€€€€ÁÉ¥¹Ð (€€€€€€€€€€€€€€€€‰MÑ•À€É|ÄÍ­¥ÁÁ•è½ÕÑÁÕÑÌ•á¥ÍÐ…¹¥¹ÁÕÑÌ…É”Õ¹¡…¹•¸ˆ(€€€€€€€€€€€€¤(€€€€€€€€€€€™½ÈÁ…Ñ ¥¸½ÕÑÁÕÑ}Á…Ñ¡Ìè(€€€€€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰=ÕÑÁÕÐèíÁ…Ñ¡ôˆ¤(€€€€€€€€€€€É•ÑÕÉ¸€À((€€€€€€€É¥°±ÉÐ€ôÉ•…‘}¥¹ÁÕÑÌ (€€€€€€€€€€€É¥‘}Á­œõÉ¥‘}Á­œ°(€€€€€€€€€€€É¥‘}±…å•ÈõÉ¥‘}±…å•È°(€€€€€€€€€€€±ÉÑ}Á­œõ±ÉÑ}Á­œ°(€€€€€€€€€€€±ÉÑ}±…å•Èõ±ÉÑ}±…å•È°(€€€€€€€€€€€É¥‘}¥‘}½±Õµ¸õÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€¤((€€€€€€€ÁÉ¥¹Ð¡˜‰É¥•±±Ì€èí±•¸¡É¥¤è±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰1IPÉ½ÝÌ€€€èí±•¸¡±ÉÐ¤è±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰¡Õ¹¬Í¥é”€èí¡Õ¹­}Í¥é”è±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰AÉ½•ÍÍ•Ì€€èíÁÉ½•ÍÍ•Íôˆ¤((€€€€€€€¥¹Ñ•ÉÍ•Ñ¥½¹Ì€ô¥¹Ñ•ÉÍ•Ñ}¥¹}¡Õ¹­Ì (€€€€€€€€€€€É¥õÉ¥°(€€€€€€€€€€€±ÉÐõ±ÉÐ°(€€€€€€€€€€€É¥‘}¥‘}½±Õµ¸õÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€¡Õ¹­}Í¥é”õ¡Õ¹­}Í¥é”°(€€€€€€€€€€€ÁÉ½•ÍÍ•ÌõÁÉ½•ÍÍ•Ì°(€€€€€€€€€€€µ…áÑ…Í­ÍÁ•É¡¥±õµ…áÑ…Í­ÍÁ•É¡¥±°(€€€€€€€€€€€¡•­Á½¥¹Ñ}‘¥Èõ¡Õ¹­}¡•­Á½¥¹Ñ}‘¥È°(€€€€€€€€¤((€€€€€€€ÍÕµµ…Éä°‘•Ñ…¥±•€ô‰Õ¥±‘}ÍÕµµ…Éä (€€€€€€€€€€€¥¹Ñ•ÉÍ•Ñ¥½¹Ìõ¥¹Ñ•ÉÍ•Ñ¥½¹Ì°(€€€€€€€€€€€É¥‘}¥‘}½±Õµ¸õÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€•±±}…É•…}´Èõ•±±}…É•…}´È°(€€€€€€€€€€€‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐõ‘¥ÍÁÕÑ•‘}Ñ¡É•Í¡½±‘}ÁÐ°(€€€€€€€€¤((€€€€€€€½ÕÑÁÕÑ}ÍØ¹Á…É•¹Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€€€€…Ñ½µ¥}ÝÉ¥Ñ•}ÍØ¡ÍÕµµ…Éä°½ÕÑÁÕÑ}ÍØ¤((€€€€€€€¥˜½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¥Ì¹½Ð9½¹”è(€€€€€€€€€€€…Ñ½µ¥}ÝÉ¥Ñ•}Á…ÉÅÕ•Ð (€€€€€€€€€€€€€€€‘•Ñ…¥±•°(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}Á…ÉÅÕ•Ð°(€€€€€€€€€€€€¤((€€€€€€€É¥‘}É½ÝÌ°É¥‘}½±Õµ¹Ì€ôÝÉ¥Ñ•}¹½Ñ•‰½½­}É¥‘}ÁÉ½‘ÕÑÌ (€€€€€€€€€€€É¥õÉ¥°(€€€€€€€€€€€ÍÕµµ…ÉäõÍÕµµ…Éä°(€€€€€€€€€€€É¥‘}¥‘}½±Õµ¸õÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€½ÕÑÁÕÑ}Á­œõ½ÕÑÁÕÑ}É¥‘}Á­œ°(€€€€€€€€€€€½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ðõ½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ð°(€€€€€€€€€€€½ÕÑÁÕÑ}±…å•Èõ½ÕÑÁÕÑ}É¥‘}±…å•È°(€€€€€€€€¤((€€€€€€€ÍÕÍ¥}É•ÍÕ±Ð€ô9½¹”(€€€€€€€¥˜ÍÕÍ¥}•¹…‰±•è(€€€€€€€€€€€ÍÕÍ¥}É•ÍÕ±Ð€ôÝÉ¥Ñ•}ÍÕÍ¥}½µÁ…Ñ¥‰±•|ÄÀÁµ}ÁÉ½‘ÕÑÌ (€€€€€€€€€€€€€€€¥¹Ñ•ÉÍ•Ñ¥½¹Ìõ¥¹Ñ•ÉÍ•Ñ¥½¹Ì°(€€€€€€€€€€€€€€€É¥‘}¥‘}½±Õµ¸õÉ¥‘}¥‘}½±Õµ¸°(€€€€€€€€€€€€€€€•±±}…É•…}´Èõ•±±}…É•…}´È°(€€€€€€€€€€€€€€€½ÕÑÁÕÑ}‘¥ÈõÍÕÍ¥}½ÕÑÁÕÑ}‘¥È°(€€€€€€€€€€€€€€€ÝÉ¥Ñ•}¥¹Ñ•ÉÍ•Ñ¥½¹Í}ÍØõÍÕÍ¥}ÝÉ¥Ñ•}¥à°(€€€€€€€€€€€€¤((€€€€€€€ÝÉ¥Ñ•}ÍÑ…Ñ”¡ÍÑ…Ñ•}™¥±”°•áÁ•Ñ•‘}ÍÑ…Ñ”°±•¸¡ÍÕµµ…Éä¤¤((€€€€€€€ÁÉ¥¹Ð ‰q¹MÑ•À€É|Ä½µÁ±•Ñ•¸ˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰=ÕÑÁÕÐÉ½ÝÌ€èí±•¸¡ÍÕµµ…Éä¤è±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰MÕµµ…ÉäMX€èí½ÕÑÁÕÑ}ÍÙôˆ¤(€€€€€€€¥˜½ÕÑÁÕÑ}Á…ÉÅÕ•Ð¥Ì¹½Ð9½¹”è(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰•Ñ…¥±•€€€€èí½ÕÑÁÕÑ}Á…ÉÅÕ•Ñôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰É¥A-€€€èí½ÕÑÁÕÑ}É¥‘}Á­ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰É¥A…ÉÅÕ•Ðèí½ÕÑÁÕÑ}É¥‘}Á…ÉÅÕ•Ñôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰É¥É½ÝÌ€€€èíÉ¥‘}É½ÝÌè±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰É¥½±Õµ¹Ìèìœ°€œ¹©½¥¸¡É¥‘}½±Õµ¹Ì¥ôˆ¤(€€€€€€€¥˜ÍÕÍ¥}É•ÍÕ±Ð¥Ì¹½Ð9½¹”è(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰MÕÍ¤€ÄÀÁ´€€€èíÍÕÍ¥}É•ÍÕ±Ñl½ÕÑÁÕÑ}‘¥Èuôˆ¤(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰MÕÍ¤É½ÝÌ€€€èíÍÕÍ¥}É•ÍÕ±ÑlÉ½ÝÌtè±ôˆ¤(€€€€€€€ÁÉ¥¹Ð¡˜‰MÑ…Ñ”™¥±”€€èíÍÑ…Ñ•}™¥±•ôˆ¤(€€€€€€€É•ÑÕÉ¸€À((€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€ÁÉ¥¹Ð¡˜‰II=H¥¸MÑ•À€É|Äèí•áôˆ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ¤(€€€€€€€É•ÑÕÉ¸€Ä(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€µÀ¹™É••é•}ÍÕÁÁ½ÉÐ ¤(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤(
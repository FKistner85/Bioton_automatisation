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
SUSI_MATRIX_SCHEMA_VERSION = "2026-07-29-centi-percent-abck-v2"


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
            "coverage_pct": "majority_formation_coverage_pct",
        }
    )

    selected = intersections.merge(
        majority[[grid_id_column, "majority_formation"]],
        left_on=[grid_id_column, "Formation"],
        right_on=[grid_id_column, "majority_formation"],
        how="inner",
    )

    majority_polygon_status = (
        selected.groupby(grid_id_column)
        .agg(
            majority_formation_polygon_count=("src_id", "nunique"),
            majority_formation_status_count=(
                "conservation_status",
                lambda values: values.dropna().nunique(),
            ),
        )
        .reset_index()
    )

    majority_polygon_status[
        "majority_formation_mixed_conservation_status"
    ] = (
        (majority_polygon_status["majority_formation_polygon_count"] > 1)
        & (majority_polygon_status["majority_formation_status_count"] > 1)
    )

    status_area = (
        selected[
            selected["conservation_status"].isin(["A", "B", "C"])
        ]
        .groupby(
            [grid_id_column, "conservation_status"],
            as_index=False,
        )["intersection_area_m2"]
        .sum()
    )
    status_area["coverage_pct"] = (
        status_area["intersection_area_m2"] / cell_area_m2 * 100
    )

    status_priority = {"A": 1, "B": 2, "C": 3}
    status_area["tie_priority"] = (
        status_area["conservation_status"].map(status_priority)
    )
    status_ranked = status_area.sort_values(
        [grid_id_column, "intersection_area_m2", "tie_priority"],
        ascending=[True, False, True],
    ).copy()
    status_ranked["status_rank"] = (
        status_ranked.groupby(grid_id_column).cumcount() + 1
    )
    status_top3 = add_top3_metrics(
        ranked=status_ranked,
        grid_id_column=grid_id_column,
        label_column="conservation_status",
        value_column="coverage_pct",
        rank_column="status_rank",
        prefix="majority_formation_status",
    )

    status_majority = (
        status_ranked
        .drop_duplicates(grid_id_column)
        .rename(
            columns={
                "conservation_status": "majority_formation_status",
                "intersection_area_m2": (
                    "majority_formation_status_area_m2"
                ),
            }
        )
    )
    status_majority["majority_formation_status_coverage_pct"] = (
        status_majority["majority_formation_status_area_m2"]
        / cell_area_m2
        * 100
    )

    # Notebook-compatible representative polygon:
    # choose the single LRT polygon with the largest intersection area
    # inside the selected majority formation for each 100 m grid cell.
    lrt_best = (
        selected.sort_values(
            [grid_id_column, "intersection_area_m2", "src_id"],
            ascending=[True, False, True],
        )
        .drop_duplicates(grid_id_column, keep="first")
        [[grid_id_column, "LRT_code", "mapping_year"]]
        .rename(
            columns={
                "LRT_code": "majority_formation_lrt_code",
                "mapping_year": "representative_mapping_year",
            }
        )
    )

    year_area = (
        selected[selected["mapping_year"].notna()]
        .groupby(
            [grid_id_column, "mapping_year"],
            as_index=False,
        )["intersection_area_m2"]
        .sum()
    )

    year_majority = (
        year_area.sort_values(
            [grid_id_column, "intersection_area_m2", "mapping_year"],
            ascending=[True, False, False],
        )
        .drop_duplicates(grid_id_column)
        .rename(
            columns={
                "mapping_year": "majority_formation_mapping_year",
                "intersection_area_m2": (
                    "majority_formation_mapping_year_area_m2"
                ),
            }
        )
    )
    year_majority["majority_formation_mapping_year_coverage_pct"] = (
        year_majority["majority_formation_mapping_year_area_m2"]
        / cell_area_m2
        * 100
    )

    summary = majority[
        [
            grid_id_column,
            "majority_formation",
            "majority_formation_coverage_pct",
            "majority_gap_pct",
            "majority_disputed",
        ]
    ].merge(
        formation_counts,
        on=grid_id_column,
        how="left",
    ).merge(
        formation_top3,
        on=grid_id_column,
        how="left",
    ).merge(
        majority_polygon_status,
        on=grid_id_column,
        how="left",
    ).merge(
        status_majority[
            [
                grid_id_column,
                "majority_formation_status",
                "majority_formation_status_coverage_pct",
            ]
        ],
        on=grid_id_column,
        how="left",
    ).merge(
        status_top3,
        on=grid_id_column,
        how="left",
    ).merge(
        year_majority[
            [
                grid_id_column,
                "majority_formation_mapping_year",
                "majority_formation_mapping_year_coverage_pct",
            ]
        ],
        on=grid_id_column,
        how="left",
    )

    summary["majority_formation_mapping_year"] = (
        summary["majority_formation_mapping_year"].astype("Int64")
    )

    summary = summary.merge(
        lrt_best,
        on=grid_id_column,
        how="left",
    )

    # Exact column names used in the original notebook.
    summary["Majority_formation"] = summary["majority_formation"]
    summary["LRT_code"] = summary["majority_formation_lrt_code"]
    summary["mapping_year"] = pd.to_numeric(
        summary["representative_mapping_year"],
        errors="coerce",
    ).astype("Int64")

    formation_wide = formation_area.pivot(
        index=grid_id_column,
        columns="Formation",
        values="coverage_pct",
    ).fillna(0.0)

    formation_wide.columns = [
        f"formation_pct_{column}" for column in formation_wide.columns
    ]
    formation_wide = formation_wide.reset_index()

    detailed = summary.merge(
        formation_wide,
        on=grid_id_column,
        how="left",
    )

    return summary, detailed


def write_notebook_grid_products(
    grid: gpd.GeoDataFrame,
    summary: pd.DataFrame,
    grid_id_column: str,
    output_gpkg: Path,
    output_grid_parquet: Path,
    output_layer: str,
) -> tuple[int, list[str]]:
    """Create the 100 m majority grid products used by the notebook."""
    keep = [
        grid_id_column,
        "Majority_formation",
        "majority_formation_status",
        "LRT_code",
        "mapping_year",
    ]
    ratio_columns = [
        column
        for column in summary.columns
        if column.startswith("majority_formation_top")
        or column.startswith("majority_formation_status_top")
    ]
    keep.extend(column for column in ratio_columns if column not in keep)

    majority_grid = grid[[grid_id_column, "geometry"]].merge(
        summary[keep],
        on=grid_id_column,
        how="inner",
    )
    majority_grid = gpd.GeoDataFrame(
        majority_grid,
        geometry="geometry",
        crs=grid.crs,
    )

    ids = majority_grid[grid_id_column].astype("string").str.extract(
        r"100mN(-?\d+)E(-?\d+)"
    )
    if ids.isna().any(axis=None):
        bad = majority_grid.loc[
            ids.isna().any(axis=1), grid_id_column
        ].head(5).tolist()
        raise ValueError(
            "Could not derive 100 m coordinates from grid_id. "
            f"Examples: {bad}"
        )

    majority_grid["x_sw"] = pd.to_numeric(ids[1]) * 100
    majority_grid["y_sw"] = pd.to_numeric(ids[0]) * 100

    centroids = gpd.GeoSeries(
        gpd.points_from_xy(
            majority_grid["x_sw"] + 50,
            majority_grid["y_sw"] + 50,
        ),
        crs="EPSG:3035",
    ).to_crs("EPSG:4326")
    majority_grid["lng"] = centroids.x.to_numpy()
    majority_grid["lat"] = centroids.y.to_numpy()

    output_gpkg.parent.mkdir(parents=True, exist_ok=True)
    output_grid_parquet.parent.mkdir(parents=True, exist_ok=True)

    atomic_write_gpkg(
        majority_grid,
        output_gpkg,
        layer=output_layer,
    )

    parquet_columns = [
        grid_id_column,
        "Majority_formation",
        "majority_formation_status",
        "LRT_code",
        "mapping_year",
        "x_sw",
        "y_sw",
        "lng",
        "lat",
    ]
    parquet_columns.extend(
        column
        for column in ratio_columns
        if column in majority_grid.columns and column not in parquet_columns
    )
    atomic_write_parquet(
        majority_grid.drop(columns="geometry")[parquet_columns],
        output_grid_parquet,
    )

    return len(majority_grid), parquet_columns


def write_susi_compatible_100m_products(
    intersections: pd.DataFrame,
    grid_id_column: str,
    cell_area_m2: float,
    output_dir: Path,
    write_intersections_csv: bool,
) -> dict[str, Any]:
    """Write Susi-compatible 100 m matrix products into processed output.

    Susi's notebook stores cell coverage in centi-percent integer units:
    a fully covered 100 m cell is represented as 10000.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ix = intersections.copy()
    ix["pct_of_cell"] = (
        ix["intersection_area_m2"] / cell_area_m2 * 100.0
    )
    ix = ix.rename(columns={grid_id_column: "grid_id"})

    if write_intersections_csv:
        atomic_write_csv(ix, output_dir / "ix.csv")

    x_lrt = (
        ix.groupby(["grid_id", "LRT_code", "conservation_status"])[
            "pct_of_cell"
        ]
        .sum()
        .unstack(["LRT_code", "conservation_status"])
        .fillna(0)
    )
    x_lrt.columns = [f"{code}_{status}" for code, status in x_lrt.columns]
    x_lrt = (x_lrt * 100).round().clip(0, 65535).astype(np.uint16)

    lrt_status_cols = list(x_lrt.columns)
    lrt_codes = sorted({column.rsplit("_", 1)[0] for column in lrt_status_cols})
    if lrt_codes:
        lrt_presence = pd.DataFrame(
            {
                code: x_lrt[
                    [
                        column
                        for column in lrt_status_cols
                        if column.rsplit("_", 1)[0] == code
                    ]
                ]
                .gt(0)
                .any(axis=1)
                for code in lrt_codes
            },
            index=x_lrt.index,
        )
        x_lrt["n_lrts"] = lrt_presence.sum(axis=1).astype(np.uint16)
        del lrt_presence
    else:
        x_lrt["n_lrts"] = np.uint16(0)

    x_fs = (
        ix.groupby(["grid_id", "Formation", "conservation_status"])[
            "pct_of_cell"
        ]
        .sum()
        .unstack(["Formation", "conservation_status"])
        .fillna(0)
    )
    x_fs.columns = [
        f"{formation}_{status}" for formation, status in x_fs.columns
    ]
    x_fs = (x_fs * 100).round().clip(0, 65535).astype(np.uint16)

    formations = sorted({column.rsplit("_", 1)[0] for column in x_fs.columns})
    for formation in formations:
        columns = [
            column
            for column in x_fs.columns
            if column.startswith(f"{formation}_")
        ]
        x_fs[formation] = (
            x_fs[columns].sum(axis=1).clip(0, 65535).astype(np.uint16)
        )

    # Keep A/B/C/K shares for formations. Formation totals therefore include K,
    # while the majority status below deliberately considers A/B/C only.
    x_fs = x_fs[sorted(x_fs.columns)]
    if "Permanent Glaciers_C" not in x_fs.columns:
        x_fs["Permanent Glaciers_C"] = np.uint16(0)

    formation_cols = [
        column
        for column in x_fs.columns
        if "_" not in column
        and column
        not in ["Majority_formation", "majority_formation_status"]
    ]
    nonzero_formation = x_fs[formation_cols].gt(0).any(axis=1)
    x_fs = x_fs.loc[nonzero_formation].copy()
    x_lrt = x_lrt.loc[x_lrt.index.intersection(x_fs.index)].copy()

    x_fs["n_formations"] = (
        x_fs[formation_cols].gt(0).sum(axis=1).astype(np.uint16)
    )
    x_fs["Majority_formation"] = x_fs[formation_cols].idxmax(axis=1)

    values = x_fs[formation_cols].to_numpy(dtype=np.float64)
    if values.shape[1] >= 2:
        top2 = np.partition(values, -2, axis=1)[:, -2:]
        majority_value = top2.max(axis=1)
        second_value = top2.min(axis=1)
    else:
        majority_value = values[:, 0]
        second_value = np.zeros(len(x_fs), dtype=np.float64)

    majority_delta = majority_value - second_value
    x_fs["majority_value"] = (
        np.rint(majority_value).clip(0, 65535).astype(np.uint16)
    )
    x_fs["second_value"] = (
        np.rint(second_value).clip(0, 65535).astype(np.uint16)
    )
    x_fs["majority_delta"] = (
        np.rint(majority_delta).clip(0, 65535).astype(np.uint16)
    )
    x_fs["majority_disputed"] = x_fs["majority_delta"] <= 200

    abc_cols = [
        column for column in x_fs.columns if column.endswith(("_A", "_B", "_C"))
    ]
    long = x_fs[abc_cols].stack().rename("value").reset_index()
    status_column = long.columns[1]
    split = long[status_column].astype(str).str.rsplit("_", n=1, expand=True)
    long["formation"] = split[0]
    long["status"] = split[1]
    long["Majority_formation"] = x_fs.loc[
        long["grid_id"], "Majority_formation"
    ].values
    long = long[long["formation"] == long["Majority_formation"]]

    maj_status = (
        long[long["value"] > 0]
        .sort_values(["grid_id", "value", "status"], ascending=[True, False, True])
        .drop_duplicates("grid_id")
        .set_index("grid_id")["status"]
    )
    x_fs["majority_formation_status"] = maj_status

    x = x_fs.reset_index().merge(
        x_lrt.reset_index(),
        on="grid_id",
        how="inner",
    )
    x_fs_out = x_fs.reset_index()

    with_lrt_csv = output_dir / "Formation_Status_Grid_withLRTCode.csv"
    with_lrt_parquet = output_dir / "Formation_Status_Grid_withLRTCode.parquet"
    formation_csv = output_dir / "Formation_Status_Grid.csv"

    atomic_write_csv(x, with_lrt_csv)
    atomic_write_parquet(
        x,
        with_lrt_parquet,
    )
    atomic_write_csv(x_fs_out, formation_csv)

    return {
        "rows": int(len(x)),
        "columns_with_lrt": list(x.columns),
        "output_dir": str(output_dir),
        "with_lrt_csv": str(with_lrt_csv),
        "with_lrt_parquet": str(with_lrt_parquet),
        "formation_csv": str(formation_csv),
        "ix_csv": str(output_dir / "ix.csv") if write_intersections_csv else None,
    }


def write_state(
    state_file: Path,
    expected_state: dict[str, Any],
    output_rows: int,
) -> None:
    state = {
        **expected_state,
        "result": {"output_rows": output_rows},
    }
    atomic_write_json(state_file, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 2_1: merge cleaned LRTs and 100 m grid."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        settings = config["lrt_grid_merge"]

        grid_gpkg = Path(settings["grid_gpkg"])
        grid_layer = settings.get("grid_layer", "grid")
        grid_id_column = settings.get("grid_id_column", "grid_id")

        lrt_gpkg = Path(settings["lrt_gpkg"])
        lrt_layer = settings.get("lrt_layer", "lrt")

        output_csv = Path(settings["output_csv"])
        output_parquet = (
            Path(settings["output_parquet"])
            if settings.get("output_parquet")
            else None
        )

        output_grid_gpkg = Path(
            settings.get(
                "output_grid_gpkg",
                output_csv.parent / "majority_formation_grid.gpkg",
            )
        )
        output_grid_parquet = Path(
            settings.get(
                "output_grid_parquet",
                output_csv.parent / "majority_formation_grid.parquet",
            )
        )
        output_grid_layer = settings.get(
            "output_grid_layer",
            "majority_formation_100m",
        )

        output_paths = [
            output_csv,
            output_grid_gpkg,
            output_grid_parquet,
        ]
        if output_parquet is not None:
            output_paths.append(output_parquet)

        susi_settings = settings.get("susi_compatible_outputs", {})
        susi_enabled = bool(susi_settings.get("enabled", False))
        susi_output_dir = Path(
            susi_settings.get(
                "output_dir",
                output_csv.parent / "susi_compatible",
            )
        )
        susi_write_ix = bool(
            susi_settings.get("write_intersections_csv", False)
        )
        if susi_enabled:
            output_paths.extend(
                [
                    susi_output_dir / "Formation_Status_Grid_withLRTCode.csv",
                    susi_output_dir
                    / "Formation_Status_Grid_withLRTCode.parquet",
                    susi_output_dir / "Formation_Status_Grid.csv",
                ]
            )
            if susi_write_ix:
                output_paths.append(susi_output_dir / "ix.csv")

        chunk_size = int(settings.get("chunk_size", 100_000))
        raw_checkpoint_dir = settings.get("chunk_checkpoint_dir")
        chunk_checkpoint_root = (
            Path(raw_checkpoint_dir)
            if raw_checkpoint_dir
            else output_csv.parent / "_chunk_checkpoints"
        )
        cell_area_m2 = float(settings.get("cell_area_m2", 10_000))
        disputed_threshold_pct = float(
            settings.get("disputed_threshold_pct", 2.0)
        )

        allocated_cpus = int(
            os.environ.get("SLURM_CPUS_PER_TASK", "1")
        )
        configured_processes = int(
            settings.get("processes", allocated_cpus)
        )
        processes = max(
            1,
            min(configured_processes, allocated_cpus),
        )
        raw_maxtasks = settings.get("maxtasksperchild")
        maxtasksperchild = (
            int(raw_maxtasks)
            if raw_maxtasks is not None
            else None
        )

        if "SLURM_JOB_ID" not in os.environ and configured_processes > 1:
            print(
                "WARNING: outside Slurm; Step 2_1 is restricted "
                "to one process.",
                file=sys.stderr,
            )

        status_dir = Path(config["status_dir"])
        state_file = Path(
            settings.get(
                "state_file",
                status_dir / "step_2_1_lrt_grid_merge_state.json",
            )
        )

        input_state = {
            "grid_gpkg": file_fingerprint(grid_gpkg),
            "lrt_gpkg": file_fingerprint(lrt_gpkg),
        }
        checkpoint_payload = {
            "inputs": input_state,
            "grid_layer": grid_layer,
            "grid_id_column": grid_id_column,
            "lrt_layer": lrt_layer,
            "chunk_size": chunk_size,
        }
        checkpoint_namespace = hashlib.sha256(
            json.dumps(
                checkpoint_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        chunk_checkpoint_dir = chunk_checkpoint_root / checkpoint_namespace

        expected_state = {
            "inputs": input_state,
            "processing": {
                "grid_layer": grid_layer,
                "grid_id_column": grid_id_column,
                "lrt_layer": lrt_layer,
                "chunk_size": chunk_size,
                "chunk_checkpoint_root": str(chunk_checkpoint_root.resolve()),
                "chunk_checkpoint_namespace": checkpoint_namespace,
                "chunk_checkpoint_dir": str(chunk_checkpoint_dir.resolve()),
                "cell_area_m2": cell_area_m2,
                "disputed_threshold_pct": disputed_threshold_pct,
                "output_csv": str(output_csv.resolve()),
                "output_parquet": (
                    str(output_parquet.resolve())
                    if output_parquet is not None
                    else None
                ),
                "output_grid_gpkg": str(output_grid_gpkg.resolve()),
                "output_grid_parquet": str(output_grid_parquet.resolve()),
                "output_grid_layer": output_grid_layer,
                "susi_matrix_schema_version": SUSI_MATRIX_SCHEMA_VERSION,
                "susi_compatible_outputs": {
                    "enabled": susi_enabled,
                    "output_dir": str(susi_output_dir.resolve()),
                    "write_intersections_csv": susi_write_ix,
                },
            },
        }

        if should_skip(
            output_paths,
            state_file,
            expected_state,
            args.force,
        ):
            print(
                "Step 2_1 skipped: outputs exist and inputs are unchanged."
            )
            for path in output_paths:
                print(f"Output: {path}")
            return 0

        grid, lrt = read_inputs(
            grid_gpkg=grid_gpkg,
            grid_layer=grid_layer,
            lrt_gpkg=lrt_gpkg,
            lrt_layer=lrt_layer,
            grid_id_column=grid_id_column,
        )

        print(f"Grid cells : {len(grid):,}")
        print(f"LRT rows   : {len(lrt):,}")
        print(f"Chunk size : {chunk_size:,}")
        print(f"Processes  : {processes}")

        intersections = intersect_in_chunks(
            grid=grid,
            lrt=lrt,
            grid_id_column=grid_id_column,
            chunk_size=chunk_size,
            processes=processes,
            maxtasksperchild=maxtasksperchild,
            checkpoint_dir=chunk_checkpoint_dir,
        )

        summary, detailed = build_summary(
            intersections=intersections,
            grid_id_column=grid_id_column,
            cell_area_m2=cell_area_m2,
            disputed_threshold_pct=disputed_threshold_pct,
        )

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(summary, output_csv)

        if output_parquet is not None:
            atomic_write_parquet(
                detailed,
                output_parquet,
            )

        grid_rows, grid_columns = write_notebook_grid_products(
            grid=grid,
            summary=summary,
            grid_id_column=grid_id_column,
            output_gpkg=output_grid_gpkg,
            output_grid_parquet=output_grid_parquet,
            output_layer=output_grid_layer,
        )

        susi_result = None
        if susi_enabled:
            susi_result = write_susi_compatible_100m_products(
                intersections=intersections,
                grid_id_column=grid_id_column,
                cell_area_m2=cell_area_m2,
                output_dir=susi_output_dir,
                write_intersections_csv=susi_write_ix,
            )

        write_state(state_file, expected_state, len(summary))

        print("\nStep 2_1 completed.")
        print(f"Output rows : {len(summary):,}")
        print(f"Summary CSV : {output_csv}")
        if output_parquet is not None:
            print(f"Detailed    : {output_parquet}")
        print(f"Grid GPKG   : {output_grid_gpkg}")
        print(f"Grid Parquet: {output_grid_parquet}")
        print(f"Grid rows   : {grid_rows:,}")
        print(f"Grid columns: {', '.join(grid_columns)}")
        if susi_result is not None:
            print(f"Susi 100m   : {susi_result['output_dir']}")
            print(f"Susi rows   : {susi_result['rows']:,}")
        print(f"State file  : {state_file}")
        return 0

    except Exception as exc:
        print(f"ERROR in Step 2_1: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())

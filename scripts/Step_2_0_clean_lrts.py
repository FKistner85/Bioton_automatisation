#!/usr/bin/env python3
"""Step 2_0: Clean and consolidate German LRT polygons."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.ops import unary_union
from shapely.validation import make_valid
from tqdm import tqdm

from common import atomic_write_json


STATUS_RANK = {"A": 4, "B": 3, "C": 2, "K": 1}
FORMATION_DEFINITION_VERSION = "table_2026_08_03_coastal_v2"

COLUMN_ALIASES = {
    "mapping_year": {
        "mapping_year", "Mapping_year", "MAPPING_YEAR",
        "mappingyear", "MappingYear",
    },
    "LRT_code": {
        "LRT_code", "LRT_Code", "lrt_code", "LRTCODE", "lrtcode",
    },
    "conservation_status": {
        "conservation_status", "Conservation_status",
        "CONSERVATION_STATUS", "conservationstatus",
        "ConservationStatus",
    },
}


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    section = config.get("lrt_cleaning")
    if not isinstance(section, dict):
        raise KeyError("Missing 'lrt_cleaning' section in config.json.")

    required = ["source_gpkgs", "output_gpkg"]
    missing = [key for key in required if not section.get(key)]
    if missing:
        raise KeyError(
            "Missing required lrt_cleaning key(s): " + ", ".join(missing)
        )

    if not isinstance(section["source_gpkgs"], list) or not section["source_gpkgs"]:
        raise ValueError("'lrt_cleaning.source_gpkgs' must be a non-empty list.")

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
    output_gpkg: Path,
    state_file: Path,
    expected_state: dict[str, Any],
    force: bool,
) -> bool:
    if force or not output_gpkg.is_file() or not state_file.is_file():
        return False

    try:
        with state_file.open("r", encoding="utf-8") as file:
            previous = json.load(file)
    except (OSError, json.JSONDecodeError):
        return False

    return normalise_state(previous) == expected_state


def find_column(columns: list[str], canonical: str) -> str | None:
    aliases = COLUMN_ALIASES[canonical]
    return next((column for column in columns if column in aliases), None)


def harmonise_columns(
    gdf: gpd.GeoDataFrame,
    source: str,
) -> gpd.GeoDataFrame:
    rename_map: dict[str, str] = {}

    for canonical in COLUMN_ALIASES:
        found = find_column(list(gdf.columns), canonical)
        if found is None:
            raise ValueError(
                f"Required column '{canonical}' not found in {source}. "
                f"Available columns: {list(gdf.columns)}"
            )
        rename_map[found] = canonical

    gdf = gdf.rename(columns=rename_map)
    return gdf[
        ["mapping_year", "LRT_code", "conservation_status", "geometry"]
    ].copy()


def repair_polygons(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.apply(make_valid)
    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
        & gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
    ].copy()
    return gdf[gdf.is_valid].copy()


def read_all_lrt_layers(
    gpkg_path: Path,
    target_crs: int,
) -> gpd.GeoDataFrame:
    layers = pyogrio.list_layers(gpkg_path)[:, 0].tolist()

    if not layers:
        raise ValueError(f"No layers found in {gpkg_path}")

    print(f"\nLayers in {gpkg_path}:")
    prepared: list[gpd.GeoDataFrame] = []

    for layer_name in layers:
        print(f"  checking: {layer_name}")
        layer = gpd.read_file(gpkg_path, layer=layer_name, engine="pyogrio")

        if layer.empty:
            print("    skipped: empty layer")
            continue

        try:
            layer = harmonise_columns(
                layer,
                source=f"{gpkg_path.name}:{layer_name}",
            )
        except ValueError as exc:
            print(f"    skipped: {exc}")
            continue

        if layer.crs is None:
            raise ValueError(
                f"Layer has no CRS: {gpkg_path.name}:{layer_name}"
            )

        layer = layer.to_crs(target_crs)
        layer = repair_polygons(layer)

        if layer.empty:
            print("    skipped: no usable polygon geometries")
            continue

        layer["source_gpkg"] = gpkg_path.name
        layer["source_layer"] = layer_name
        prepared.append(layer)
        print(f"    loaded: {len(layer):,} polygon features")

    if not prepared:
        raise ValueError(f"No usable LRT layers found in {gpkg_path}")

    return gpd.GeoDataFrame(
        pd.concat(prepared, ignore_index=True),
        geometry="geometry",
        crs=f"EPSG:{target_crs}",
    )


def norm_lrt_code(series: pd.Series) -> pd.Series:
    series = series.astype("string").str.strip()
    series = series.where(
        ~series.str.lower().isin(["nan", "<na>", "none", ""]),
        pd.NA,
    )
    series = series.str.replace(r"\s+", "", regex=True)
    numeric = series.str.match(r"^\d+(\.0+)?$", na=False)
    series.loc[numeric] = (
        pd.to_numeric(series.loc[numeric], errors="coerce")
        .astype("Int64")
        .astype("string")
    )
    return series


def lrt_formation(code: object) -> str:
    code = str(code)

    if code.startswith("1340") or code.startswith("7"):
        return "Bogs"
    if code.startswith("8340"):
        return "Permanent Glaciers"
    if code.startswith("2180") or code.startswith("9"):
        return "Forests"
    if code.startswith(("2310", "2320", "4", "5")):
        return "Temperate heath"
    if code.startswith("2330") or code.startswith("6"):
        return "Grassland"
    if code.startswith("3"):
        return "Freshwater"
    if code.startswith("8"):
        return "Rocky habitats"
    if code.startswith(("1", "2")):
        return "Coastal"
    return "Other"


def resolve_within_formation(
    df_form: gpd.GeoDataFrame,
    eps_area: float,
) -> gpd.GeoDataFrame:
    df = (
        df_form.sort_values(
            ["mapping_year_num", "status_rank", "src_id"],
            ascending=[False, False, True],
            na_position="last",
        )
        .reset_index(drop=True)
        .copy()
    )

    df = repair_polygons(df).reset_index(drop=True)
    spatial_index = df.sindex
    output_geometries: list[object | None] = [None] * len(df)

    for index in range(len(df) - 1, -1, -1):
        geometry = df.geometry.iat[index]
        candidate_positions = [
            pos
            for pos in spatial_index.intersection(geometry.bounds)
            if pos < index
        ]

        higher_priority = []
        for position in candidate_positions:
            candidate = df.geometry.iat[position]
            try:
                if (
                    candidate.intersects(geometry)
                    and candidate.intersection(geometry).area > eps_area
                ):
                    higher_priority.append(candidate)
            except Exception as exc:
                print(
                    f"Intersection warning at row {index}, "
                    f"candidate {position}: {exc}"
                )

        if higher_priority:
            try:
                geometry = geometry.difference(
                    unary_union(higher_priority)
                )
            except Exception as exc:
                print(f"Difference warning at row {index}: {exc}")

        if (
            geometry is not None
            and not geometry.is_empty
            and geometry.area > eps_area
        ):
            output_geometries[index] = geometry

    df["geometry"] = output_geometries
    df = df[df.geometry.notna()].copy()
    return gpd.GeoDataFrame(df, geometry="geometry", crs=df_form.crs)


def process_group(
    task: tuple[str, gpd.GeoDataFrame, float],
) -> gpd.GeoDataFrame | None:
    name, group, eps_area = task
    try:
        return resolve_within_formation(group, eps_area)
    except Exception as exc:
        print(f"Formation '{name}' failed: {exc}")
        return None


def resolve_all_formations(
    gdf: gpd.GeoDataFrame,
    eps_area: float,
    processes: int,
    maxtasksperchild: int | None,
) -> gpd.GeoDataFrame:
    tasks = [
        (str(name), group.copy(), eps_area)
        for name, group in gdf.groupby("Formation", dropna=False)
    ]

    workers = max(
        1,
        min(processes, len(tasks), os.cpu_count() or 1),
    )

    print(f"\nFormation groups: {len(tasks)}")
    print(f"Worker processes: {workers}")

    if workers == 1:
        results = [
            process_group(task)
            for task in tqdm(tasks, total=len(tasks))
        ]
    else:
        context = (
            mp.get_context("fork")
            if "fork" in mp.get_all_start_methods()
            else mp.get_context()
        )
        with context.Pool(
            processes=workers,
            maxtasksperchild=maxtasksperchild,
        ) as pool:
            results = list(
                tqdm(
                    pool.imap_unordered(
                        process_group,
                        tasks,
                        chunksize=1,
                    ),
                    total=len(tasks),
                )
            )

    results = [result for result in results if result is not None]
    if not results:
        raise RuntimeError("No formation group was processed successfully.")

    return gpd.GeoDataFrame(
        pd.concat(results, ignore_index=True),
        geometry="geometry",
        crs=gdf.crs,
    )


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
        description="Step 2_0: clean and consolidate LRT polygons."
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
        settings = config["lrt_cleaning"]

        source_gpkgs = [Path(path) for path in settings["source_gpkgs"]]
        output_gpkg = Path(settings["output_gpkg"])
        output_layer = settings.get("output_layer", "lrt")
        target_crs = int(settings.get("target_crs", 3035))
        eps_area = float(settings.get("eps_area", 1.0))
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
                "WARNING: outside Slurm; Step 2_0 is restricted "
                "to one process.",
                file=sys.stderr,
            )

        status_dir = Path(config["status_dir"])
        state_file = Path(
            settings.get(
                "state_file",
                status_dir / "step_2_0_clean_lrts_state.json",
            )
        )

        expected_state = {
            "inputs": {
                str(path): file_fingerprint(path)
                for path in source_gpkgs
            },
            "processing": {
                "output_gpkg": str(output_gpkg.resolve()),
                "output_layer": output_layer,
                "target_crs": target_crs,
                "eps_area": eps_area,
                "formation_definition": FORMATION_DEFINITION_VERSION,
            },
        }

        if should_skip(
            output_gpkg,
            state_file,
            expected_state,
            args.force,
        ):
            print("Step 2_0 skipped: output exists and inputs are unchanged.")
            print(f"Output: {output_gpkg}")
            return 0

        all_sources = [
            read_all_lrt_layers(path, target_crs)
            for path in source_gpkgs
        ]

        lrt = gpd.GeoDataFrame(
            pd.concat(all_sources, ignore_index=True),
            geometry="geometry",
            crs=f"EPSG:{target_crs}",
        )

        print(f"\nRows before duplicate removal: {len(lrt):,}")
        lrt = lrt.drop_duplicates(
            subset=[
                "mapping_year",
                "LRT_code",
                "conservation_status",
                "geometry",
            ]
        ).copy()
        print(f"Rows after duplicate removal : {len(lrt):,}")

        lrt["LRT_code"] = norm_lrt_code(lrt["LRT_code"])
        lrt["Formation"] = lrt["LRT_code"].apply(lrt_formation)
        lrt = repair_polygons(lrt)
        lrt = lrt.explode(ignore_index=True)
        lrt = repair_polygons(lrt)

        lrt["src_id"] = np.arange(len(lrt))
        lrt["status_rank"] = (
            lrt["conservation_status"]
            .map(STATUS_RANK)
            .fillna(0)
            .astype(int)
        )
        lrt["mapping_year_num"] = pd.to_numeric(
            lrt["mapping_year"],
            errors="coerce",
        ).astype("Int64")

        output = resolve_all_formations(
            lrt,
            eps_area=eps_area,
            processes=processes,
            maxtasksperchild=maxtasksperchild,
        )

        output_gpkg.parent.mkdir(parents=True, exist_ok=True)
        temporary_gpkg = output_gpkg.with_name(
            f"{output_gpkg.stem}.part{output_gpkg.suffix}"
        )
        temporary_gpkg.unlink(missing_ok=True)
        output.to_file(
            temporary_gpkg,
            layer=output_layer,
            driver="GPKG",
            engine="pyogrio",
        )
        written_rows = int(
            pyogrio.read_info(
                temporary_gpkg,
                layer=output_layer,
            )["features"]
        )
        if written_rows != len(output):
            raise RuntimeError(
                f"Atomic GPKG validation failed: expected {len(output)} rows, "
                f"found {written_rows}."
            )
        temporary_gpkg.replace(output_gpkg)

        write_state(state_file, expected_state, len(output))

        print("\nStep 2_0 completed.")
        print(f"Output rows: {len(output):,}")
        print(f"Output     : {output_gpkg}")
        print(f"Processes  : {processes}")
        print(f"State file : {state_file}")
        return 0

    except Exception as exc:
        print(f"ERROR in Step 2_0: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())

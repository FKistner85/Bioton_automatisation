#!/usr/bin/env python3
"""Step 2_4: Generate Susi-compatible 10 m LRT/formation products."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import box
from tqdm import tqdm

from common import (
    finish_step_manifest,
    start_step_manifest,
    utc_now_iso,
    workflow_run_id,
    write_batch_status,
)

_WORKER_LRT: gpd.GeoDataFrame | None = None
_WORKER_SETTINGS: dict[str, Any] | None = None
SUSI_10M_MATRIX_SCHEMA_VERSION = "2026-08-03-centi-percent-abck-coastal-v3"
TEN_M_CELL_AREA_M2 = 100.0


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "susi_10m_products" not in config:
        raise KeyError("Missing 'susi_10m_products' section in config.")
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


def read_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def reset_outputs_for_new_inputs(settings: dict[str, Any], final_parquet: Path) -> None:
    output_dir = Path(settings["output_dir"])
    dirs = [
        Path(settings.get("grid_chunk_dir", output_dir / "grid10m_chunks")),
        Path(settings.get("ix_chunk_dir", output_dir / "ix_chunks")),
        Path(settings.get("parquet_chunk_dir", output_dir / "parquet_10")),
    ]
    for directory in dirs:
        if directory.exists():
            shutil.rmtree(directory)
    final_parquet.unlink(missing_ok=True)


def parse_100m_grid_id(grid_id: str) -> tuple[int, int]:
    match = re.fullmatch(r"100mN(-?\d+)E(-?\d+)", str(grid_id))
    if match is None:
        raise ValueError(f"Invalid 100 m grid_id: {grid_id}")
    north_100 = int(match.group(1))
    east_100 = int(match.group(2))
    return north_100, east_100


def make_10m_cells(grid_id: str) -> list[dict[str, Any]]:
    north_100, east_100 = parse_100m_grid_id(grid_id)
    x0 = east_100 * 100
    y0 = north_100 * 100
    cells = []
    for dy in range(10):
        for dx in range(10):
            minx = x0 + dx * 10
            miny = y0 + dy * 10
            east_10 = east_100 * 10 + dx
            north_10 = north_100 * 10 + dy
            cells.append(
                {
                    "grid_id_10": f"10mN{north_10}E{east_10}",
                    "grid_id_100": grid_id,
                    "geometry": box(minx, miny, minx + 10, miny + 10),
                }
            )
    return cells


def build_10m_grid(grid_ids: list[str]) -> gpd.GeoDataFrame:
    cells = [cell for grid_id in grid_ids for cell in make_10m_cells(grid_id)]
    return gpd.GeoDataFrame(cells, geometry="geometry", crs="EPSG:3035")


def build_susi_matrix(ix: pd.DataFrame) -> pd.DataFrame:
    x_lrt = (
        ix.groupby(["grid_id_10", "LRT_code", "conservation_status"])[
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
        ix.groupby(["grid_id_10", "Formation", "conservation_status"])[
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
        long["grid_id_10"], "Majority_formation"
    ].values
    long = long[long["formation"] == long["Majority_formation"]]

    maj_status = (
        long[long["value"] > 0]
        .sort_values(
            ["grid_id_10", "value", "status"],
            ascending=[True, False, True],
        )
        .drop_duplicates("grid_id_10")
        .set_index("grid_id_10")["status"]
    )
    x_fs["majority_formation_status"] = maj_status

    return x_fs.reset_index().merge(
        x_lrt.reset_index(),
        on="grid_id_10",
        how="inner",
    )


def reference_schema_from_100m(source_parquet: Path) -> pa.Schema:
    schema = pq.read_schema(source_parquet)
    return pa.schema(
        [
            ("grid_id_10" if field.name == "grid_id" else field.name, field.type)
            for field in schema
        ]
    )


def merge_parquet_parts(
    parts: list[Path],
    output: Path,
    reference_schema: pa.Schema,
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.stem}.part{output.suffix}")
    temporary.unlink(missing_ok=True)

    effective_schema = schema_with_part_extras(reference_schema, parts)
    writer: pq.ParquetWriter | None = None
    total_rows = 0
    try:
        for part in parts:
            table = pq.read_table(part)
            table = align_table_to_schema(table, effective_schema)
            if writer is None:
                writer = pq.ParquetWriter(
                    temporary,
                    effective_schema,
                    compression="zstd",
                    use_dictionary=True,
                )
            writer.write_table(table)
            total_rows += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError(f"Temporary final parquet is empty: {temporary}")
    temporary.replace(output)
    return total_rows


def schema_with_part_extras(reference_schema: pa.Schema, parts: list[Path]) -> pa.Schema:
    fields = list(reference_schema)
    names = {field.name for field in fields}
    for part in parts:
        part_schema = pq.read_schema(part)
        for field in part_schema:
            if field.name not in names:
                fields.append(field)
                names.add(field.name)
    return pa.schema(fields)


def zero_array(length: int, field: pa.Field) -> pa.Array:
    if pa.types.is_boolean(field.type):
        return pa.array([False] * length, type=field.type)
    if pa.types.is_integer(field.type) or pa.types.is_floating(field.type):
        return pa.array([0] * length, type=field.type)
    if pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
        return pa.array(["0"] * length, type=field.type)
    return pa.nulls(length, type=field.type)


def align_table_to_schema(table: pa.Table, schema: pa.Schema) -> pa.Table:
    arrays = []
    for field in schema:
        if field.name in table.column_names:
            column = table[field.name]
            if not column.type.equals(field.type):
                column = column.cast(field.type, safe=False)
            arrays.append(column)
        else:
            arrays.append(zero_array(table.num_rows, field))
    return pa.Table.from_arrays(arrays, schema=schema)


def process_chunk(
    part_no: int,
    grid_ids: list[str],
    lrt: gpd.GeoDataFrame,
    settings: dict[str, Any],
) -> Path:
    output_dir = Path(settings["output_dir"])
    grid_dir = Path(settings.get("grid_chunk_dir", output_dir / "grid10m_chunks"))
    ix_dir = Path(settings.get("ix_chunk_dir", output_dir / "ix_chunks"))
    parquet_dir = Path(settings.get("parquet_chunk_dir", output_dir / "parquet_10"))
    write_grid = bool(settings.get("write_grid_chunks", True))
    write_ix = bool(settings.get("write_ix_chunks", True))
    batch_status_dir = settings.get("_batch_status_dir")
    batch_id = f"part_{part_no:04d}"
    batch_started_utc = utc_now_iso()

    grid_dir.mkdir(parents=True, exist_ok=True)
    ix_dir.mkdir(parents=True, exist_ok=True)
    parquet_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = parquet_dir / f"X_part_{part_no:04d}.parquet"
    if parquet_path.exists() and not bool(settings.get("_force", False)):
        if batch_status_dir:
            write_batch_status(
                batch_status_dir,
                batch_id,
                "skipped",
                outputs=[parquet_path],
                result={"reason": "existing_nonempty_parquet"},
                started_utc=batch_started_utc,
            )
        return parquet_path

    if batch_status_dir:
        write_batch_status(
            batch_status_dir,
            batch_id,
            "running",
            result={"grid_ids": len(grid_ids)},
            started_utc=batch_started_utc,
        )

    try:
        grid10 = build_10m_grid(grid_ids)
        grid_path = grid_dir / f"grid10m_part_{part_no:04d}.gpkg"
        if write_grid:
            if grid_path.exists():
                grid_path.unlink()
            grid10.to_file(
                grid_path,
                layer="grid10m",
                driver="GPKG",
                engine="pyogrio",
            )

        ix = gpd.overlay(grid10, lrt, how="intersection", keep_geom_type=False)
        ix["ix_area"] = ix.geometry.area
        # A 10 m cell covers 100 m2. pct_of_cell is a true percentage here;
        # build_susi_matrix subsequently stores percentage * 100 as uint16.
        ix["pct_of_cell"] = ix["ix_area"] / TEN_M_CELL_AREA_M2 * 100.0

        ix_table = pd.DataFrame(
            ix[
                [
                    "grid_id_10",
                    "grid_id_100",
                    "Formation",
                    "conservation_status",
                    "LRT_code",
                    "ix_area",
                    "pct_of_cell",
                ]
            ]
        )
        ix_path = ix_dir / f"ix_part_{part_no:04d}.csv"
        if write_ix:
            ix_table.to_csv(ix_path, index=False)

        matrix = build_susi_matrix(ix_table)
        temporary = parquet_path.with_suffix(parquet_path.suffix + ".part")
        matrix.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(parquet_path)
        if batch_status_dir:
            write_batch_status(
                batch_status_dir,
                batch_id,
                "complete",
                outputs=[
                    path
                    for path in [grid_path if write_grid else None, ix_path if write_ix else None, parquet_path]
                    if path is not None
                ],
                result={
                    "grid_ids": len(grid_ids),
                    "rows": int(len(matrix)),
                },
                started_utc=batch_started_utc,
            )
        return parquet_path
    except Exception as exc:
        if batch_status_dir:
            write_batch_status(
                batch_status_dir,
                batch_id,
                "failed",
                result={"grid_ids": len(grid_ids)},
                error=repr(exc),
                started_utc=batch_started_utc,
            )
        raise


def init_chunk_worker(lrt: gpd.GeoDataFrame, settings: dict[str, Any]) -> None:
    global _WORKER_LRT, _WORKER_SETTINGS
    _WORKER_LRT = lrt
    _WORKER_SETTINGS = settings


def process_chunk_worker(task: tuple[int, list[str]]) -> tuple[int, Path]:
    if _WORKER_LRT is None or _WORKER_SETTINGS is None:
        raise RuntimeError("Step 2_4 worker was not initialised.")
    part_no, grid_ids = task
    return part_no, process_chunk(part_no, grid_ids, _WORKER_LRT, _WORKER_SETTINGS)


def resolve_process_count(settings: dict[str, Any]) -> int:
    allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", "1") or "1")
    configured = int(settings.get("processes", allocated))
    return max(1, min(configured, allocated))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 2_4: generate Susi-compatible 10 m products."
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
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        settings = dict(config["susi_10m_products"])
        settings["_force"] = False

        source = Path(settings["source_100m_parquet"])
        lrt_gpkg = Path(settings["lrt_gpkg"])
        lrt_layer = settings.get("lrt_layer", "lrt")
        output_dir = Path(settings["output_dir"])
        final_parquet = Path(
            settings.get(
                "final_parquet",
                output_dir / "Formation_Status_10m_Grid_withLRTCode.parquet",
            )
        )
        state_file = Path(settings.get("state_file", output_dir / "state.json"))
        chunk_size = int(settings.get("chunk_size_100m", 1000))
        processes = resolve_process_count(settings)

        if not source.is_file():
            raise FileNotFoundError(f"Missing source parquet: {source}")
        if not lrt_gpkg.is_file():
            raise FileNotFoundError(f"Missing LRT GPKG: {lrt_gpkg}")

        output_dir.mkdir(parents=True, exist_ok=True)
        expected_state = {
            "inputs": {
                "source_100m_parquet": file_fingerprint(source),
                "lrt_gpkg": file_fingerprint(lrt_gpkg),
            },
            "processing": {
                "chunk_size_100m": chunk_size,
                "output_dir": str(output_dir.resolve()),
                "final_parquet": str(final_parquet.resolve()),
                "susi_matrix_schema_version": SUSI_10M_MATRIX_SCHEMA_VERSION,
            },
        }
        previous_state = read_state(state_file)
        same_inputs = (
            previous_state is not None
            and previous_state.get("inputs") == expected_state["inputs"]
            and previous_state.get("processing") == expected_state["processing"]
        )
        resume_full_generation = bool(
            args.force
            and same_inputs
            and previous_state.get("status") == "in_progress"
            and previous_state.get("full_rebuild_requested") is True
        )
        reset_required = (
            not same_inputs
            or (args.force and not resume_full_generation)
        )
        full_rebuild_requested = bool(
            args.force
            or (
                same_inputs
                and previous_state.get("full_rebuild_requested") is True
            )
        )
        generation_started_utc = (
            str(previous_state.get("generation_started_utc", ""))
            if resume_full_generation
            else utc_now_iso()
        )
        if reset_required:
            print(
                "Step 2_4 input or processing state changed/missing; "
                "resetting 10 m chunk outputs."
            )
            reset_outputs_for_new_inputs(settings, final_parquet)
            write_state(
                state_file,
                {
                    **expected_state,
                    "status": "in_progress",
                    "full_rebuild_requested": full_rebuild_requested,
                    "generation_started_utc": generation_started_utc,
                    "generation_workflow_run_id": workflow_run_id(),
                },
            )
        else:
            print(
                "Step 2_4 state unchanged; existing chunk outputs will be reused."
            )

        ids = pd.read_parquet(source, columns=["grid_id"])["grid_id"]
        grid_ids = ids.dropna().astype(str).drop_duplicates().tolist()
        lrt = gpd.read_file(lrt_gpkg, layer=lrt_layer, engine="pyogrio")
        if lrt.crs != "EPSG:3035":
            lrt = lrt.to_crs("EPSG:3035")

        parts: list[Path] = []
        starts = list(range(0, len(grid_ids), chunk_size))
        tasks = [
            (part_no, grid_ids[start : start + chunk_size])
            for part_no, start in enumerate(starts, start=1)
        ]
        settings["_batch_status_dir"] = str(output_dir / "_batch_status")
        manifest_path, manifest = start_step_manifest(
            config,
            "step_2_4_susi_10m_products",
            config_path=args.config,
            inputs=[source, lrt_gpkg],
            outputs=[final_parquet, state_file],
            parameters={
                "chunk_size_100m": chunk_size,
                "processes": processes,
                "force": args.force,
                "schema_version": SUSI_10M_MATRIX_SCHEMA_VERSION,
            },
            force=args.force,
            batch_count=len(tasks),
        )
        started = time.monotonic()
        completed_parts: dict[int, Path] = {}
        print(f"Processes  : {processes}")
        if processes > 1 and "fork" in mp.get_all_start_methods():
            context = mp.get_context("fork")
            with context.Pool(
                processes=processes,
                initializer=init_chunk_worker,
                initargs=(lrt, settings),
                maxtasksperchild=int(settings.get("maxtasksperchild", 20)),
            ) as pool:
                iterator = pool.imap_unordered(process_chunk_worker, tasks)
                for completed, (part_no, part) in enumerate(iterator, start=1):
                    completed_parts[part_no] = part
                    elapsed = time.monotonic() - started
                    rate = completed / elapsed if elapsed > 0 else 0.0
                    eta = (len(tasks) - completed) / rate if rate > 0 else 0.0
                    print(
                        f"Part {part_no:04d}/{len(tasks):04d} done -> {part} "
                        f"ETA {eta / 60:.1f} min"
                    )
        else:
            for completed, (part_no, part_ids) in enumerate(tasks, start=1):
                part = process_chunk(part_no, part_ids, lrt, settings)
                completed_parts[part_no] = part
                elapsed = time.monotonic() - started
                rate = completed / elapsed if elapsed > 0 else 0.0
                eta = (len(tasks) - completed) / rate if rate > 0 else 0.0
                print(
                    f"Part {part_no:04d}/{len(tasks):04d}: "
                    f"{len(part_ids):,} 100m cells -> {part} "
                    f"ETA {eta / 60:.1f} min"
                )

        parts = [completed_parts[index] for index in sorted(completed_parts)]

        total_rows = merge_parquet_parts(
            parts,
            final_parquet,
            reference_schema_from_100m(source),
        )
        write_state(
            state_file,
            {
                **expected_state,
                "status": "complete",
                "full_rebuild_requested": full_rebuild_requested,
                "generation_started_utc": generation_started_utc,
                "generation_finished_utc": utc_now_iso(),
                "generation_workflow_run_id": workflow_run_id(),
                "result": {
                    "parts": len(parts),
                    "total_rows": int(total_rows),
                },
            },
        )
        print("\nStep 2_4 completed.")
        print(f"100m cells : {len(grid_ids):,}")
        print(f"Parts      : {len(parts):,}")
        print(f"Processes  : {processes}")
        print(f"10m rows   : {total_rows:,}")
        print(f"Output     : {final_parquet}")
        print(f"State file : {state_file}")
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "complete",
                result={
                    "100m_cells": int(len(grid_ids)),
                    "parts": int(len(parts)),
                    "total_rows": int(total_rows),
                },
            )
        return 0
    except Exception as exc:
        print(f"ERROR in Step 2_4: {exc}", file=sys.stderr)
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "failed",
                error=repr(exc),
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

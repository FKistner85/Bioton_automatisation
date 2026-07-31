#!/usr/bin/env python3
"""Step 2_6: Build Susi-compatible public 100 m LRT grid products."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from Step_2_1_merge_lrts_and_grid import (  # noqa: E402
    SUSI_MATRIX_SCHEMA_VERSION,
    build_summary,
    file_fingerprint,
    intersect_in_chunks,
    read_inputs,
    should_skip,
    write_susi_compatible_100m_products,
    write_state,
)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "public_lrt_grid_merge" not in config:
        raise KeyError("Missing public_lrt_grid_merge section in config.")
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge public LRT polygons and public 100 m grid."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        settings = config["public_lrt_grid_merge"]
        grid_gpkg = Path(settings["grid_gpkg"])
        grid_layer = settings.get("grid_layer", "grid")
        grid_id_column = settings.get("grid_id_column", "grid_id")
        lrt_gpkg = Path(settings["lrt_gpkg"])
        lrt_layer = settings.get("lrt_layer", "lrt")
        output_dir = Path(settings["output_dir"])
        state_file = Path(settings.get("state_file", output_dir / "state.json"))
        raw_checkpoint_dir = settings.get("chunk_checkpoint_dir")
        chunk_checkpoint_dir = (
            Path(raw_checkpoint_dir)
            if raw_checkpoint_dir
            else output_dir / "_chunk_checkpoints"
        )
        chunk_size = int(settings.get("chunk_size", 500_000))
        cell_area_m2 = float(settings.get("cell_area_m2", 10_000))
        disputed_threshold_pct = float(
            settings.get("disputed_threshold_pct", 2.0)
        )
        write_ix = bool(settings.get("write_intersections_csv", True))

        output_paths = [
            output_dir / "ix.csv",
            output_dir / "Formation_Status_Grid_withLRTCode.csv",
            output_dir / "Formation_Status_Grid_withLRTCode.parquet",
            output_dir / "Formation_Status_Grid.csv",
            output_dir / "Formation_Status_Grid_public.csv",
            output_dir / "Formation_Status_Grid_public_withLRTCode.csv",
            output_dir / "Formation_Status_Grid_public_withLRTCode.parquet",
        ]
        if not write_ix:
            output_paths = [path for path in output_paths if path.name != "ix.csv"]

        allocated_cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
        configured_processes = int(settings.get("processes", allocated_cpus))
        processes = max(1, min(configured_processes, allocated_cpus))
        maxtasksperchild = settings.get("maxtasksperchild")
        if maxtasksperchild is not None:
            maxtasksperchild = int(maxtasksperchild)

        expected_state = {
            "inputs": {
                "grid_gpkg": file_fingerprint(grid_gpkg),
                "lrt_gpkg": file_fingerprint(lrt_gpkg),
            },
            "processing": {
                "grid_layer": grid_layer,
                "grid_id_column": grid_id_column,
                "lrt_layer": lrt_layer,
                "chunk_size": chunk_size,
                "chunk_checkpoint_dir": str(chunk_checkpoint_dir.resolve()),
                "cell_area_m2": cell_area_m2,
                "disputed_threshold_pct": disputed_threshold_pct,
                "output_dir": str(output_dir.resolve()),
                "write_intersections_csv": write_ix,
                "susi_matrix_schema_version": SUSI_MATRIX_SCHEMA_VERSION,
            },
        }

        if should_skip(
            output_paths,
            state_file,
            expected_state,
            args.force,
        ):
            print("Step 2_6 skipped: outputs exist and inputs are unchanged.")
            print(f"Output dir: {output_dir}")
            return 0

        grid, lrt = read_inputs(
            grid_gpkg=grid_gpkg,
            grid_layer=grid_layer,
            lrt_gpkg=lrt_gpkg,
            lrt_layer=lrt_layer,
            grid_id_column=grid_id_column,
        )
        print(f"Public grid cells: {len(grid):,}")
        print(f"Public LRT rows  : {len(lrt):,}")
        print(f"Chunk size       : {chunk_size:,}")
        print(f"Processes        : {processes}")

        intersections = intersect_in_chunks(
            grid=grid,
            lrt=lrt,
            grid_id_column=grid_id_column,
            chunk_size=chunk_size,
            processes=processes,
            maxtasksperchild=maxtasksperchild,
            checkpoint_dir=chunk_checkpoint_dir,
        )
        summary, _ = build_summary(
            intersections=intersections,
            grid_id_column=grid_id_column,
            cell_area_m2=cell_area_m2,
            disputed_threshold_pct=disputed_threshold_pct,
        )
        result = write_susi_compatible_100m_products(
            intersections=intersections,
            grid_id_column=grid_id_column,
            cell_area_m2=cell_area_m2,
            output_dir=output_dir,
            write_intersections_csv=write_ix,
        )

        shutil.copyfile(
            output_dir / "Formation_Status_Grid.csv",
            output_dir / "Formation_Status_Grid_public.csv",
        )
        shutil.copyfile(
            output_dir / "Formation_Status_Grid_withLRTCode.csv",
            output_dir / "Formation_Status_Grid_public_withLRTCode.csv",
        )
        shutil.copyfile(
            output_dir / "Formation_Status_Grid_withLRTCode.parquet",
            output_dir / "Formation_Status_Grid_public_withLRTCode.parquet",
        )
        summary.to_csv(output_dir / "public_majority_summary.csv", index=False)
        write_state(state_file, expected_state, int(result["rows"]))

        print("Step 2_6 completed.")
        print(f"Output dir : {output_dir}")
        print(f"Susi rows  : {result['rows']:,}")
        print(f"State file : {state_file}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 2_6: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())

#!/usr/bin/env python3
"""Step 2_3: Create notebook-compatible 1 km, 5 km and 10 km products."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import pandas as pd
from pyproj import Transformer

from common import atomic_write_json

_BASE: pd.DataFrame | None = None


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config.get("lrt_grid_aggregation"), dict):
        raise KeyError("Missing 'lrt_grid_aggregation' section.")
    if not isinstance(config.get("lrt_grid_merge"), dict):
        raise KeyError("Missing 'lrt_grid_merge' section.")
    return config


def resolve_source(config: dict[str, Any]) -> Path:
    """Resolve only products created by Step 2_1."""
    aggregation = config["lrt_grid_aggregation"]
    merge = config["lrt_grid_merge"]

    candidates: list[Path] = []

    if merge.get("output_grid_parquet"):
        candidates.append(Path(merge["output_grid_parquet"]))

    if merge.get("output_csv"):
        candidates.append(
            Path(merge["output_csv"]).parent
            / "majority_formation_grid.parquet"
        )

    if aggregation.get("source_parquet"):
        candidates.append(Path(aggregation["source_parquet"]))

    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)

    for path in unique:
        if path.is_file():
            return path

    checked = "\n  ".join(str(path) for path in unique)
    raise FileNotFoundError(
        "No Step 2_1 majority-grid parquet found. Checked:\n  "
        + checked
        + "\nRun the updated Step 2_1 first."
    )


def fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        digest.update(file.read(1024 * 1024))
        if stat.st_size > 1024 * 1024:
            file.seek(max(0, stat.st_size - 1024 * 1024))
            digest.update(file.read(1024 * 1024))
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "edge_sha256": digest.hexdigest(),
    }


def atomic_write_dataframe_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def mode_first(series: pd.Series) -> object:
    values = series.dropna()
    if values.empty:
        return pd.NA
    return values.mode().iloc[0]


def normalise_source(data: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "majority_formation": "Majority_formation",
        "majority_formation_lrt_code": "LRT_code",
        "majority_formation_mapping_year": "mapping_year",
    }
    for old, new in aliases.items():
        if new not in data.columns and old in data.columns:
            data[new] = data[old]

    required = {
        "grid_id",
        "Majority_formation",
        "majority_formation_status",
        "LRT_code",
        "mapping_year",
        "x_sw",
        "y_sw",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            "Step 2_1 parquet misses notebook columns: "
            + ", ".join(sorted(missing))
        )

    data = data.copy()
    data["x_sw"] = pd.to_numeric(data["x_sw"], errors="raise").astype("int64")
    data["y_sw"] = pd.to_numeric(data["y_sw"], errors="raise").astype("int64")
    data["mapping_year"] = pd.to_numeric(
        data["mapping_year"], errors="coerce"
    ).astype("Int64")
    return data


def build_resolution(task: tuple[int, str, str]) -> tuple[int, int, int, str, str]:
    if _BASE is None:
        raise RuntimeError("Worker source was not initialised.")

    cell_size_m, output_raw, counts_raw = task
    output_csv = Path(output_raw)
    counts_csv = Path(counts_raw)
    d = _BASE.copy()

    d["x_sw_target"] = (d["x_sw"] // cell_size_m) * cell_size_m
    d["y_sw_target"] = (d["y_sw"] // cell_size_m) * cell_size_m
    d["grid_id_target"] = (
        f"{cell_size_m // 1000}kmN"
        + (d["y_sw_target"] // cell_size_m).astype(str)
        + "E"
        + (d["x_sw_target"] // cell_size_m).astype(str)
    )

    formation_counts = (
        d.groupby(
            ["grid_id_target", "Majority_formation"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "n_100m_cells"})
        .sort_values(
            ["grid_id_target", "n_100m_cells", "Majority_formation"],
            ascending=[True, False, True],
        )
    )
    top = formation_counts.drop_duplicates(
        "grid_id_target", keep="first"
    )

    status_base = d.merge(
        top[["grid_id_target", "Majority_formation"]],
        on=["grid_id_target", "Majority_formation"],
        how="inner",
    )
    status_base = status_base[
        status_base["majority_formation_status"].notna()
    ]

    if status_base.empty:
        top["majority_formation_status"] = pd.NA
    else:
        top_status = (
            status_base.groupby(
                ["grid_id_target", "majority_formation_status"],
                as_index=False,
            )
            .size()
            .rename(columns={"size": "status_n"})
            .sort_values(
                [
                    "grid_id_target",
                    "status_n",
                    "majority_formation_status",
                ],
                ascending=[True, False, True],
            )
            .drop_duplicates("grid_id_target", keep="first")
        )
        top = top.merge(
            top_status[
                ["grid_id_target", "majority_formation_status"]
            ],
            on="grid_id_target",
            how="left",
        )

    top_code_base = d.merge(
        top[["grid_id_target", "Majority_formation"]],
        on=["grid_id_target", "Majority_formation"],
        how="inner",
    )
    top_code = (
        top_code_base.groupby("grid_id_target")["LRT_code"]
        .agg(mode_first)
        .reset_index()
    )
    with_top_code = top_code_base.merge(
        top_code,
        on="grid_id_target",
        suffixes=("", "_top"),
    )
    with_top_code = with_top_code[
        with_top_code["LRT_code"] == with_top_code["LRT_code_top"]
    ]
    top_year = (
        with_top_code.groupby("grid_id_target")["mapping_year"]
        .agg(mode_first)
        .reset_index()
    )

    top = (
        top.merge(top_code, on="grid_id_target", how="left")
        .merge(top_year, on="grid_id_target", how="left")
    )
    top["mapping_year"] = pd.to_numeric(
        top["mapping_year"], errors="coerce"
    ).astype("Int64")

    coords = (
        d.groupby("grid_id_target", as_index=False)[
            ["x_sw_target", "y_sw_target"]
        ]
        .first()
        .rename(
            columns={
                "x_sw_target": "x_sw",
                "y_sw_target": "y_sw",
            }
        )
    )

    transformer = Transformer.from_crs(
        "EPSG:3035", "EPSG:4326", always_xy=True
    )
    coords["lng"], coords["lat"] = transformer.transform(
        (coords["x_sw"] + cell_size_m / 2).to_numpy(),
        (coords["y_sw"] + cell_size_m / 2).to_numpy(),
    )

    output = coords.merge(
        top[
            [
                "grid_id_target",
                "Majority_formation",
                "majority_formation_status",
                "LRT_code",
                "mapping_year",
                "n_100m_cells",
            ]
        ],
        on="grid_id_target",
        how="left",
    ).rename(columns={"grid_id_target": "grid_id"})

    class_counts = (
        output.groupby("Majority_formation", dropna=False)
        .size()
        .rename("n_cells_in_class")
        .reset_index()
    )
    class_counts["share_of_cells"] = (
        class_counts["n_cells_in_class"] / len(output)
    )

    output = output.merge(
        class_counts, on="Majority_formation", how="left"
    )
    output = output[
        [
            "grid_id",
            "Majority_formation",
            "majority_formation_status",
            "LRT_code",
            "mapping_year",
            "n_cells_in_class",
            "n_100m_cells",
            "x_sw",
            "y_sw",
            "lng",
            "lat",
        ]
    ].sort_values("grid_id").reset_index(drop=True)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_dataframe_csv(output, output_csv)
    atomic_write_dataframe_csv(class_counts, counts_csv)

    return (
        cell_size_m,
        len(output),
        len(class_counts),
        str(output_csv),
        str(counts_csv),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    global _BASE
    args = parse_args()

    try:
        config = load_config(args.config)
        settings = config["lrt_grid_aggregation"]
        source = resolve_source(config)

        output_dir = Path(
            settings.get("output_dir", source.parent)
        )
        resolutions = [
            int(value)
            for value in settings.get(
                "resolutions_m", [1000, 5000, 10000]
            )
        ]

        allocated = int(
            os.environ.get("SLURM_CPUS_PER_TASK", "1")
        )
        processes = max(
            1,
            min(
                int(settings.get("processes", allocated)),
                allocated,
                len(resolutions),
            ),
        )

        state_file = Path(
            settings.get(
                "state_file",
                Path(config["status_dir"])
                / "step_2_3_grid_aggregation_state.json",
            )
        )

        tasks: list[tuple[int, str, str]] = []
        outputs: list[Path] = []
        for resolution in resolutions:
            label = f"{resolution // 1000}km"
            csv = output_dir / f"majority_formation_grid_{label}.csv"
            counts = (
                output_dir
                / f"majority_formation_grid_{label}_class_counts.csv"
            )
            tasks.append((resolution, str(csv), str(counts)))
            outputs.extend([csv, counts])

        expected_state = {
            "input": fingerprint(source),
            "processing": {
                "resolutions_m": resolutions,
                "schema_version": "notebook_exact_v2",
            },
            "outputs": [str(path.resolve()) for path in outputs],
        }

        if (
            not args.force
            and state_file.is_file()
            and all(path.is_file() for path in outputs)
        ):
            previous = json.loads(
                state_file.read_text(encoding="utf-8")
            )
            previous.pop("result", None)
            if previous == expected_state:
                print("Step 2_3 skipped: products are current.")
                return 0

        _BASE = normalise_source(pd.read_parquet(source))
        output_dir.mkdir(parents=True, exist_ok=True)

        if processes > 1 and "fork" in mp.get_all_start_methods():
            with mp.get_context("fork").Pool(processes) as pool:
                results = pool.map(build_resolution, tasks)
        else:
            results = [build_resolution(task) for task in tasks]

        atomic_write_json(
            state_file,
            {
                **expected_state,
                "result": {
                    "source_rows": len(_BASE),
                    "products": [
                        {
                            "resolution_m": row[0],
                            "rows": row[1],
                            "classes": row[2],
                            "output_csv": row[3],
                            "class_counts_csv": row[4],
                        }
                        for row in results
                    ],
                },
            },
        )

        print(f"Step 2_3 completed from: {source}")
        for row in sorted(results):
            print(f"{row[0]} m: {row[1]:,} cells")
        return 0

    except Exception as exc:
        print(f"ERROR in Step 2_3: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())

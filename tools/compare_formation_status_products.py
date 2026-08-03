#!/usr/bin/env python3
"""Compare HoreKa core outputs with Susi-compatible companion outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

FORMATION_COLUMNS = [
    "Bogs",
    "Coastal",
    "Forests",
    "Freshwater",
    "Grassland",
    "Other",
    "Permanent Glaciers",
    "Rocky habitats",
    "Temperate heath",
]
REQUIRED_MATRIX_COLUMNS = [
    "Majority_formation",
    "majority_formation_status",
    "majority_value",
    "second_value",
    "majority_delta",
    "majority_disputed",
    "n_formations",
    "n_lrts",
]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def compare_majority_tables(
    core_parquet: Path,
    susi_parquet: Path,
    output_dir: Path,
    label: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": label,
        "core_parquet": str(core_parquet),
        "susi_parquet": str(susi_parquet),
        "exists_core": core_parquet.is_file(),
        "exists_susi": susi_parquet.is_file(),
    }
    if not core_parquet.is_file() or not susi_parquet.is_file():
        return result

    core = pd.read_parquet(
        core_parquet,
        columns=[
            "grid_id",
            "Majority_formation",
            "majority_formation_status",
            "LRT_code",
        ],
    )
    susi = pd.read_parquet(
        susi_parquet,
        columns=["grid_id", "Majority_formation", "majority_formation_status"],
    )

    merged = core.merge(
        susi,
        on="grid_id",
        how="outer",
        suffixes=("_core", "_susi"),
        indicator=True,
    )
    mismatches = merged[
        (merged["_merge"] != "both")
        | (
            merged["Majority_formation_core"]
            != merged["Majority_formation_susi"]
        )
        | (
            merged["majority_formation_status_core"].fillna("<NA>")
            != merged["majority_formation_status_susi"].fillna("<NA>")
        )
    ].copy()

    mismatch_csv = output_dir / f"{label}_majority_mismatches.csv"
    mismatches.head(100000).to_csv(mismatch_csv, index=False)

    result.update(
        {
            "core_rows": int(len(core)),
            "susi_rows": int(len(susi)),
            "merged_rows": int(len(merged)),
            "mismatch_rows": int(len(mismatches)),
            "mismatch_share": (
                float(len(mismatches) / len(merged)) if len(merged) else 0.0
            ),
            "mismatch_csv": str(mismatch_csv),
        }
    )
    return result


def summarize_gpkg(path: Path, layer: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return result
    kwargs = {"engine": "pyogrio"}
    if layer:
        kwargs["layer"] = layer
    gdf = gpd.read_file(path, **kwargs)
    result.update(
        {
            "rows": int(len(gdf)),
            "crs": str(gdf.crs),
            "columns": list(gdf.columns),
            "total_bounds": [float(value) for value in gdf.total_bounds],
        }
    )
    if "Formation" in gdf.columns:
        result["formation_counts"] = (
            gdf["Formation"]
            .value_counts(dropna=False)
            .rename_axis("Formation")
            .reset_index(name="rows")
            .to_dict(orient="records")
        )
    if "Majority_formation" in gdf.columns:
        result["majority_formation_counts"] = (
            gdf["Majority_formation"]
            .value_counts(dropna=False)
            .rename_axis("Majority_formation")
            .reset_index(name="rows")
            .to_dict(orient="records")
        )
    return result


def detect_lrt_status_columns(columns: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    formation_names = set(FORMATION_COLUMNS)
    for column in columns:
        if "_" not in column:
            continue
        code, status = column.rsplit("_", 1)
        if status not in {"A", "B", "C", "K"}:
            continue
        if code in formation_names:
            continue
        grouped.setdefault(code, []).append(column)
    return grouped


def validate_susi_matrix(
    parquet_path: Path,
    id_column: str,
    output_dir: Path,
    label: str,
    batch_size: int = 100_000,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": label,
        "path": str(parquet_path),
        "exists": parquet_path.is_file(),
        "id_column": id_column,
    }
    if not parquet_path.is_file():
        return result

    parquet = pq.ParquetFile(parquet_path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    formation_cols = [column for column in FORMATION_COLUMNS if column in columns]
    formation_status_cols = [
        f"{formation}_{status}"
        for formation in FORMATION_COLUMNS
        for status in ["A", "B", "C"]
        if f"{formation}_{status}" in columns
    ]
    lrt_status_groups = detect_lrt_status_columns(columns)
    lrt_status_cols = [
        column for cols in lrt_status_groups.values() for column in cols
    ]
    required = [id_column, *REQUIRED_MATRIX_COLUMNS]
    missing_required = [column for column in required if column not in columns]

    result.update(
        {
            "rows": int(parquet.metadata.num_rows),
            "columns": len(columns),
            "missing_required_columns": missing_required,
            "formation_columns": formation_cols,
            "formation_status_columns": formation_status_cols,
            "lrt_status_code_count": len(lrt_status_groups),
            "schema_types": {
                column: str(schema.field(column).type)
                for column in required
                if column in columns
            },
        }
    )
    if missing_required or not formation_cols:
        return result

    read_columns = list(
        dict.fromkeys(
            [
                id_column,
                *formation_cols,
                *lrt_status_cols,
                *REQUIRED_MATRIX_COLUMNS,
            ]
        )
    )
    counters = {
        "formation_value_over_10000": 0,
        "majority_delta_over_10000": 0,
        "majority_disputed_mismatch": 0,
        "n_formations_mismatch": 0,
        "n_lrts_mismatch": 0,
        "majority_value_mismatch": 0,
        "second_value_mismatch": 0,
        "majority_delta_mismatch": 0,
    }
    examples: list[dict[str, Any]] = []

    def add_examples(df: pd.DataFrame, mask: pd.Series, issue: str) -> None:
        remaining = 50 - len(examples)
        if remaining <= 0:
            return
        sample_cols = [
            column
            for column in [
                id_column,
                "Majority_formation",
                "majority_formation_status",
                "majority_value",
                "second_value",
                "majority_delta",
                "majority_disputed",
                "n_formations",
                "n_lrts",
            ]
            if column in df.columns
        ]
        sample = df.loc[mask, sample_cols].head(remaining).copy()
        for row in sample.to_dict(orient="records"):
            row["issue"] = issue
            examples.append(row)

    for batch in parquet.iter_batches(
        batch_size=batch_size,
        columns=read_columns,
    ):
        df = batch.to_pandas()
        formation_values = df[formation_cols].fillna(0)
        formation_array = formation_values.to_numpy(dtype=np.float64)
        top1 = formation_array.max(axis=1)
        if formation_array.shape[1] >= 2:
            top2 = np.partition(formation_array, -2, axis=1)[:, -2:]
            second = top2.min(axis=1)
        else:
            second = np.zeros(len(df), dtype=np.float64)
        delta = top1 - second

        over_formation = formation_values.gt(10000).any(axis=1)
        counters["formation_value_over_10000"] += int(over_formation.sum())
        add_examples(df, over_formation, "formation_value_over_10000")

        over_delta = df["majority_delta"].fillna(0).astype(float).gt(10000)
        counters["majority_delta_over_10000"] += int(over_delta.sum())
        add_examples(df, over_delta, "majority_delta_over_10000")

        disputed_expected = df["majority_delta"].fillna(0).astype(float).le(200)
        disputed_actual = df["majority_disputed"].fillna(False).astype(bool)
        disputed_mismatch = disputed_expected.ne(disputed_actual)
        counters["majority_disputed_mismatch"] += int(disputed_mismatch.sum())
        add_examples(df, disputed_mismatch, "majority_disputed_mismatch")

        n_formations_expected = formation_values.gt(0).sum(axis=1).astype(int)
        n_formations_actual = df["n_formations"].fillna(-1).astype(int)
        n_formations_mismatch = n_formations_expected.ne(n_formations_actual)
        counters["n_formations_mismatch"] += int(n_formations_mismatch.sum())
        add_examples(df, n_formations_mismatch, "n_formations_mismatch")

        n_lrts_expected = pd.Series(0, index=df.index, dtype="int64")
        for cols in lrt_status_groups.values():
            available = [column for column in cols if column in df.columns]
            if available:
                n_lrts_expected += df[available].fillna(0).gt(0).any(axis=1).astype(int)
        n_lrts_actual = df["n_lrts"].fillna(-1).astype(int)
        n_lrts_mismatch = n_lrts_expected.ne(n_lrts_actual)
        counters["n_lrts_mismatch"] += int(n_lrts_mismatch.sum())
        add_examples(df, n_lrts_mismatch, "n_lrts_mismatch")

        majority_value_mismatch = (
            df["majority_value"].fillna(-1).astype(float).ne(np.rint(top1))
        )
        counters["majority_value_mismatch"] += int(majority_value_mismatch.sum())
        add_examples(df, majority_value_mismatch, "majority_value_mismatch")

        second_value_mismatch = (
            df["second_value"].fillna(-1).astype(float).ne(np.rint(second))
        )
        counters["second_value_mismatch"] += int(second_value_mismatch.sum())
        add_examples(df, second_value_mismatch, "second_value_mismatch")

        majority_delta_mismatch = (
            df["majority_delta"].fillna(-1).astype(float).ne(np.rint(delta))
        )
        counters["majority_delta_mismatch"] += int(majority_delta_mismatch.sum())
        add_examples(df, majority_delta_mismatch, "majority_delta_mismatch")

    issues_csv = output_dir / f"{label}_schema_issues.csv"
    pd.DataFrame(examples).to_csv(issues_csv, index=False)
    result.update(
        {
            **counters,
            "issues_total": int(sum(counters.values())),
            "issues_csv": str(issues_csv),
            "ok": not missing_required and sum(counters.values()) == 0,
        }
    )
    return result


def write_markdown(results: dict[str, Any], path: Path) -> None:
    lines = [
        "# Susi Compatibility Sanity Check",
        "",
        "## Majority Table Comparisons",
        "",
    ]
    for item in results["majority_table_comparisons"]:
        lines.extend(
            [
                f"### {item['label']}",
                "",
                f"- Core exists: `{item['exists_core']}`",
                f"- Susi exists: `{item['exists_susi']}`",
            ]
        )
        if "mismatch_rows" in item:
            lines.extend(
                [
                    f"- Core rows: `{item['core_rows']:,}`",
                    f"- Susi rows: `{item['susi_rows']:,}`",
                    f"- Mismatches: `{item['mismatch_rows']:,}` "
                    f"({item['mismatch_share']:.4%})",
                    f"- Mismatch CSV: `{item['mismatch_csv']}`",
                ]
            )
        lines.append("")

    lines.extend(["## GPKG Summaries", ""])
    for name, summary in results["gpkg_summaries"].items():
        lines.extend([f"### {name}", ""])
        lines.append(f"- Exists: `{summary.get('exists')}`")
        if summary.get("exists"):
            lines.append(f"- Rows: `{summary.get('rows'):,}`")
            lines.append(f"- CRS: `{summary.get('crs')}`")
            lines.append(f"- Bounds: `{summary.get('total_bounds')}`")
        lines.append("")

    lines.extend(["## Susi Matrix Schema Checks", ""])
    for item in results.get("matrix_schema_checks", []):
        lines.extend([f"### {item['label']}", ""])
        lines.append(f"- Exists: `{item.get('exists')}`")
        if item.get("exists"):
            lines.append(f"- Rows: `{item.get('rows', 0):,}`")
            lines.append(
                "- Missing required columns: "
                f"`{item.get('missing_required_columns', [])}`"
            )
            lines.append(f"- Issues total: `{item.get('issues_total', 'not_run')}`")
            if "issues_csv" in item:
                lines.append(f"- Issue examples: `{item['issues_csv']}`")
            lines.append(f"- OK: `{item.get('ok')}`")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare core HoreKa products with Susi-compatible products."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    settings = config.get("susi_sanity_check", {})

    output_dir = Path(
        settings.get(
            "output_dir",
            "/lsdf/kit/ipf/projects/Bio-O-Ton/"
            "Data_automatisation_skripts/outputs/"
            "step_8_susi_compatibility",
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    core_100m_parquet = Path(config["lrt_grid_merge"]["output_grid_parquet"])
    susi_100m_parquet = Path(
        config["lrt_grid_merge"]["susi_compatible_outputs"]["output_dir"]
    ) / "Formation_Status_Grid_withLRTCode.parquet"
    legacy_susi_100m = Path(
        settings.get(
            "legacy_susi_100m_parquet",
            "/lsdf/kit/ipf/projects/Bio-O-Ton/InspireGrid/Vector_Data/"
            "Formation_Status_Grid_withLRTCode.parquet",
        )
    )
    susi_10m_parquet = Path(
        config["susi_10m_products"].get(
            "final_parquet",
            Path(config["susi_10m_products"]["output_dir"])
            / "Formation_Status_10m_Grid_withLRTCode.parquet",
        )
    )

    results = {
        "majority_table_comparisons": [
            compare_majority_tables(
                core_100m_parquet,
                susi_100m_parquet,
                output_dir,
                "core_vs_susi_compatible_100m",
            ),
            compare_majority_tables(
                core_100m_parquet,
                legacy_susi_100m,
                output_dir,
                "core_vs_legacy_susi_100m",
            ),
        ],
        "gpkg_summaries": {
            "core_lrt": summarize_gpkg(
                Path(config["lrt_cleaning"]["output_gpkg"]),
                config["lrt_cleaning"].get("output_layer", "lrt"),
            ),
            "legacy_susi_lrt": summarize_gpkg(
                Path(
                    settings.get(
                        "legacy_susi_lrt_gpkg",
                        "/lsdf/kit/ipf/projects/Bio-O-Ton/"
                        "InspireGrid/Vector_Data/lrt.gpkg",
                    )
                ),
                "lrt",
            ),
            "core_majority_grid": summarize_gpkg(
                Path(config["lrt_grid_merge"]["output_grid_gpkg"]),
                config["lrt_grid_merge"].get(
                    "output_grid_layer", "majority_formation_100m"
                ),
            ),
        },
        "matrix_schema_checks": [
            validate_susi_matrix(
                susi_100m_parquet,
                "grid_id",
                output_dir,
                "susi_compatible_100m_schema",
            ),
            validate_susi_matrix(
                susi_10m_parquet,
                "grid_id_10",
                output_dir,
                "susi_compatible_10m_schema",
            ),
        ],
    }

    json_path = output_dir / "susi_compatibility_sanity.json"
    md_path = output_dir / "susi_compatibility_sanity.md"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_markdown(results, md_path)

    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")
    for item in results["majority_table_comparisons"]:
        if "mismatch_rows" in item:
            print(
                f"{item['label']}: {item['mismatch_rows']:,} mismatches "
                f"({item['mismatch_share']:.4%})"
            )
    for item in results["matrix_schema_checks"]:
        if item.get("exists"):
            print(
                f"{item['label']}: {item.get('issues_total', 'not_run')} "
                f"schema/scale issues; ok={item.get('ok')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


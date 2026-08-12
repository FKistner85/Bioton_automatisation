#!/usr/bin/env python3
"""Build the normalized Dawn Chorus x LRT-variant formation table."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from Step_7_0_update_master_table import (
    add_100m_formation,
    add_10m_formation,
    normalise_id_column,
    read_csv_optional,
)

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from step2_variants import prepare


VARIANT_COLUMNS = [
    "dawn_chorus_id",
    "datetime_local",
    "datetime_utc",
    "recording_year",
    "recording_month",
    "lrt_variant",
    "lrt_variant_is_primary",
    "source_gpkg",
    "variant_100m_product_exists",
    "variant_10m_product_exists",
    "variant_row_count",
    "variant_complete_recording_count",
    "variant_majority_grid_100m_count",
    "variant_majority_grid_10m_count",
    "variant_lrt_polygon_count",
    "grid_100m_id",
    "grid_100m_assignment_exists",
    "grid_100m_has_majority_formation",
    "inside_lrt_polygon",
    "lrt_polygon_count",
    "lrt_code_count",
    "lrt_formation_count",
    "lrt_status_count",
    "lrt_mapping_year_count",
    "lrt_codes",
    "lrt_formations",
    "lrt_conservation_statuses",
    "lrt_mapping_years",
    "majority_formation_100m",
    "majority_formation_status_100m",
    "majority_value_100m",
    "second_value_100m",
    "majority_delta_100m",
    "majority_disputed_100m",
    "grid_10m_id",
    "grid_10m_assignment_exists",
    "grid_10m_has_majority_formation",
    "majority_formation_10m",
    "majority_formation_status_10m",
    "majority_value_10m",
    "second_value_10m",
    "majority_delta_10m",
    "majority_disputed_10m",
    "formation_100m_10m_agree",
    "formation_status_100m_10m_agree",
    "metadata_status",
    "sound_exists",
    "sound_status",
    "sound_has_issues",
    "photo_exists",
    "photo_status",
    "photo_has_issues",
    "sentinel_exists",
    "sentinel_status",
    "sentinel_has_issues",
    "weather_point_exists",
    "weather_point_status",
    "weather_point_has_issues",
    "bioacoustic_status",
    "bioacoustic_has_issues",
    "bioacoustic_required_models_complete",
    "ready_for_general_analysis",
    "ready_for_multimodal_analysis",
    "ready_for_bioacoustic_analysis",
    "record_blocking_issue_codes",
    "record_status",
    "release_status",
    "variant_record_status",
    "updated_utc",
]

SCHEMA_VERSION = 2


RECORDING_CONTEXT_COLUMNS = [
    column for column in VARIANT_COLUMNS
    if column in {
        "dawn_chorus_id", "datetime_local", "datetime_utc", "recording_year",
        "recording_month", "metadata_status", "sound_exists", "sound_status",
        "sound_has_issues", "photo_exists", "photo_status", "photo_has_issues",
        "sentinel_exists", "sentinel_status", "sentinel_has_issues",
        "weather_point_exists", "weather_point_status", "weather_point_has_issues",
        "bioacoustic_status", "bioacoustic_has_issues",
        "bioacoustic_required_models_complete", "ready_for_general_analysis",
        "ready_for_multimodal_analysis", "ready_for_bioacoustic_analysis",
        "record_blocking_issue_codes", "record_status", "release_status",
    }
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, dir=path.parent, encoding="utf-8", newline=""
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temporary, path)


def load_metadata(config: dict[str, Any]) -> pd.DataFrame:
    path = Path(config["point_lrt_assignment"]["metadata_csv"])
    metadata = normalise_id_column(
        read_csv_optional(path),
        ["dawn_chorus_id", "id"],
    )
    required = {"dawn_chorus_id", "lat", "lon"}
    missing = required - set(metadata.columns)
    if missing:
        raise KeyError(f"Metadata missing columns: {sorted(missing)}")
    keep = [column for column in ["dawn_chorus_id", "lat", "lon", "datetime_local", "datetime_utc"] if column in metadata.columns]
    return metadata[keep].drop_duplicates("dawn_chorus_id")


def load_recording_context(config: dict[str, Any], metadata: pd.DataFrame) -> pd.DataFrame:
    """Load non-formation dataset status once and repeat it across LRT variants."""
    master_cfg = config.get("master_table", {})
    candidates = [master_cfg.get("output_parquet"), master_cfg.get("output_csv")]
    context = pd.DataFrame()
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        path = Path(candidate)
        try:
            context = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path, low_memory=False)
            break
        except Exception:
            continue
    if context.empty:
        context = metadata.copy()
    context = normalise_id_column(context, ["dawn_chorus_id", "id"])
    for time_column in ["datetime_local", "datetime_utc"]:
        if time_column not in context.columns and time_column in metadata.columns:
            context = context.merge(metadata[["dawn_chorus_id", time_column]], on="dawn_chorus_id", how="left")
    local_values = context["datetime_local"] if "datetime_local" in context.columns else pd.Series(pd.NaT, index=context.index)
    utc_values = context["datetime_utc"] if "datetime_utc" in context.columns else pd.Series(pd.NaT, index=context.index)
    local_time = pd.to_datetime(local_values, errors="coerce")
    if local_time.isna().all():
        local_time = pd.to_datetime(utc_values, errors="coerce", utc=True)
    context["recording_year"] = local_time.dt.year.astype("Int64")
    context["recording_month"] = local_time.dt.month.astype("Int64")
    keep = [column for column in RECORDING_CONTEXT_COLUMNS if column in context.columns]
    return context[keep].drop_duplicates("dawn_chorus_id")


def parquet_row_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        import pyarrow.parquet as pq
        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:
        return int(len(pd.read_parquet(path, columns=[])))


def csv_data_row_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        return max(0, sum(1 for _line in handle) - 1)


def gpkg_feature_count(path: Path, layer: str | None = None) -> int:
    if not path.is_file():
        return 0
    try:
        import pyogrio
        return int(pyogrio.read_info(path, layer=layer).get("features", 0))
    except Exception:
        return 0


def build_variant_rows(
    metadata: pd.DataFrame,
    context: pd.DataFrame,
    config: dict[str, Any],
    suffix: str,
    primary: str,
    source_gpkg: Path,
) -> pd.DataFrame:
    assignment = Path(config["point_lrt_assignment"]["output_csv"])
    ten_m = Path(config["susi_10m_products"]["final_parquet"])
    table = add_100m_formation(metadata.copy(), config)
    table = add_10m_formation(table, config)
    table = table.merge(context, on="dawn_chorus_id", how="left", suffixes=("", "_context"))
    for column in RECORDING_CONTEXT_COLUMNS:
        context_column = f"{column}_context"
        if context_column in table.columns:
            table[column] = table[context_column].combine_first(table.get(column, pd.Series(pd.NA, index=table.index)))
            table = table.drop(columns=context_column)
    table["lrt_variant"] = suffix
    table["lrt_variant_is_primary"] = suffix == primary
    table["source_gpkg"] = str(source_gpkg)
    table["variant_100m_product_exists"] = assignment.is_file()
    table["variant_10m_product_exists"] = ten_m.is_file()
    row_count = len(table)
    table["variant_row_count"] = row_count
    complete = assignment.is_file() and ten_m.is_file()
    complete_ids = int(table["dawn_chorus_id"].nunique()) if complete else 0
    table["variant_complete_recording_count"] = complete_ids if complete else 0
    table["variant_majority_grid_100m_count"] = csv_data_row_count(Path(config["lrt_grid_merge"]["output_csv"]))
    table["variant_majority_grid_10m_count"] = parquet_row_count(ten_m)
    table["variant_lrt_polygon_count"] = gpkg_feature_count(
        Path(config["lrt_cleaning"]["output_gpkg"]), config["lrt_cleaning"].get("output_layer")
    )
    table["formation_100m_10m_agree"] = (
        table["majority_formation_100m"].notna()
        & table["majority_formation_10m"].notna()
        & (
            table["majority_formation_100m"].astype(str)
            == table["majority_formation_10m"].astype(str)
        )
    )
    table["formation_status_100m_10m_agree"] = (
        table["majority_formation_status_100m"].notna()
        & table["majority_formation_status_10m"].notna()
        & (
            table["majority_formation_status_100m"].astype(str)
            == table["majority_formation_status_10m"].astype(str)
        )
    )
    complete_products = assignment.is_file() and ten_m.is_file()
    table["variant_record_status"] = "complete" if complete_products else "partial"
    table["updated_utc"] = utc_now()
    for column in VARIANT_COLUMNS:
        if column not in table.columns:
            table[column] = pd.NA
    return table[VARIANT_COLUMNS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        base, variants = prepare(args.config)
        settings = base["lrt_variants"]
        primary = str(settings["primary_suffix"])
        output_csv = Path(settings["master_csv"])
        output_parquet = Path(settings["master_parquet"])
        summary_json = Path(settings["master_summary_json"])
        variant_summary_csv = Path(
            settings.get(
                "variant_summary_csv",
                output_csv.parent / "Bio_O_Ton_Variant_Summary.csv",
            )
        )
        temporal_summary_csv = Path(
            settings.get(
                "temporal_summary_csv",
                output_csv.parent / "Bio_O_Ton_Variant_Temporal_Summary.csv",
            )
        )
        part_dir = Path(settings["output_root"]) / "_master_parts"
        metadata = load_metadata(base)
        context = load_recording_context(base, metadata)
        parts: list[Path] = []
        rebuilt: list[str] = []

        for variant in variants:
            config = json.loads(variant.config_path.read_text(encoding="utf-8"))
            assignment = Path(config["point_lrt_assignment"]["output_csv"])
            ten_m = Path(config["susi_10m_products"]["final_parquet"])
            part = part_dir / f"{variant.suffix}.parquet"
            state_path = part_dir / f"{variant.suffix}.state.json"
            expected_state = {
                "schema_version": SCHEMA_VERSION,
                "source_gpkg": fingerprint(variant.source_gpkg),
                "assignment_100m": fingerprint(assignment),
                "formation_10m": fingerprint(ten_m),
                "metadata": fingerprint(Path(base["point_lrt_assignment"]["metadata_csv"])),
                "master_context": fingerprint(Path(base.get("master_table", {}).get("output_parquet", ""))),
            }
            previous = {}
            if state_path.is_file():
                previous = json.loads(state_path.read_text(encoding="utf-8"))
            if args.force or not part.is_file() or previous != expected_state:
                rows = build_variant_rows(
                    metadata,
                    context,
                    config,
                    variant.suffix,
                    primary,
                    variant.source_gpkg,
                )
                write_parquet_atomic(rows, part)
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(
                    json.dumps(expected_state, indent=2) + "\n",
                    encoding="utf-8",
                )
                rebuilt.append(variant.suffix)
            parts.append(part)

        if not rebuilt and output_csv.is_file() and output_parquet.is_file():
            print("Formation variant master table skipped: all parts are current.")
            return 0

        combined = pd.concat(
            [pd.read_parquet(path) for path in parts],
            ignore_index=True,
        )
        combined = combined.sort_values(
            ["dawn_chorus_id", "lrt_variant"],
            key=lambda values: (
                pd.to_numeric(values, errors="coerce")
                if values.name == "dawn_chorus_id"
                else values.astype(str)
            ),
        ).reset_index(drop=True)
        write_csv_atomic(combined, output_csv)
        write_parquet_atomic(combined, output_parquet)

        # Per-variant summary: one row per variant with key counts
        variant_stats = (
            combined.groupby("lrt_variant", sort=False)
            .agg(
                source_gpkg=("source_gpkg", "first"),
                is_primary=("lrt_variant_is_primary", "first"),
                row_count=("dawn_chorus_id", "count"),
                recording_count=("dawn_chorus_id", "nunique"),
                complete_recording_count=("variant_complete_recording_count", "first"),
                product_100m_exists=("variant_100m_product_exists", "first"),
                product_10m_exists=("variant_10m_product_exists", "first"),
                record_status=("variant_record_status", "first"),
                majority_grid_100m_count=("variant_majority_grid_100m_count", "first"),
                majority_grid_10m_count=("variant_majority_grid_10m_count", "first"),
                lrt_polygon_count=("variant_lrt_polygon_count", "first"),
                recordings_in_majority_grid_100m=("grid_100m_has_majority_formation", "sum"),
                recordings_in_majority_grid_10m=("grid_10m_has_majority_formation", "sum"),
                recordings_directly_in_lrt_polygon=("inside_lrt_polygon", "sum"),
                recordings_100m_10m_agree=("formation_100m_10m_agree", "sum"),
                recordings_general_ready=("ready_for_general_analysis", "sum"),
                recordings_multimodal_ready=("ready_for_multimodal_analysis", "sum"),
                recordings_bioacoustic_ready=("ready_for_bioacoustic_analysis", "sum"),
            )
            .reset_index()
            .rename(columns={"lrt_variant": "suffix"})
        )
        variant_stats["computed_at"] = utc_now()
        write_csv_atomic(variant_stats, variant_summary_csv)

        temporal_source = combined.dropna(subset=["recording_year"]).copy()
        temporal_source["recording_year"] = pd.to_numeric(
            temporal_source["recording_year"], errors="coerce"
        ).astype("Int64")
        temporal_stats = (
            temporal_source.groupby(["recording_year", "lrt_variant"], dropna=False, sort=True)
            .agg(
                recording_count=("dawn_chorus_id", "nunique"),
                recordings_in_majority_grid_100m=("grid_100m_has_majority_formation", "sum"),
                recordings_in_majority_grid_10m=("grid_10m_has_majority_formation", "sum"),
                recordings_directly_in_lrt_polygon=("inside_lrt_polygon", "sum"),
                recordings_general_ready=("ready_for_general_analysis", "sum"),
            )
            .reset_index()
        )
        temporal_stats["computed_at"] = utc_now()
        write_csv_atomic(temporal_stats, temporal_summary_csv)
        summary = {
            "created_utc": utc_now(),
            "primary_suffix": primary,
            "variant_count": len(variants),
            "row_count": len(combined),
            "recording_count": int(combined["dawn_chorus_id"].nunique()),
            "rebuilt_variants": rebuilt,
            "complete_variant_products": int(
                combined.groupby("lrt_variant")[[
                    "variant_100m_product_exists",
                    "variant_10m_product_exists",
                ]].all().all(axis=1).sum()
            ),
            "output_csv": str(output_csv),
            "output_parquet": str(output_parquet),
            "variant_summary_csv": str(variant_summary_csv),
            "temporal_summary_csv": str(temporal_summary_csv),
        }
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Formation variants : {len(variants)}")
        print(f"Rows               : {len(combined):,}")
        print(f"CSV                : {output_csv}")
        print(f"Parquet            : {output_parquet}")
        print(f"Variant summary    : {variant_summary_csv}")
        print(f"Temporal summary   : {temporal_summary_csv}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 7_1 formation variant table: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

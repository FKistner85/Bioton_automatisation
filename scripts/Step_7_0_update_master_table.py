#!/usr/bin/env python3
"""Step 7_0: Build/update the final Bio-O-Ton master table.

The master table is intentionally a compact, ID-level status product. Detailed
diagnostics stay in the step-specific inventory, QC and manifest files.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import (
    atomic_write_csv,
    atomic_write_json,
    load_config,
    processed_root_from_config,
    read_ids_file,
    susi_10m_grid_id_from_parent,
    utc_now_iso,
    workflow_run_id,
)


from spatiotemporal_duplicates import FLAG_COLUMNS, proximity_flags
from pipeline_phase import execution_phase
from input_consistency import require_point_coverage, guard_source_population

SCHEMA_VERSION = "2026-09-17-mastertable-v6"
MASTER_COLUMNS = [
    "mastertable_schema_version",
    "workflow_run_id",
    "dawn_chorus_id",
    "source_fingerprint",
    "datetime_local",
    "datetime_utc",
    "date_local",
    "time_local",
    "timestamp_source",
    "timestamp_changed",
    "timestamp_change_reason",
    "lat",
    "lon",
    "record_added_to_mastertable_utc",
    "record_updated_in_mastertable_utc",
    "metadata_status",
    "sound_exists",
    "sound_has_issues",
    "sound_issue_codes",
    "sound_status",
    "photo_exists",
    "photo_has_issues",
    "photo_issue_codes",
    "photo_status",
    "sentinel_exists",
    "sentinel_has_issues",
    "sentinel_quality_score",
    "sentinel_issue_codes",
    "sentinel_status",
    "weather_point_exists",
    "weather_point_has_issues",
    "weather_point_issue_codes",
    "weather_point_status",
    "weather_raster_hostrada_100m_exists",
    "weather_raster_hostrada_100m_has_issues",
    "weather_raster_hostrada_100m_issue_codes",
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
    "formation_100m_status",
    "grid_10m_id",
    "grid_10m_assignment_exists",
    "grid_10m_has_majority_formation",
    "majority_formation_10m",
    "majority_formation_status_10m",
    "majority_value_10m",
    "second_value_10m",
    "majority_delta_10m",
    "majority_disputed_10m",
    "formation_10m_status",
    "formation_100m_10m_agree",
    "formation_status_100m_10m_agree",
    "formation_primary_variant",
    "formation_variant_count_expected",
    "formation_variants_with_100m_majority",
    "formation_variants_with_10m_majority",
    "formation_variant_products_complete",
    "bioacoustic_status",
    "bioacoustic_has_issues",
    "bioacoustic_issue_codes",
    "bioacoustic_models_expected",
    "bioacoustic_models_complete",
    "bioacoustic_required_models_complete",
    "bioacoustic_inference_version",
    "bioacoustic_species_count",
    "bird_species_count",
    "nonbird_species_count",
    "bioacoustic_max_confidence",
    "top_species_scientific",
    "top_species_model_support",
    "ready_for_general_analysis",
    "ready_for_formation_analysis_100m",
    "ready_for_direct_lrt_analysis",
    "ready_for_formation_weather_raster_analysis_100m",
    "ready_for_formation_analysis_10m",
    "ready_for_multimodal_analysis",
    "ready_for_bioacoustic_analysis",
    "record_blocking_issue_codes",
    "record_status",
    "release_status",
    "manual_review_comment",
    "manual_reviewed_by",
    "manual_reviewed_utc",
]
MASTER_COLUMNS += FLAG_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build/update the final Bio-O-Ton master table."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help=(
            "Update only IDs listed in this CSV and preserve all other rows "
            "from the existing master table."
        ),
    )
    parser.add_argument(
        "--preserve-existing-nonformation-domains",
        action="store_true",
        help=(
            "Keep audio, photo, Sentinel, weather and bioacoustic values from "
            "the existing master table. Intended for a focused metadata/Step-2 "
            "refresh when those domain products are deliberately unavailable."
        ),
    )
    parser.add_argument('--allow-deferred-spatial', action='store_true',
                        help='Intermediate updates only: retain the master while Step 2.2 is pending.')
    return parser.parse_args()


def read_csv_optional(path: str | Path | None, **kwargs: Any) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(p, low_memory=False, encoding="utf-8-sig", **kwargs)


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.lower().isin({"true", "1", "yes", "y"})


def clean_issue_token(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    text = text.split(":", 1)[0]
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_").lower()


def split_issues(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return []
    tokens = []
    for part in re.split(r"\s*\|\s*|;\s*", text):
        token = clean_issue_token(part)
        if token:
            tokens.append(token)
    return tokens


def join_codes(values: list[str]) -> str:
    return "|".join(dict.fromkeys(code for code in values if code))


def id_string(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return ""
    return str(int(numeric))


def normalise_id_column(frame: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    for candidate in candidates:
        if candidate in result.columns:
            numeric = pd.to_numeric(result[candidate], errors='coerce')
            result["dawn_chorus_id"] = numeric.map(
                lambda value: '' if pd.isna(value) else str(int(value))
            )
            return result[result["dawn_chorus_id"] != ""].copy()
    return pd.DataFrame()


def read_previous_added(output_csv: Path) -> dict[str, str]:
    if not output_csv.is_file() or output_csv.stat().st_size == 0:
        return {}
    previous = pd.read_csv(
        output_csv,
        usecols=lambda column: column
        in {"dawn_chorus_id", "record_added_to_mastertable_utc"},
        dtype="string",
        low_memory=False,
    )
    if {"dawn_chorus_id", "record_added_to_mastertable_utc"} <= set(previous.columns):
        return dict(
            zip(
                previous["dawn_chorus_id"].astype(str),
                previous["record_added_to_mastertable_utc"].astype(str),
            )
        )
    return {}


def read_previous_master(output_csv: Path) -> pd.DataFrame:
    previous = read_csv_optional(output_csv, dtype={"dawn_chorus_id": "string"})
    return normalise_id_column(previous, ["dawn_chorus_id", "id"])


def restrict_to_ids(table: pd.DataFrame, selected_ids: set[str] | None) -> pd.DataFrame:
    """Return only requested rows when this is an incremental master update."""
    if selected_ids is None:
        return table
    return table[table["dawn_chorus_id"].astype(str).isin(selected_ids)].copy()


def merge_master_rows(
    previous: pd.DataFrame, updates: pd.DataFrame,
    *, replace_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Replace the requested scope, including requested IDs with no new row."""
    if previous.empty:
        return updates.copy()
    update_ids = set(updates["dawn_chorus_id"].astype(str)) if not updates.empty else set()
    replaced = update_ids if replace_ids is None else update_ids | replace_ids
    retained = previous[
        ~previous["dawn_chorus_id"].astype(str).isin(replaced)
    ].copy()
    return pd.concat([retained, updates], ignore_index=True, sort=False)


def parse_local_wall_times(values: pd.Series) -> pd.Series:
    """Parse mixed UTC offsets while preserving each row's local clock time."""
    parsed: list[pd.Timestamp | pd.NaT] = []
    for value in values:
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError):
            timestamp = pd.NaT
        if pd.isna(timestamp):
            parsed.append(pd.NaT)
            continue
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        parsed.append(timestamp)
    return pd.to_datetime(pd.Series(parsed, index=values.index), errors="coerce")


def build_base_table(config: dict[str, Any], output_csv: Path, now: str) -> pd.DataFrame:
    status_dir = Path(config["status_dir"])
    clean = read_csv_optional(status_dir / "dawnchorus_metadata_clean.csv")
    if clean.empty:
        if {"id", "datetime", "lat", "lon"}.issubset(clean.columns):
            # A valid header-only Step-1 product represents an empty population.
            return pd.DataFrame(columns=MASTER_COLUMNS)
        raise FileNotFoundError(
            f"Step 1 clean metadata is missing or empty: {status_dir / 'dawnchorus_metadata_clean.csv'}"
        )
    clean = normalise_id_column(clean, ["id", "dawn_chorus_id"])
    clean = clean.drop_duplicates("dawn_chorus_id", keep="first")
    clean = clean.rename(
        columns={
            "datetime": "datetime_local",
        }
    )
    if "lon" not in clean.columns and "lng" in clean.columns:
        clean = clean.rename(columns={"lng": "lon"})

    base = clean[["dawn_chorus_id", "datetime_local", "lat", "lon"]].copy()
    parsed_local = parse_local_wall_times(base["datetime_local"])
    parsed_utc = pd.to_datetime(base["datetime_local"], errors="coerce", utc=True, format="mixed")
    base["datetime_utc"] = parsed_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    base.loc[parsed_utc.isna(), "datetime_utc"] = pd.NA
    # UTC must be obtained from the offset-aware Step-1 value BEFORE removing
    # the offset for the consumer-facing German clock column.
    base["datetime_local"] = parsed_local.dt.strftime("%Y-%m-%d %H:%M:%S")
    base["date_local"] = parsed_local.dt.strftime("%Y-%m-%d")
    base["time_local"] = parsed_local.dt.strftime("%H:%M:%S")

    log = read_csv_optional(status_dir / "dawnchorus_metadata_log.csv")
    log = normalise_id_column(log, ["id", "dawn_chorus_id"])
    if not log.empty:
        keep = [
            column
            for column in [
                "dawn_chorus_id",
                "datetime_source",
                "conversion_needed",
                "conversion_step",
            ]
            if column in log.columns
        ]
        base = base.merge(log[keep].drop_duplicates("dawn_chorus_id"), on="dawn_chorus_id", how="left")
    base = base.rename(
        columns={
            "datetime_source": "timestamp_source",
            "conversion_needed": "timestamp_changed",
            "conversion_step": "timestamp_change_reason",
        }
    )
    for column in ["timestamp_source", "timestamp_changed", "timestamp_change_reason"]:
        if column not in base.columns:
            base[column] = pd.NA
    base["timestamp_changed"] = bool_series(base["timestamp_changed"])

    previous_added = read_previous_added(output_csv)
    base["record_added_to_mastertable_utc"] = base["dawn_chorus_id"].map(previous_added).fillna(now)
    base["record_updated_in_mastertable_utc"] = now
    base["mastertable_schema_version"] = SCHEMA_VERSION
    base["workflow_run_id"] = workflow_run_id()

    fingerprint_path = Path(
        config.get("metadata_extraction", {}).get(
            "fingerprint_csv",
            status_dir / "metadata_source_fingerprints.csv",
        )
    )
    fingerprints = normalise_id_column(
        read_csv_optional(fingerprint_path, dtype={"dawn_chorus_id": "string"}),
        ["dawn_chorus_id", "id"],
    )
    if not fingerprints.empty and "source_fingerprint" in fingerprints.columns:
        base = base.merge(
            fingerprints[["dawn_chorus_id", "source_fingerprint"]].drop_duplicates(
                "dawn_chorus_id",
                keep="last",
            ),
            on="dawn_chorus_id",
            how="left",
        )
    else:
        base["source_fingerprint"] = pd.NA

    previous = read_previous_master(output_csv)
    manual_columns = [
        "dawn_chorus_id",
        "release_status",
        "manual_review_comment",
        "manual_reviewed_by",
        "manual_reviewed_utc",
    ]
    available = [column for column in manual_columns if column in previous.columns]
    if len(available) > 1:
        base = base.merge(
            previous[available].drop_duplicates("dawn_chorus_id", keep="last"),
            on="dawn_chorus_id",
            how="left",
        )
    for column in manual_columns[1:]:
        if column not in base.columns:
            base[column] = pd.NA
    return base


# Fields that do not depend on metadata or the primary formation products.
# A focused local refresh can retain these values from a trusted previous
# master instead of copying every historical domain product to the workstation.
PRESERVED_NONFORMATION_COLUMNS = [
    "sound_exists", "sound_has_issues", "sound_issue_codes",
    "photo_exists", "photo_has_issues", "photo_issue_codes",
    "sentinel_exists", "sentinel_has_issues", "sentinel_quality_score",
    "sentinel_issue_codes",
    "weather_point_exists", "weather_point_has_issues", "weather_point_issue_codes",
    "weather_raster_hostrada_100m_exists",
    "weather_raster_hostrada_100m_has_issues",
    "weather_raster_hostrada_100m_issue_codes",
    "bioacoustic_status", "bioacoustic_has_issues", "bioacoustic_issue_codes",
    "bioacoustic_models_expected", "bioacoustic_models_complete",
    "bioacoustic_required_models_complete", "bioacoustic_inference_version",
    "bioacoustic_species_count", "bird_species_count", "nonbird_species_count",
    "bioacoustic_max_confidence", "top_species_scientific",
    "top_species_model_support",
    "formation_variant_count_expected",
    "formation_variants_with_100m_majority",
    "formation_variants_with_10m_majority",
    "formation_variant_products_complete",
]


def add_preserved_nonformation_domains(
    table: pd.DataFrame,
    previous_master: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Reuse non-Step-2 domain values from an existing master snapshot."""
    previous = normalise_id_column(previous_master, ["dawn_chorus_id", "id"])
    available = [
        column for column in PRESERVED_NONFORMATION_COLUMNS if column in previous.columns
    ]
    if available:
        table = table.merge(
            previous[["dawn_chorus_id", *available]].drop_duplicates(
                "dawn_chorus_id", keep="last"
            ),
            on="dawn_chorus_id",
            how="left",
        )
    for column in PRESERVED_NONFORMATION_COLUMNS:
        if column not in table.columns:
            table[column] = pd.NA

    if "date_local" in previous.columns:
        old_dates = previous.drop_duplicates("dawn_chorus_id").set_index("dawn_chorus_id")["date_local"]
        before = table["dawn_chorus_id"].map(old_dates)
        changed_day = before.notna() & table["date_local"].ne(before)
        for prefix in ("weather_point", "sentinel"):
            table.loc[changed_day, f"{prefix}_has_issues"] = True
            table.loc[changed_day, f"{prefix}_issue_codes"] = table.loc[
                changed_day, f"{prefix}_issue_codes"
            ].map(lambda value: join_codes(split_issues(value) + ["recording_date_changed_recheck_required"]))

    table["formation_primary_variant"] = str(
        config.get("lrt_variants", {}).get("primary_suffix", "")
    )
    return table


def aggregate_detail_issues(
    detail_csv: str | Path | None,
    id_candidates: list[str],
) -> pd.DataFrame:
    detail = read_csv_optional(detail_csv)
    detail = normalise_id_column(detail, id_candidates)
    if detail.empty or "issues" not in detail.columns:
        return pd.DataFrame(columns=["dawn_chorus_id", "issue_codes"])
    rows = []
    for dawn_id, group in detail.groupby("dawn_chorus_id", sort=False):
        codes: list[str] = []
        for value in group["issues"]:
            codes.extend(split_issues(value))
        rows.append({"dawn_chorus_id": dawn_id, "issue_codes": join_codes(codes)})
    return pd.DataFrame(rows)


def aggregate_retry_issues(
    retry_csv: str | Path | None,
    prefix: str,
) -> pd.DataFrame:
    retry = read_csv_optional(retry_csv)
    retry = normalise_id_column(retry, ["dawn_chorus_id", "id"])
    if retry.empty or "last_error" not in retry.columns:
        return pd.DataFrame(columns=["dawn_chorus_id", "retry_issue_codes"])
    rows = []
    for dawn_id, group in retry.groupby("dawn_chorus_id", sort=False):
        codes: list[str] = []
        for value in group["last_error"]:
            codes.extend(f"{prefix}_{code}" for code in split_issues(value))
        rows.append({"dawn_chorus_id": dawn_id, "retry_issue_codes": join_codes(codes)})
    return pd.DataFrame(rows)


def add_media_status(
    table: pd.DataFrame,
    config: dict[str, Any],
    section_name: str,
    prefix: str,
) -> pd.DataFrame:
    settings = config.get(section_name, {})
    compact = normalise_id_column(
        read_csv_optional(settings.get("compact_log")),
        ["dawn_chorus_id", "id"],
    )
    if compact.empty:
        media = pd.DataFrame({"dawn_chorus_id": table["dawn_chorus_id"]})
        media[f"{prefix}_exists"] = False
        media[f"{prefix}_has_issues"] = True
        media[f"{prefix}_issue_codes"] = "inventory_not_run"
    else:
        media = compact[["dawn_chorus_id"]].drop_duplicates().copy()
        media[f"{prefix}_exists"] = True
        if "has_issues" in compact.columns:
            issue_by_id = (
                compact.assign(_has_issues=bool_series(compact["has_issues"]))
                .groupby("dawn_chorus_id")["_has_issues"]
                .any()
            )
            media[f"{prefix}_has_issues"] = (
                media["dawn_chorus_id"].map(issue_by_id).fillna(False).astype(bool)
            )
        else:
            media[f"{prefix}_has_issues"] = False
        media[f"{prefix}_issue_codes"] = ""

    detail_issues = aggregate_detail_issues(
        settings.get("detailed_log"),
        ["dawn_chorus_id", "id"],
    ).rename(columns={"issue_codes": f"{prefix}_detail_issue_codes"})
    retry_section = config.get(f"{prefix}_download", {})
    retry_issues = aggregate_retry_issues(
        retry_section.get("retry_log"),
        prefix,
    )

    media = table[["dawn_chorus_id"]].merge(media, on="dawn_chorus_id", how="left")
    media[f"{prefix}_exists"] = bool_series(media[f"{prefix}_exists"])
    media_issue_missing = media[f"{prefix}_has_issues"].isna()
    media[f"{prefix}_has_issues"] = (
        bool_series(media[f"{prefix}_has_issues"]) | media_issue_missing
    )
    media[f"{prefix}_issue_codes"] = media[f"{prefix}_issue_codes"].fillna("")
    media = media.merge(detail_issues, on="dawn_chorus_id", how="left")
    media = media.merge(retry_issues, on="dawn_chorus_id", how="left")

    missing_code = "missing_file"
    issue_values = []
    for row in media.to_dict("records"):
        codes: list[str] = []
        if not row[f"{prefix}_exists"]:
            codes.append(missing_code)
        codes.extend(split_issues(row.get(f"{prefix}_issue_codes", "")))
        codes.extend(split_issues(row.get(f"{prefix}_detail_issue_codes", "")))
        codes.extend(split_issues(row.get("retry_issue_codes", "")))
        issue_values.append(join_codes(codes))
    media[f"{prefix}_issue_codes"] = issue_values
    media[f"{prefix}_has_issues"] = (
        media[f"{prefix}_has_issues"]
        | media[f"{prefix}_issue_codes"].astype(str).ne("")
    )
    return table.merge(
        media[
            [
                "dawn_chorus_id",
                f"{prefix}_exists",
                f"{prefix}_has_issues",
                f"{prefix}_issue_codes",
            ]
        ],
        on="dawn_chorus_id",
        how="left",
    )


def add_bioacoustic_status(
    table: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Attach compact Step-6 QC and recording-level species summaries."""
    settings = config.get("bioacoustics", {})
    compact = normalise_id_column(
        read_csv_optional(
            settings.get("qc_compact_csv"),
            dtype={"dawn_chorus_id": "string"},
        ),
        ["dawn_chorus_id", "id"],
    )
    columns = [
        "bioacoustic_status",
        "bioacoustic_has_issues",
        "bioacoustic_issue_codes",
        "bioacoustic_models_expected",
        "bioacoustic_models_complete",
        "bioacoustic_required_models_complete",
        "bioacoustic_inference_version",
        "bioacoustic_species_count",
        "bird_species_count",
        "nonbird_species_count",
        "bioacoustic_max_confidence",
        "top_species_scientific",
        "top_species_model_support",
    ]
    if compact.empty:
        bio = table[["dawn_chorus_id"]].copy()
        bio["bioacoustic_status"] = "not_started"
        bio["bioacoustic_has_issues"] = True
        bio["bioacoustic_issue_codes"] = "bioacoustic_qc_not_run"
    else:
        available = ["dawn_chorus_id", *[column for column in columns if column in compact.columns]]
        bio = compact[available].drop_duplicates("dawn_chorus_id", keep="last")
    for column in columns:
        if column not in bio.columns:
            bio[column] = pd.NA
    bio["bioacoustic_status"] = bio["bioacoustic_status"].fillna("not_started")
    bio["bioacoustic_has_issues"] = bool_series(
        bio["bioacoustic_has_issues"].fillna(True)
    )
    bio["bioacoustic_issue_codes"] = bio["bioacoustic_issue_codes"].fillna("")
    bio["bioacoustic_required_models_complete"] = bool_series(
        bio["bioacoustic_required_models_complete"].fillna(False)
    )
    for column in [
        "bioacoustic_species_count",
        "bird_species_count",
        "nonbird_species_count",
        "top_species_model_support",
    ]:
        bio[column] = pd.to_numeric(bio[column], errors="coerce").astype("Int64")
    bio["bioacoustic_max_confidence"] = pd.to_numeric(
        bio["bioacoustic_max_confidence"],
        errors="coerce",
    )
    merged = table.merge(
        bio[["dawn_chorus_id", *columns]],
        on="dawn_chorus_id",
        how="left",
    )
    merged["bioacoustic_status"] = merged["bioacoustic_status"].fillna("not_started")
    merged["bioacoustic_has_issues"] = (
        bool_series(merged["bioacoustic_has_issues"])
        | merged["bioacoustic_has_issues"].isna()
    )
    merged["bioacoustic_issue_codes"] = merged["bioacoustic_issue_codes"].fillna(
        "bioacoustic_result_missing"
    )
    merged["bioacoustic_required_models_complete"] = (
        bool_series(merged["bioacoustic_required_models_complete"])
    )
    return merged


def refresh_bioacoustic_domain(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Refresh only Step-6 fields, preserving metadata, grids and other domains."""
    result = table.copy()
    bio = add_bioacoustic_status(table[["dawn_chorus_id"]], config)
    bio.index = table.index
    for column in bio.columns:
        if column != "dawn_chorus_id":
            result[column] = bio[column]
    result["ready_for_bioacoustic_analysis"] = (
        bool_series(result["sound_exists"])
        & ~bool_series(result["sound_has_issues"].fillna(True))
        & result["bioacoustic_status"].eq("validated")
        & bool_series(result["bioacoustic_required_models_complete"])
    )
    return result


def write_bioacoustic_master(config, output_csv, output_parquet, summary_json, now):
    """The caller holds the shared master write lock. No spatial reconstruction."""
    previous = read_previous_master(output_csv)
    if previous.empty:
        raise ValueError("Run the core pipeline first: an existing master is required.")
    table = refresh_bioacoustic_domain(previous, config)
    atomic_write_csv(table, output_csv)
    parquet_written = write_parquet_optional(table, output_parquet)
    append_status_events(config, previous, table, now, partial_update=False)
    summary = json.loads(summary_json.read_text(encoding="utf-8")) if summary_json.is_file() else {}
    summary.update({
        "phase": "bioacoustics", "workflow_run_id": workflow_run_id(),
        "created_utc": now, "rows": len(table), "rows_updated": len(table),
        "output_csv": str(output_csv),
        "output_parquet": str(output_parquet) if parquet_written else "",
        "ready_for_bioacoustic_analysis": int(table["ready_for_bioacoustic_analysis"].sum()),
    })
    atomic_write_json(summary_json, summary)
    print(f"Bioacoustic master fields refreshed: {len(table):,} recordings")


def add_sentinel_status(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    settings = config.get("sentinel2_inventory", {})
    compact = normalise_id_column(
        read_csv_optional(settings.get("compact_log")),
        ["dawn_chorus_id", "id"],
    )
    if compact.empty:
        sentinel = table[["dawn_chorus_id"]].copy()
        sentinel["sentinel_exists"] = False
        sentinel["sentinel_has_issues"] = True
        sentinel["sentinel_quality_score"] = pd.NA
        sentinel["sentinel_issue_codes"] = "inventory_not_run"
    else:
        keep = [
            column
            for column in [
                "dawn_chorus_id",
                "sentinel_exists",
                "sentinel_has_issues",
                "sentinel_quality_score",
            ]
            if column in compact.columns
        ]
        sentinel = compact[keep].drop_duplicates("dawn_chorus_id")
        for column, default in [
            ("sentinel_exists", False),
            ("sentinel_has_issues", True),
            ("sentinel_quality_score", pd.NA),
        ]:
            if column not in sentinel.columns:
                sentinel[column] = default
        sentinel["sentinel_exists"] = bool_series(sentinel["sentinel_exists"])
        sentinel["sentinel_has_issues"] = bool_series(sentinel["sentinel_has_issues"])
        sentinel["sentinel_quality_score"] = pd.to_numeric(
            sentinel["sentinel_quality_score"],
            errors="coerce",
        )
        sentinel["sentinel_issue_codes"] = ""

    detail_issues = aggregate_detail_issues(
        settings.get("detailed_log"),
        ["dawn_chorus_id", "id"],
    ).rename(columns={"issue_codes": "sentinel_detail_issue_codes"})
    sentinel = table[["dawn_chorus_id"]].merge(sentinel, on="dawn_chorus_id", how="left")
    sentinel["sentinel_exists"] = bool_series(sentinel["sentinel_exists"])
    sentinel_issue_missing = sentinel["sentinel_has_issues"].isna()
    sentinel["sentinel_has_issues"] = (
        bool_series(sentinel["sentinel_has_issues"]) | sentinel_issue_missing
    )
    sentinel = sentinel.merge(detail_issues, on="dawn_chorus_id", how="left")
    issue_values = []
    for row in sentinel.to_dict("records"):
        codes: list[str] = []
        if not row["sentinel_exists"]:
            codes.append("missing_file")
        codes.extend(split_issues(row.get("sentinel_issue_codes", "")))
        codes.extend(split_issues(row.get("sentinel_detail_issue_codes", "")))
        issue_values.append(join_codes(codes))
    sentinel["sentinel_issue_codes"] = issue_values
    sentinel["sentinel_has_issues"] = (
        sentinel["sentinel_has_issues"]
        | sentinel["sentinel_issue_codes"].astype(str).ne("")
    )
    return table.merge(
        sentinel[
            [
                "dawn_chorus_id",
                "sentinel_exists",
                "sentinel_has_issues",
                "sentinel_quality_score",
                "sentinel_issue_codes",
            ]
        ],
        on="dawn_chorus_id",
        how="left",
    )


# Weather files are checked exclusively by Step 5_1. The master consumes its
# inventory; do not introduce a second fixed-24-hour DST check here.
def add_weather_point_status(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    inventory = config.get("weather_inventory", {})
    compact = normalise_id_column(
        read_csv_optional(
            inventory.get("compact_log"),
            dtype={"dawn_chorus_id": "string"},
        ),
        ["dawn_chorus_id", "id"],
    )
    if compact.empty:
        weather = table[["dawn_chorus_id"]].copy()
        weather["weather_point_exists"] = False
        weather["weather_point_has_issues"] = True
        weather["weather_point_issue_codes"] = "inventory_not_run"
        return table.merge(weather, on="dawn_chorus_id", how="left")

    # Real inventory files may contain both the domain-specific and generic
    # issue columns. Renaming both aliases to one target creates duplicate
    # column names, causing ``compact[target]`` to return a DataFrame. Coalesce
    # aliases in priority order and remove only the redundant source columns.
    aliases = {
        "weather_point_exists": ["weather_exists", "exists"],
        "weather_point_has_issues": ["weather_has_issues", "has_issues"],
        "weather_point_issue_codes": ["issue_codes"],
    }
    compact = compact.copy()
    for target, sources in aliases.items():
        values = (
            compact[target].copy()
            if target in compact.columns
            else pd.Series(pd.NA, index=compact.index, dtype="object")
        )
        for source in sources:
            if source in compact.columns:
                values = values.combine_first(compact[source])
        compact[target] = values
        compact = compact.drop(
            columns=[source for source in sources if source in compact.columns]
        )
    weather = compact[["dawn_chorus_id"]].copy()
    for column, default in [
        ("weather_point_exists", False),
        ("weather_point_has_issues", True),
        ("weather_point_issue_codes", ""),
    ]:
        weather[column] = (
            compact[column]
            if column in compact.columns
            else default
        )
    weather["weather_point_exists"] = bool_series(weather["weather_point_exists"])
    weather["weather_point_has_issues"] = bool_series(weather["weather_point_has_issues"])
    weather["weather_point_issue_codes"] = weather["weather_point_issue_codes"].fillna("")
    weather.loc[
        ~weather["weather_point_exists"]
        & weather["weather_point_issue_codes"].astype(str).eq(""),
        "weather_point_issue_codes",
    ] = "missing_file"
    weather["weather_point_has_issues"] = (
        weather["weather_point_has_issues"]
        | weather["weather_point_issue_codes"].astype(str).ne("")
    )
    weather = weather.drop_duplicates("dawn_chorus_id", keep="last")
    result = table.merge(weather, on="dawn_chorus_id", how="left")
    result["weather_point_exists"] = result["weather_point_exists"].fillna(False).astype(bool)
    result["weather_point_has_issues"] = result["weather_point_has_issues"].fillna(True).astype(bool)
    result["weather_point_issue_codes"] = result["weather_point_issue_codes"].fillna("missing_file")
    return result


def add_weather_raster_status(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    raster_cfg = config.get("hostrada_raster_products", {})
    qc_cfg = config.get("hostrada_raster_quality_check", {})
    output_root = Path(raster_cfg.get("output_root", ""))
    resolution = int(raster_cfg.get("resolution_m", 100))
    if resolution != 100:
        raise ValueError(
            f"Expected HOSTRADA raster resolution_m=100 for the master table, got {resolution}."
        )

    tif_count = 0
    if output_root.exists():
        tif_count = sum(1 for _ in output_root.rglob("*.tif")) + sum(1 for _ in output_root.rglob("*.tiff"))
    exists = output_root.is_dir() and tif_count > 0
    issue_codes: list[str] = []
    if not exists:
        issue_codes.append("missing_raster")

    qc_csv = Path(qc_cfg.get("output_dir", "")) / "hostrada_raster_quality.csv"
    if qc_csv.is_file() and qc_csv.stat().st_size > 0:
        try:
            qc = pd.read_csv(qc_csv, low_memory=False)
            if "status" in qc.columns and qc["status"].astype(str).str.upper().eq("ONLY_NODATA").any():
                issue_codes.append("all_nodata")
            if "square" in qc.columns and (~bool_series(qc["square"])).any():
                issue_codes.append("unexpected_shape")
            for column in ["constant_rows", "constant_cols", "nodata_rows", "nodata_cols"]:
                if column in qc.columns and pd.to_numeric(qc[column], errors="coerce").fillna(0).gt(0).any():
                    issue_codes.append("raster_structure_warning")
                    break
        except Exception as exc:
            issue_codes.append(f"raster_qc_read_error_{type(exc).__name__}")
    elif exists:
        issue_codes.append("qc_not_run")

    table["weather_raster_hostrada_100m_exists"] = exists
    table["weather_raster_hostrada_100m_has_issues"] = bool(issue_codes)
    table["weather_raster_hostrada_100m_issue_codes"] = join_codes(issue_codes)
    return table


def centi_percent_from_pct(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").mul(100).round().astype("Int64")


def read_grid_at_points(grid_path, layer, grid_column, projected):
    """Use the GeoPackage R-tree for candidates; retain exact geometry checks."""
    import geopandas as gpd
    import sqlite3

    with contextlib.closing(sqlite3.connect(
        Path(grid_path).resolve().as_uri() + "?mode=ro", uri=True
    )) as connection:
        geometry = connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
            (layer,),
        ).fetchone()
        index_name = f"rtree_{layer}_{geometry[0]}" if geometry else ""
        indexed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (index_name,),
        ).fetchone()
        if indexed:
            quoted_index = '"' + index_name.replace('"', '""') + '"'
            query = (f"SELECT id FROM {quoted_index} WHERE minx <= ? AND maxx >= ? "
                     "AND miny <= ? AND maxy >= ?")
            candidates = set()
            coordinates = set(zip(projected.geometry.x, projected.geometry.y))
            for x, y in coordinates:
                candidates.update(row[0] for row in connection.execute(query, (x, x, y, y)))
            if not candidates:
                return gpd.GeoDataFrame(
                    {grid_column: pd.Series(dtype="string")}, geometry=[], crs=projected.crs
                )
            return gpd.read_file(
                grid_path, layer=layer, engine="pyogrio", columns=[grid_column],
                fids=sorted(candidates),
            )
    return gpd.read_file(
        grid_path, layer=layer, engine="pyogrio", columns=[grid_column],
        mask=projected.geometry,
    )


def complete_100m_grid_ids(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Fill missing IDs from the original grid, independently of LRT products.

    Reuse Step 2.2's projection, within predicate and overlap tie-breaking.
    IDs are read verbatim from the reference grid, never synthesised.
    """
    ids = table.get("grid_100m_id", pd.Series(pd.NA, index=table.index)).astype("string")
    missing = ids.isna() | ids.str.strip().eq("")
    settings = config.get("point_lrt_assignment", {})
    grid_path = settings.get("grid_gpkg")
    if missing.any() and grid_path:
        import pyogrio
        from Step_2_2_assign_points_to_lrt_grid import (
            assign_points_to_grid,
            build_point_geodataframe,
        )

        layer = settings.get("grid_layer", "grid")
        grid_column = settings.get("grid_id_column", "grid_id")
        info = pyogrio.read_info(grid_path, layer=layer)
        if not info["crs"]:
            raise ValueError("The INSPIRE grid has no CRS.")
        points = table.loc[missing, ["lat", "lon"]].copy()
        # Use row positions rather than recording IDs to preserve index/order.
        points["id"] = range(len(points))
        for column in ("lat", "lon"):
            points[column] = pd.to_numeric(points[column], errors="coerce")
        points = points.loc[
            points["lat"].between(-90, 90) & points["lon"].between(-180, 180)
        ]
        projected = build_point_geodataframe(points, info["crs"])
        if not projected.empty:
            # Spatial filtering avoids loading the entire national 100 m grid.
            grid = read_grid_at_points(grid_path, layer, grid_column, projected)
            assigned = assign_points_to_grid(projected, grid, grid_column)
            by_position = assigned.set_index("id")[grid_column]
            ids.loc[missing] = pd.array(
                by_position.reindex(range(int(missing.sum()))), dtype="string"
            )
    table["grid_100m_id"] = ids
    table["grid_100m_assignment_exists"] = ids.notna() & ids.str.strip().ne("")
    return table


def add_100m_formation(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    point_cfg = config.get("point_lrt_assignment", {})
    assignment = normalise_id_column(
        read_csv_optional(point_cfg.get("output_csv")),
        ["id", "dawn_chorus_id"],
    )
    if assignment.empty:
        for column in [
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
        ]:
            table[column] = pd.NA
        table["grid_100m_assignment_exists"] = False
        table["grid_100m_has_majority_formation"] = False
        table["inside_lrt_polygon"] = False
        table["lrt_polygon_count"] = 0
        return complete_100m_grid_ids(table, config)

    grid_col = config.get("point_lrt_assignment", {}).get("grid_id_column", "grid_id")
    keep = [column for column in assignment.columns if column in {
        "dawn_chorus_id",
        grid_col,
        "inside_majority_grid",
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
        "majority_formation",
        "Majority_formation",
        "majority_formation_status",
        "majority_value",
        "second_value",
        "majority_delta",
        "majority_disputed",
        "majority_formation_coverage_pct",
        "majority_gap_pct",
    }]
    assignment = assignment[keep].drop_duplicates("dawn_chorus_id")
    result = table.merge(assignment, on="dawn_chorus_id", how="left")
    result["grid_100m_id"] = result.get(grid_col, pd.Series(pd.NA, index=result.index))
    result["grid_100m_assignment_exists"] = result["grid_100m_id"].notna()
    result["majority_formation_100m"] = result.get("majority_formation", result.get("Majority_formation", pd.NA))
    result["grid_100m_has_majority_formation"] = result["majority_formation_100m"].notna()
    result["inside_lrt_polygon"] = bool_series(
        result.get("inside_lrt_polygon", pd.Series(False, index=result.index))
    )
    result["lrt_polygon_count"] = pd.to_numeric(
        result.get("lrt_polygon_count", pd.Series(0, index=result.index)), errors="coerce"
    ).fillna(0).astype("Int64")
    result["majority_formation_status_100m"] = result.get("majority_formation_status", pd.NA)

    if "majority_value" in result.columns:
        result["majority_value_100m"] = pd.to_numeric(result["majority_value"], errors="coerce").round().astype("Int64")
    elif "majority_formation_coverage_pct" in result.columns:
        result["majority_value_100m"] = centi_percent_from_pct(result["majority_formation_coverage_pct"])
    else:
        result["majority_value_100m"] = pd.NA

    if "majority_delta" in result.columns:
        result["majority_delta_100m"] = pd.to_numeric(result["majority_delta"], errors="coerce").round().astype("Int64")
    elif "majority_gap_pct" in result.columns:
        result["majority_delta_100m"] = centi_percent_from_pct(result["majority_gap_pct"])
    else:
        result["majority_delta_100m"] = pd.NA

    if "second_value" in result.columns:
        result["second_value_100m"] = pd.to_numeric(result["second_value"], errors="coerce").round().astype("Int64")
    else:
        result["second_value_100m"] = (
            result["majority_value_100m"] - result["majority_delta_100m"]
        ).astype("Int64")
    if "majority_disputed" in result.columns:
        result["majority_disputed_100m"] = bool_series(result["majority_disputed"])
    else:
        result["majority_disputed_100m"] = result["majority_delta_100m"].le(200)
    result = result.drop(columns=[column for column in [grid_col] if column in result.columns], errors="ignore")
    return complete_100m_grid_ids(result, config)


def compute_10m_grid_ids(table: pd.DataFrame) -> pd.Series:
    try:
        from pyproj import Transformer
    except Exception:
        return pd.Series(pd.NA, index=table.index)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    ids: list[str | pd.NA] = []
    grid_100m_ids = table.get(
        "grid_100m_id", pd.Series(pd.NA, index=table.index)
    )
    for grid_id_100, lon, lat in zip(grid_100m_ids, table["lon"], table["lat"]):
        try:
            if pd.isna(grid_id_100) or pd.isna(lon) or pd.isna(lat):
                ids.append(pd.NA)
                continue
            x, y = transformer.transform(float(lon), float(lat))
            if not math.isfinite(x) or not math.isfinite(y):
                ids.append(pd.NA)
                continue
            ids.append(
                susi_10m_grid_id_from_parent(str(grid_id_100), x, y)
            )
        except Exception:
            ids.append(pd.NA)
    return pd.Series(ids, index=table.index, dtype="string")


def read_10m_rows(path: Path, grid_ids: list[str], columns: list[str]) -> pd.DataFrame:
    if not path.is_file() or not grid_ids:
        return pd.DataFrame()
    try:
        import pyarrow.dataset as ds

        dataset = ds.dataset(path, format="parquet")
        available = [field.name for field in dataset.schema]
        id_column = "grid_id_10" if "grid_id_10" in available else "grid_id"
        selected = [column for column in columns if column in available]
        if id_column not in selected:
            selected.insert(0, id_column)
        table = dataset.to_table(
            columns=selected,
            filter=ds.field(id_column).isin(grid_ids),
        )
        frame = table.to_pandas()
        if id_column != "grid_id_10":
            frame = frame.rename(columns={id_column: "grid_id_10"})
        return frame.drop_duplicates("grid_id_10")
    except Exception:
        try:
            frame = pd.read_parquet(path, columns=[column for column in columns if column])
            if "grid_id" in frame.columns and "grid_id_10" not in frame.columns:
                frame = frame.rename(columns={"grid_id": "grid_id_10"})
            return frame[frame["grid_id_10"].astype(str).isin(set(grid_ids))].drop_duplicates("grid_id_10")
        except Exception as exc:
            raise ValueError(f'FORMATION_10M_UNREADABLE: {path}') from exc


def add_10m_formation(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    table["grid_10m_id"] = compute_10m_grid_ids(table)
    table["grid_10m_assignment_exists"] = table["grid_10m_id"].notna()
    path = Path(config.get("susi_10m_products", {}).get("final_parquet", ""))
    columns = [
        "grid_id_10",
        "grid_id",
        "Majority_formation",
        "majority_formation_status",
        "majority_value",
        "second_value",
        "majority_delta",
        "majority_disputed",
    ]
    ids = table["grid_10m_id"].dropna().astype(str).drop_duplicates().tolist()
    ten = read_10m_rows(path, ids, columns)
    if ten.empty:
        table["grid_10m_has_majority_formation"] = False
        for column in [
            "majority_formation_10m",
            "majority_formation_status_10m",
            "majority_value_10m",
            "second_value_10m",
            "majority_delta_10m",
            "majority_disputed_10m",
        ]:
            table[column] = pd.NA
        return table
    ten = ten.rename(
        columns={
            "grid_id_10": "grid_10m_id",
            "Majority_formation": "majority_formation_10m",
            "majority_formation_status": "majority_formation_status_10m",
            "majority_value": "majority_value_10m",
            "second_value": "second_value_10m",
            "majority_delta": "majority_delta_10m",
            "majority_disputed": "majority_disputed_10m",
        }
    )
    table = table.merge(ten, on="grid_10m_id", how="left")
    table["grid_10m_assignment_exists"] = table["grid_10m_id"].notna()
    table["grid_10m_has_majority_formation"] = table["majority_formation_10m"].notna()
    for column in ["majority_value_10m", "second_value_10m", "majority_delta_10m"]:
        table[column] = pd.to_numeric(table[column], errors="coerce").round().astype("Int64")
    table["majority_disputed_10m"] = bool_series(table["majority_disputed_10m"])
    return table


def add_formation_variant_status(
    table: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    settings = config.get("lrt_variants", {})
    primary = str(settings.get("primary_suffix", ""))
    path = Path(settings.get("master_parquet", ""))
    expected = 0
    index_path = Path(settings.get("index_json", ""))
    if index_path.is_file():
        try:
            expected = int(
                json.loads(index_path.read_text(encoding="utf-8")).get(
                    "variant_count", 0
                )
            )
        except (OSError, ValueError, json.JSONDecodeError):
            expected = 0

    table["formation_primary_variant"] = primary
    table["formation_variant_count_expected"] = expected
    table["formation_variants_with_100m_majority"] = 0
    table["formation_variants_with_10m_majority"] = 0
    table["formation_variant_products_complete"] = False
    if not path.is_file():
        return table

    columns = [
        "dawn_chorus_id",
        "lrt_variant",
        "grid_100m_has_majority_formation",
        "grid_10m_has_majority_formation",
        "variant_100m_product_exists",
        "variant_10m_product_exists",
    ]
    variants = pd.read_parquet(path, columns=columns)
    variants = normalise_id_column(variants, ["dawn_chorus_id"])
    if variants.empty:
        return table
    for column in [
        "grid_100m_has_majority_formation",
        "grid_10m_has_majority_formation",
        "variant_100m_product_exists",
        "variant_10m_product_exists",
    ]:
        variants[column] = bool_series(variants[column])
    counts = variants.groupby("dawn_chorus_id", as_index=False).agg(
        formation_variants_with_100m_majority=(
            "grid_100m_has_majority_formation", "sum"
        ),
        formation_variants_with_10m_majority=(
            "grid_10m_has_majority_formation", "sum"
        ),
    )
    table = table.drop(
        columns=[
            "formation_variants_with_100m_majority",
            "formation_variants_with_10m_majority",
        ],
        errors="ignore",
    ).merge(counts, on="dawn_chorus_id", how="left")
    table["formation_variants_with_100m_majority"] = (
        pd.to_numeric(
            table["formation_variants_with_100m_majority"], errors="coerce"
        ).fillna(0).astype("Int64")
    )
    table["formation_variants_with_10m_majority"] = (
        pd.to_numeric(
            table["formation_variants_with_10m_majority"], errors="coerce"
        ).fillna(0).astype("Int64")
    )
    product_status = variants.groupby("lrt_variant")[[
        "variant_100m_product_exists",
        "variant_10m_product_exists",
    ]].all().all(axis=1)
    actual_variants = int(variants["lrt_variant"].nunique())
    complete = bool(product_status.all()) and actual_variants == expected and expected > 0
    # Global product existence cannot certify a recording absent from a variant.
    coverage = variants.groupby('dawn_chorus_id')['lrt_variant'].nunique()
    table["formation_variant_products_complete"] = (
        complete & table['dawn_chorus_id'].map(coverage).eq(expected)
    )
    return table


def add_agreement_and_ready_flags(table: pd.DataFrame) -> pd.DataFrame:
    table["formation_100m_10m_agree"] = (
        table["majority_formation_100m"].notna()
        & table["majority_formation_10m"].notna()
        & (table["majority_formation_100m"].astype(str) == table["majority_formation_10m"].astype(str))
    )
    table["formation_status_100m_10m_agree"] = (
        table["majority_formation_status_100m"].notna()
        & table["majority_formation_status_10m"].notna()
        & (
            table["majority_formation_status_100m"].astype(str)
            == table["majority_formation_status_10m"].astype(str)
        )
    )

    valid_timestamp = table["datetime_local"].notna() & table["datetime_utc"].notna()
    valid_coordinates = (
        pd.to_numeric(table["lat"], errors="coerce").between(-90, 90)
        & pd.to_numeric(table["lon"], errors="coerce").between(-180, 180)
    )
    table["metadata_status"] = "validated"
    table.loc[~(valid_timestamp & valid_coordinates), "metadata_status"] = "has_issues"

    for prefix in ["sound", "photo", "sentinel", "weather_point"]:
        exists = table[f"{prefix}_exists"].fillna(False).astype(bool)
        has_issues = table[f"{prefix}_has_issues"].fillna(True).astype(bool)
        table[f"{prefix}_status"] = "validated"
        table.loc[~exists, f"{prefix}_status"] = "missing"
        table.loc[exists & has_issues, f"{prefix}_status"] = "has_issues"

    table["formation_100m_status"] = "validated"
    table.loc[
        ~table["grid_100m_assignment_exists"].fillna(False).astype(bool),
        "formation_100m_status",
    ] = "missing"
    table.loc[
        table["grid_100m_assignment_exists"].fillna(False).astype(bool)
        & ~table["grid_100m_has_majority_formation"].fillna(False).astype(bool),
        "formation_100m_status",
    ] = "has_issues"
    table["formation_10m_status"] = "validated"
    table.loc[
        ~table["grid_10m_assignment_exists"].fillna(False).astype(bool),
        "formation_10m_status",
    ] = "missing"
    table.loc[
        table["grid_10m_assignment_exists"].fillna(False).astype(bool)
        & ~table["grid_10m_has_majority_formation"].fillna(False).astype(bool),
        "formation_10m_status",
    ] = "has_issues"

    table["ready_for_general_analysis"] = (
        valid_timestamp
        & valid_coordinates
        & table["sound_exists"].fillna(False).astype(bool)
        & ~table["sound_has_issues"].fillna(True).astype(bool)
        & table["weather_point_exists"].fillna(False).astype(bool)
        & ~table["weather_point_has_issues"].fillna(True).astype(bool)
        & table["sentinel_exists"].fillna(False).astype(bool)
        & ~table["sentinel_has_issues"].fillna(True).astype(bool)
    )
    table["ready_for_formation_analysis_100m"] = (
        table["ready_for_general_analysis"]
        & table["grid_100m_assignment_exists"].fillna(False).astype(bool)
        & table["grid_100m_has_majority_formation"].fillna(False).astype(bool)
    )
    table["ready_for_direct_lrt_analysis"] = (
        table["ready_for_general_analysis"]
        & table["inside_lrt_polygon"].fillna(False).astype(bool)
    )
    table["ready_for_formation_weather_raster_analysis_100m"] = (
        table["ready_for_formation_analysis_100m"]
        & table["weather_raster_hostrada_100m_exists"].fillna(False).astype(bool)
        & ~table["weather_raster_hostrada_100m_has_issues"].fillna(True).astype(bool)
    )
    table["ready_for_formation_analysis_10m"] = (
        table["ready_for_general_analysis"]
        & table["grid_10m_assignment_exists"].fillna(False).astype(bool)
        & table["grid_10m_has_majority_formation"].fillna(False).astype(bool)
    )
    table["ready_for_multimodal_analysis"] = (
        table["ready_for_general_analysis"]
        & table["photo_exists"].fillna(False).astype(bool)
        & ~table["photo_has_issues"].fillna(True).astype(bool)
    )
    table["ready_for_bioacoustic_analysis"] = (
        table["sound_exists"].fillna(False).astype(bool)
        & ~table["sound_has_issues"].fillna(True).astype(bool)
        & table["bioacoustic_status"].fillna("").astype(str).eq("validated")
        & table["bioacoustic_required_models_complete"].fillna(False).astype(bool)
    )

    blocking = []
    for _, row in table.iterrows():
        codes: list[str] = []
        if not bool(valid_timestamp.loc[row.name]):
            codes.append("timestamp_missing_or_invalid")
        if not bool(valid_coordinates.loc[row.name]):
            codes.append("coordinates_missing_or_invalid")
        for prefix in ["sound", "weather_point", "sentinel", "photo"]:
            exists = bool(row.get(f"{prefix}_exists", False))
            has_issues = bool(row.get(f"{prefix}_has_issues", True))
            if not exists:
                codes.append(f"{prefix}_missing")
            elif has_issues:
                codes.append(f"{prefix}_issue")
        if not bool(row.get("grid_100m_has_majority_formation", False)):
            codes.append("grid_100m_missing_majority_formation")
        if not bool(row.get("grid_10m_has_majority_formation", False)):
            codes.append("grid_10m_missing_majority_formation")
        blocking.append(join_codes(codes))
    table["record_blocking_issue_codes"] = blocking

    table["record_status"] = "partial"
    fully_validated = (
        table["ready_for_general_analysis"]
        & table["ready_for_formation_analysis_100m"]
        & table["ready_for_formation_analysis_10m"]
    )
    table.loc[fully_validated, "record_status"] = "validated"
    no_valid_core = (
        table["metadata_status"].eq("has_issues")
        & table["sound_status"].isin({"missing", "has_issues"})
        & table["weather_point_status"].isin({"missing", "has_issues"})
        & table["sentinel_status"].isin({"missing", "has_issues"})
    )
    table.loc[no_valid_core, "record_status"] = "has_issues"

    prior_release = table["release_status"].astype("string").str.lower()
    table["release_status"] = "not_started"
    table.loc[table["record_status"].eq("validated"), "release_status"] = (
        "manual_review_required"
    )
    table.loc[prior_release.eq("approved"), "release_status"] = "approved"
    return table


STATUS_EVENT_COLUMNS = [
    "event_utc",
    "workflow_run_id",
    "dawn_chorus_id",
    "field",
    "previous_value",
    "current_value",
]


def append_status_events(
    config: dict[str, Any],
    previous: pd.DataFrame,
    current: pd.DataFrame,
    now: str,
    partial_update: bool = False,
) -> int:
    configured = config.get("pipeline_control", {}).get("status_event_csv")
    event_path = (
        Path(configured)
        if configured
        else processed_root_from_config(config) / "step_0_control" / "status_events.csv"
    )
    run_id = workflow_run_id()
    previous_by_id = (
        previous.drop_duplicates("dawn_chorus_id", keep="last").set_index(
            "dawn_chorus_id",
            drop=False,
        )
        if not previous.empty
        else pd.DataFrame()
    )
    current_by_id = current.drop_duplicates("dawn_chorus_id", keep="last").set_index(
        "dawn_chorus_id",
        drop=False,
    )
    previous_ids = set(previous_by_id.index) if not previous.empty else set()
    current_ids = set(current_by_id.index)
    events: list[dict[str, str]] = []

    for dawn_id in sorted(current_ids - previous_ids):
        events.append(
            {
                "event_utc": now,
                "workflow_run_id": run_id,
                "dawn_chorus_id": str(dawn_id),
                "field": "record_lifecycle",
                "previous_value": "",
                "current_value": "added",
            }
        )
    if not partial_update:
        for dawn_id in sorted(previous_ids - current_ids):
            events.append(
                {
                    "event_utc": now,
                    "workflow_run_id": run_id,
                    "dawn_chorus_id": str(dawn_id),
                    "field": "record_lifecycle",
                    "previous_value": "present",
                    "current_value": "deleted",
                }
            )

    tracked = [
        "metadata_status",
        "sound_status",
        "photo_status",
        "sentinel_status",
        "weather_point_status",
        "formation_100m_status",
        "formation_10m_status",
        "bioacoustic_status",
        "record_status",
        "release_status",
        "ready_for_general_analysis",
        "ready_for_formation_analysis_100m",
        "ready_for_formation_analysis_10m",
        "ready_for_multimodal_analysis",
        "ready_for_bioacoustic_analysis",
        "record_blocking_issue_codes",
    ]
    for dawn_id in sorted(current_ids & previous_ids):
        old = previous_by_id.loc[dawn_id]
        new = current_by_id.loc[dawn_id]
        for field in tracked:
            old_value = "" if field not in old or pd.isna(old[field]) else str(old[field])
            new_value = "" if field not in new or pd.isna(new[field]) else str(new[field])
            if old_value != new_value:
                events.append(
                    {
                        "event_utc": now,
                        "workflow_run_id": run_id,
                        "dawn_chorus_id": str(dawn_id),
                        "field": field,
                        "previous_value": old_value,
                        "current_value": new_value,
                    }
                )

    existing = read_csv_optional(event_path, dtype="string")
    additions = pd.DataFrame(events, columns=STATUS_EVENT_COLUMNS)
    combined = pd.concat([existing, additions], ignore_index=True)
    for column in STATUS_EVENT_COLUMNS:
        if column not in combined.columns:
            combined[column] = ""
    atomic_write_csv(combined[STATUS_EVENT_COLUMNS], event_path)
    return len(events)


def output_paths(config: dict[str, Any], config_path: Path) -> tuple[Path, Path, Path]:
    root = config_path.resolve().parents[0]
    section = config.get("master_table", {})
    csv_path = Path(section.get("output_csv", root / "Bio_O_Ton_Master.csv"))
    parquet_path = Path(section.get("output_parquet", root / "Bio_O_Ton_Master.parquet"))
    summary_path = Path(section.get("summary_json", root / "Bio_O_Ton_Master_summary.json"))
    return csv_path, parquet_path, summary_path


@contextlib.contextmanager
def mastertable_write_lock(output_csv: Path):
    """Serialize regular Slurm and optional in-step batch master updates."""
    lock_path = output_csv.with_suffix(output_csv.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            import fcntl
        except ImportError:
            # Horeka runs on Linux and uses fcntl. Local Windows tests do not
            # run concurrent writers, so a no-op lock is sufficient there.
            yield
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            try:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
        finally:
            handle.close()


def write_parquet_optional(table: pd.DataFrame, path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        table.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(path)
        return True
    except Exception as exc:
        print(f"WARNING: Could not write parquet output {path}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        now = utc_now_iso()
        output_csv, output_parquet, summary_json = output_paths(config, args.config)
        with mastertable_write_lock(output_csv):
            if execution_phase() == "bioacoustics":
                write_bioacoustic_master(config, output_csv, output_parquet, summary_json, now)
                return 0
            previous_master = read_previous_master(output_csv)
            selected_ids: set[str] | None = None
            if args.ids_file is not None:
                if not args.ids_file.is_file():
                    raise FileNotFoundError(f"Master update ID file not found: {args.ids_file}")
                selected_ids = read_ids_file(args.ids_file)

            table = build_base_table(config, output_csv, now)
            guard_source_population(table['dawn_chorus_id'],
                previous_master.get('dawn_chorus_id', pd.Series(dtype=str)),
                config.get('metadata_extraction', {}))
            table = restrict_to_ids(table, selected_ids)
            # Deletion-only updates have no domains to recompute.
            if not table.empty:
                try:
                    require_point_coverage(table, config)
                    ten_path = config.get('susi_10m_products', {}).get('final_parquet')
                    if ten_path and not Path(ten_path).is_file():
                        raise ValueError(f'FORMATION_10M_MISSING: {ten_path}; existing master retained.')
                except ValueError:
                    if not getattr(args, 'allow_deferred_spatial', False):
                        raise
                    print('MASTER_UPDATE_DEFERRED: Step 2.2 incomplete; existing master retained. Final update requires complete coverage.')
                    return 0
                if args.preserve_existing_nonformation_domains:
                    table = add_preserved_nonformation_domains(
                        table, previous_master, config
                    )
                else:
                    table = add_media_status(table, config, "audio_inventory", "sound")
                    table = add_media_status(table, config, "photo_inventory", "photo")
                    table = add_bioacoustic_status(table, config)
                    table = add_sentinel_status(table, config)
                    table = add_weather_point_status(table, config)
                    table = add_weather_raster_status(table, config)
                table = add_100m_formation(table, config)
                table = add_10m_formation(table, config)
                if not args.preserve_existing_nonformation_domains:
                    table = add_formation_variant_status(table, config)
                table = add_agreement_and_ready_flags(table)

            for column in MASTER_COLUMNS:
                if column not in table.columns:
                    table[column] = pd.NA
            updated_rows = table[MASTER_COLUMNS].copy()
            replace_ids = selected_ids
            if replace_ids is None:
                replace_ids = (
                    set(previous_master["dawn_chorus_id"].astype(str))
                    if "dawn_chorus_id" in previous_master else set()
                )
            table = merge_master_rows(previous_master, updated_rows, replace_ids=replace_ids)
            for column in MASTER_COLUMNS:
                if column not in table.columns:
                    table[column] = pd.NA
            table = table[MASTER_COLUMNS].drop_duplicates(
                "dawn_chorus_id",
                keep="last",
            ).sort_values("dawn_chorus_id", key=lambda s: pd.to_numeric(s, errors="coerce"))

            # Recompute across retained AND updated rows: new neighbors can flag old IDs.
            flags = proximity_flags(table, config.get("proximity_review", {}))
            for column in FLAG_COLUMNS:
                table[column] = flags[column]
            table["mastertable_schema_version"] = SCHEMA_VERSION

            atomic_write_csv(table, output_csv)
            parquet_written = write_parquet_optional(table, output_parquet)
            event_previous = restrict_to_ids(previous_master, selected_ids)
            status_events_written = append_status_events(
                config,
                event_previous,
                updated_rows,
                now,
                # Both sides already contain only the requested scope. Missing
                # current rows are real deletions, even for an incremental run.
                partial_update=False,
            )

        summary = {
            "schema_version": SCHEMA_VERSION,
            "workflow_run_id": workflow_run_id(),
            "created_utc": now,
            "rows": int(len(table)),
            "rows_updated": int(len(updated_rows)),
            "incremental_update": selected_ids is not None,
            "ids_file": str(args.ids_file) if args.ids_file else "",
            "output_csv": str(output_csv),
            "output_parquet": str(output_parquet) if parquet_written else "",
            "processed_root": str(processed_root_from_config(config)),
            "ready_for_general_analysis": int(table["ready_for_general_analysis"].sum()),
            "ready_for_formation_analysis_100m": int(table["ready_for_formation_analysis_100m"].sum()),
            "ready_for_formation_analysis_10m": int(table["ready_for_formation_analysis_10m"].sum()),
            "ready_for_multimodal_analysis": int(table["ready_for_multimodal_analysis"].sum()),
            "ready_for_bioacoustic_analysis": int(table["ready_for_bioacoustic_analysis"].sum()),
            "status_events_written": status_events_written,
            "proximity_review": {
                "algorithm": "spherical_distance_utc_connected_components_v1",
                "thresholds": {**{"duplicate_distance_m": 10, "duplicate_seconds": 300,
                                   "cluster_distance_m": 50, "cluster_seconds": 1800},
                               **config.get("proximity_review", {})},
                "duplicate_candidate_rows": int(table["duplicate_candidate"].sum()),
                "duplicate_pairs": int(table["duplicate_neighbor_count"].sum() // 2),
                "clustered_rows": int((table["spatiotemporal_cluster_size"] > 1).sum()),
                "unchecked_rows": int((table["proximity_check_status"] != "checked").sum()),
            },
            "record_status_counts": {
                str(key): int(value)
                for key, value in table["record_status"].value_counts(dropna=False).items()
            },
            "release_status_counts": {
                str(key): int(value)
                for key, value in table["release_status"].value_counts(dropna=False).items()
            },
        }
        atomic_write_json(summary_json, summary)

        print(f"Mastertable rows                  : {len(table):,}")
        print(f"Rows updated                      : {len(updated_rows):,}")
        print(f"Ready general analysis            : {summary['ready_for_general_analysis']:,}")
        print(f"Ready formation analysis 100m     : {summary['ready_for_formation_analysis_100m']:,}")
        print(f"Ready formation analysis 10m      : {summary['ready_for_formation_analysis_10m']:,}")
        print(f"Ready multimodal analysis         : {summary['ready_for_multimodal_analysis']:,}")
        print(f"Ready bioacoustic analysis        : {summary['ready_for_bioacoustic_analysis']:,}")
        print(f"Status events written             : {status_events_written:,}")
        print(f"CSV                               : {output_csv}")
        if parquet_written:
            print(f"Parquet                           : {output_parquet}")
        print(f"Summary                           : {summary_json}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 7_0 master table update: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

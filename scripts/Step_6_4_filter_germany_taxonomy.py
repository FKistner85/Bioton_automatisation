#!/usr/bin/env python3
"""Step 6_4: Harmonise taxonomy and annotate Germany/season plausibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common import atomic_write_json, load_config, utc_now_iso
from common import file_fingerprint
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    atomic_write_parquet,
    bio_config,
    configured_models,
    normalise_id,
    output_path,
)


ALLOWLIST_COLUMNS = [
    "species_scientific",
    "accepted_scientific_name",
    "taxon_id",
    "taxon_group",
    "present_in_germany",
    "start_month",
    "end_month",
]
FILTER_OUTPUT_COLUMNS = [
    "schema_version",
    "dawn_chorus_id",
    "audio_fingerprint",
    "model",
    "model_fingerprint",
    "work_key",
    "taxon_scope",
    "segment_index",
    "segment_start_seconds",
    "segment_end_seconds",
    "species_raw",
    "species_scientific",
    "score_raw",
    "score",
    "rank_within_segment",
    "prediction_status",
    "recording_month",
    "accepted_scientific_name",
    "taxon_id",
    "taxon_group_harmonised",
    "germany_plausibility",
    "season_plausibility",
    "plausibility_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def read_allowlist(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame(columns=ALLOWLIST_COLUMNS)
    frame = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    missing = {"species_scientific"} - set(frame.columns)
    if missing:
        raise KeyError(f"Taxonomy allowlist missing columns: {sorted(missing)}")
    for column in ALLOWLIST_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[ALLOWLIST_COLUMNS].drop_duplicates("species_scientific", keep="last")


def month_in_window(month: int, start: int | None, end: int | None) -> bool | None:
    if start is None or end is None:
        return None
    if start <= end:
        return start <= month <= end
    return month >= start or month <= end


def apply_filter(
    predictions: pd.DataFrame,
    allowlist: pd.DataFrame,
    metadata: pd.DataFrame,
) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(columns=FILTER_OUTPUT_COLUMNS)
    result = predictions.copy()
    result["dawn_chorus_id"] = result["dawn_chorus_id"].map(normalise_id)
    if not metadata.empty:
        metadata = metadata.copy()
        metadata["dawn_chorus_id"] = metadata["dawn_chorus_id"].map(normalise_id)
        datetime_column = "datetime_local" if "datetime_local" in metadata.columns else "datetime"
        metadata["recording_month"] = pd.to_datetime(
            metadata.get(datetime_column), errors="coerce"
        ).dt.month
        result = result.merge(
            metadata[["dawn_chorus_id", "recording_month"]].drop_duplicates("dawn_chorus_id"),
            on="dawn_chorus_id",
            how="left",
        )
    else:
        result["recording_month"] = pd.NA

    if allowlist.empty:
        result["accepted_scientific_name"] = result["species_scientific"]
        result["taxon_id"] = ""
        result["taxon_group_harmonised"] = result.get("taxon_scope", "")
        result["germany_plausibility"] = "not_evaluated"
        result["season_plausibility"] = "not_evaluated"
        result["plausibility_status"] = "not_evaluated"
        return result

    allow = allowlist.rename(columns={"taxon_group": "taxon_group_harmonised"})
    result = result.merge(allow, on="species_scientific", how="left")
    result["accepted_scientific_name"] = result["accepted_scientific_name"].fillna(
        result["species_scientific"]
    )
    present = result["present_in_germany"].astype(str).str.lower()
    result["germany_plausibility"] = "not_in_reference"
    result.loc[present.isin({"true", "1", "yes", "y"}), "germany_plausibility"] = "accepted"
    result.loc[present.isin({"false", "0", "no", "n"}), "germany_plausibility"] = "outside_reference"

    season_status: list[str] = []
    for row in result.to_dict("records"):
        month = pd.to_numeric(row.get("recording_month"), errors="coerce")
        start = pd.to_numeric(row.get("start_month"), errors="coerce")
        end = pd.to_numeric(row.get("end_month"), errors="coerce")
        if pd.isna(month) or pd.isna(start) or pd.isna(end):
            season_status.append("not_evaluated")
            continue
        season_status.append(
            "accepted"
            if month_in_window(int(month), int(start), int(end))
            else "outside_season"
        )
    result["season_plausibility"] = season_status
    result["plausibility_status"] = "accepted"
    result.loc[
        result["germany_plausibility"].ne("accepted")
        | result["season_plausibility"].isin({"outside_season"}),
        "plausibility_status",
    ] = "flagged"
    result.loc[
        result["germany_plausibility"].eq("not_in_reference"),
        "plausibility_status",
    ] = "not_evaluated"
    return result


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        section = bio_config(config)
        allowlist_path = Path(str(section.get("taxonomy_allowlist_csv", "")))
        allowlist = read_allowlist(allowlist_path)
        metadata_path = Path(
            section.get(
                "metadata_csv",
                Path(config["status_dir"]) / "dawnchorus_metadata_clean.csv",
            )
        )
        metadata = (
            pd.read_csv(metadata_path, low_memory=False, encoding="utf-8-sig")
            if metadata_path.is_file()
            else pd.DataFrame()
        )
        raw_root = output_path(config, "raw_prediction_dir")
        target_root = output_path(config, "filtered_prediction_dir")
        rows_by_model: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for model in configured_models(config):
            name = model["name"]
            source = raw_root / f"model={name}" / "predictions.parquet"
            predictions = pd.read_parquet(source) if source.is_file() else pd.DataFrame()
            filtered = apply_filter(predictions, allowlist, metadata)
            atomic_write_parquet(
                filtered,
                target_root / f"model={name}" / "predictions.parquet",
            )
            rows_by_model[name] = int(len(filtered))
            if "plausibility_status" in filtered.columns:
                for key, value in filtered["plausibility_status"].value_counts().items():
                    status_counts[str(key)] = status_counts.get(str(key), 0) + int(value)
        atomic_write_json(
            output_path(config, "taxonomy_state_json"),
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "created_utc": utc_now_iso(),
                "status": "complete",
                "allowlist_path": str(allowlist_path),
                "allowlist_rows": int(len(allowlist)),
                "allowlist_fingerprint": (
                    file_fingerprint(allowlist_path)
                    if allowlist_path.is_file()
                    else {}
                ),
                "prediction_rows_by_model": rows_by_model,
                "plausibility_status_counts": status_counts,
            },
        )
        print(f"Taxonomy reference rows: {len(allowlist):,}")
        print(f"Filtered prediction rows: {sum(rows_by_model.values()):,}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 6_4 Germany taxonomy filter: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

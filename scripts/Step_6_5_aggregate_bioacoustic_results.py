#!/usr/bin/env python3
"""Step 6_5: Aggregate segment/model predictions to Dawn Chorus recordings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from common import atomic_write_csv, atomic_write_json, load_config, utc_now_iso
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    atomic_write_parquet,
    configured_models,
    output_path,
    read_parquet_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def aggregate_predictions(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if predictions.empty:
        species_columns = [
            "dawn_chorus_id",
            "accepted_scientific_name",
            "model_support",
            "max_score",
            "detection_segments",
            "taxon_group",
            "recording_species_rank",
        ]
        return (
            pd.DataFrame(
                columns=[
                    "dawn_chorus_id",
                    "bioacoustic_species_count",
                    "bird_species_count",
                    "nonbird_species_count",
                    "bioacoustic_max_confidence",
                    "top_species_scientific",
                    "top_species_model_support",
                ]
            ),
            pd.DataFrame(columns=species_columns),
        )
    frame = predictions.copy()
    usable = ~frame["plausibility_status"].astype(str).eq("flagged")
    frame = frame[usable]
    species_column = "accepted_scientific_name"
    frame[species_column] = frame[species_column].fillna(frame["species_scientific"])
    species = (
        frame.groupby(["dawn_chorus_id", species_column, "model"], as_index=False)
        .agg(
            max_score=("score", "max"),
            detection_segments=("segment_index", "nunique"),
            taxon_group=("taxon_group_harmonised", "first"),
            plausibility_status=("plausibility_status", "first"),
        )
    )
    consensus = (
        species.groupby(["dawn_chorus_id", species_column], as_index=False)
        .agg(
            model_support=("model", "nunique"),
            max_score=("max_score", "max"),
            detection_segments=("detection_segments", "sum"),
            taxon_group=("taxon_group", "first"),
        )
        .sort_values(
            ["dawn_chorus_id", "model_support", "max_score"],
            ascending=[True, False, False],
        )
    )
    consensus["recording_species_rank"] = consensus.groupby("dawn_chorus_id").cumcount() + 1
    rows = []
    for dawn_id, group in consensus.groupby("dawn_chorus_id", sort=False):
        top = group.iloc[0]
        groups = group["taxon_group"].fillna("").astype(str).str.lower()
        bird_mask = groups.str.contains("bird")
        rows.append(
            {
                "dawn_chorus_id": str(dawn_id),
                "bioacoustic_species_count": int(group[species_column].nunique()),
                "bird_species_count": int(group.loc[bird_mask, species_column].nunique()),
                "nonbird_species_count": int(group.loc[~bird_mask, species_column].nunique()),
                "bioacoustic_max_confidence": float(group["max_score"].max()),
                "top_species_scientific": str(top[species_column]),
                "top_species_model_support": int(top["model_support"]),
            }
        )
    return pd.DataFrame(rows), consensus


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        root = output_path(config, "filtered_prediction_dir")
        files = [
            root / f"model={model['name']}" / "predictions.parquet"
            for model in configured_models(config)
        ]
        predictions = read_parquet_files(files)
        summary, species = aggregate_predictions(predictions)
        atomic_write_csv(summary, output_path(config, "recording_summary_csv"))
        atomic_write_parquet(summary, output_path(config, "recording_summary_parquet"))
        atomic_write_parquet(species, output_path(config, "recording_species_parquet"))
        atomic_write_json(
            output_path(config, "aggregation_state_json"),
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "created_utc": utc_now_iso(),
                "status": "complete",
                "prediction_rows": int(len(predictions)),
                "recording_rows": int(len(summary)),
                "recording_species_rows": int(len(species)),
            },
        )
        print(f"Recording summaries: {len(summary):,}")
        print(f"Recording-species rows: {len(species):,}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 6_5 aggregation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Step 6_3: Normalise and threshold native Bacpipe classifier predictions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common import atomic_write_json, load_config, utc_now_iso
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    atomic_write_parquet,
    bio_config,
    configured_models,
    output_path,
    read_parquet_files,
    sanitise_species_name,
)

NORMALISED_COLUMNS = [
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
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def normalise_model(frame: pd.DataFrame, threshold: float, top_k: int) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=NORMALISED_COLUMNS)
    frame = frame.copy()
    frame["species_scientific"] = frame["species_raw"].map(sanitise_species_name)
    frame["score"] = pd.to_numeric(frame["score_raw"], errors="coerce")
    frame = frame[
        frame["species_scientific"].ne("")
        & frame["score"].notna()
        & frame["score"].ge(threshold)
    ]
    keys = ["dawn_chorus_id", "model", "segment_index"]
    frame = frame.sort_values(keys + ["score"], ascending=[True, True, True, False])
    frame["rank_within_segment"] = frame.groupby(keys).cumcount() + 1
    frame = frame[frame["rank_within_segment"] <= top_k]
    frame["prediction_status"] = "raw_model_prediction"
    return frame[NORMALISED_COLUMNS]


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        section = bio_config(config)
        source_root = output_path(config, "native_prediction_dir")
        target_root = output_path(config, "raw_prediction_dir")
        worklist = pd.read_parquet(output_path(config, "worklist_parquet"))
        state_path = output_path(config, "normalisation_state_json")
        threshold = float(section.get("classifier_threshold", 0.1))
        top_k = int(section.get("classifier_top_k", 5))
        rows_by_model: dict[str, int] = {}
        for model in configured_models(config):
            name = model["name"]
            files = sorted((source_root / f"model={name}").glob("*.parquet"))
            native = read_parquet_files(files)
            valid_work_keys = set(
                worklist.loc[
                    worklist["model"].astype(str).eq(name),
                    "work_key",
                ].astype(str)
            )
            if not native.empty:
                if "work_key" not in native.columns:
                    native = native.iloc[0:0]
                else:
                    native = native[native["work_key"].astype(str).isin(valid_work_keys)]
            normalised = normalise_model(native, threshold, top_k)
            target = target_root / f"model={name}" / "predictions.parquet"
            atomic_write_parquet(normalised, target)
            rows_by_model[name] = int(len(normalised))
        atomic_write_json(
            state_path,
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "created_utc": utc_now_iso(),
                "status": "complete",
                "classifier_threshold": threshold,
                "classifier_top_k": top_k,
                "prediction_rows_by_model": rows_by_model,
            },
        )
        print(f"Normalised predictions: {sum(rows_by_model.values()):,}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 6_3 prediction normalisation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

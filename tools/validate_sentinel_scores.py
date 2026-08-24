#!/usr/bin/env python3
"""Recompute a deterministic score sample and compare it to the reference CSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sentinel2_gee import (  # noqa: E402
    SCORE_COLUMNS,
    _gee_credentials,
    atomic_write_csv,
    iter_score_chunks,
    normalise_id,
    read_metadata,
    read_scores,
)


def compare_score_frames(
    reference: pd.DataFrame,
    fresh: pd.DataFrame,
    *,
    score_atol: float,
) -> pd.DataFrame:
    left = reference.copy()
    right = fresh.copy()
    left["DC_id"] = left["DC_id"].map(normalise_id)
    right["DC_id"] = right["DC_id"].map(normalise_id)
    left = left.drop_duplicates("DC_id", keep="last")
    right = right.drop_duplicates("DC_id", keep="last")
    keep = [column for column in SCORE_COLUMNS if column in right]
    merged = left.merge(
        right[keep],
        on="DC_id",
        how="left",
        suffixes=("_reference", "_fresh"),
        validate="one_to_one",
    )
    reference_score = pd.to_numeric(merged.get("score_reference"), errors="coerce")
    fresh_score = pd.to_numeric(merged.get("score_fresh"), errors="coerce")
    merged["score_delta"] = (fresh_score - reference_score).abs()
    merged["score_match"] = np.isclose(
        reference_score,
        fresh_score,
        rtol=0.0,
        atol=score_atol,
        equal_nan=True,
    )
    if "best_index_reference" in merged and "best_index_fresh" in merged:
        reference_index = merged["best_index_reference"].fillna("").astype(str)
        fresh_index = merged["best_index_fresh"].fillna("").astype(str)
        # Older reference CSVs without best_index are still valid score
        # references; when present, the selected image must match exactly.
        merged["best_index_match"] = reference_index.eq("") | reference_index.eq(
            fresh_index
        )
    else:
        merged["best_index_match"] = True
    merged["row_match"] = merged["score_match"] & merged["best_index_match"]
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.horeka.json")
    parser.add_argument("--reference-score-csv", type=Path, default=None)
    parser.add_argument("--metadata-csv", type=Path, default=None)
    parser.add_argument("--report-csv", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260822)
    parser.add_argument(
        "--reference-min-date",
        type=str,
        default=None,
        help="Optional UTC lower bound applied to the reference datetime column.",
    )
    parser.add_argument("--score-atol", type=float, default=1e-12)
    parser.add_argument("--chunk-size", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config: dict[str, Any] = json.loads(args.config.read_text(encoding="utf-8"))
    settings = config["sentinel2_download"]
    reference_path = args.reference_score_csv or Path(settings["score_csv"])
    metadata_path = args.metadata_csv or Path(settings["metadata_csv"])
    reference = read_scores(reference_path)
    metadata = read_metadata(metadata_path)
    available = reference[
        reference["DC_id"].isin(set(metadata["DC_id"]))
        & pd.to_numeric(reference["score"], errors="coerce").notna()
    ].copy()
    if args.reference_min_date:
        if "datetime" not in available:
            raise KeyError("Reference score CSV has no datetime column")
        reference_datetime = pd.to_datetime(
            pd.to_numeric(available["datetime"], errors="coerce"),
            unit="ms",
            utc=True,
            errors="coerce",
        )
        available = available[
            reference_datetime >= pd.Timestamp(args.reference_min_date, tz="UTC")
        ].copy()
    sample_size = max(1, int(args.sample_size))
    if len(available) < sample_size:
        raise RuntimeError(
            f"Only {len(available)} comparable reference scores; need {sample_size}"
        )
    sample = available.sample(n=sample_size, random_state=args.seed).sort_values(
        "DC_id", kind="stable"
    )
    sample_metadata = metadata[metadata["DC_id"].isin(set(sample["DC_id"]))].copy()

    try:
        import ee
    except ImportError as exc:
        raise RuntimeError("earthengine-api is not installed") from exc
    _gee_credentials(ee, settings, str(settings.get("gee_project", "bio-o-ton-gee")))
    frames = list(
        iter_score_chunks(ee, sample_metadata, chunk_size=max(1, args.chunk_size))
    )
    fresh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    report = compare_score_frames(sample, fresh, score_atol=max(0.0, args.score_atol))
    atomic_write_csv(args.report_csv, report)
    mismatches = int((~report["row_match"]).sum())
    max_delta = pd.to_numeric(report["score_delta"], errors="coerce").max()
    print(
        json.dumps(
            {
                "sample_size": len(report),
                "matches": len(report) - mismatches,
                "mismatches": mismatches,
                "score_atol": args.score_atol,
                "max_score_delta": None if pd.isna(max_delta) else float(max_delta),
                "report_csv": str(args.report_csv),
            },
            indent=2,
        )
    )
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())

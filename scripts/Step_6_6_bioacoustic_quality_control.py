#!/usr/bin/env python3
"""Step 6_6: Reconcile model completion and write per-ID bioacoustic QC."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from common import atomic_write_csv, atomic_write_json, load_config, utc_now_iso
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    configured_models,
    load_task_state,
    normalise_id,
    output_path,
)

QC_COMPACT_COLUMNS = [
    "dawn_chorus_id",
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
QC_DETAIL_COLUMNS = [
    "dawn_chorus_id",
    "model",
    "required_model",
    "model_complete",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def build_qc(
    worklist: pd.DataFrame,
    states: list[dict[str, Any]],
    models: list[dict[str, Any]],
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected = (
        worklist.groupby("dawn_chorus_id")["model"].agg(lambda values: sorted(set(values))).to_dict()
        if not worklist.empty
        else {}
    )
    completed: dict[str, set[str]] = {}
    failures: dict[str, dict[str, str]] = {}
    for state in states:
        model = str(state.get("model", ""))
        for dawn_id in state.get("completed_ids", []):
            completed.setdefault(normalise_id(dawn_id), set()).add(model)
        for dawn_id, error in state.get("failed_by_id", {}).items():
            failures.setdefault(normalise_id(dawn_id), {})[model] = str(error)
    required_models = {model["name"] for model in models if model["required"]}
    summary_map = (
        summary.set_index("dawn_chorus_id").to_dict("index") if not summary.empty else {}
    )
    compact_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    for dawn_id, expected_models in sorted(
        expected.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0])
    ):
        done = completed.get(str(dawn_id), set())
        failed = failures.get(str(dawn_id), {})
        missing_required = sorted(required_models - done)
        issue_codes: list[str] = []
        if missing_required:
            issue_codes.append("required_models_incomplete")
        if failed:
            issue_codes.append("model_inference_failed")
        status = "validated" if not issue_codes else ("partial" if done else "failed")
        row = {
            "dawn_chorus_id": str(dawn_id),
            "bioacoustic_status": status,
            "bioacoustic_has_issues": bool(issue_codes),
            "bioacoustic_issue_codes": "|".join(issue_codes),
            "bioacoustic_models_expected": "|".join(sorted(expected_models)),
            "bioacoustic_models_complete": "|".join(sorted(done)),
            "bioacoustic_required_models_complete": not missing_required,
            "bioacoustic_inference_version": BIOACOUSTIC_SCHEMA_VERSION,
        }
        row.update(summary_map.get(str(dawn_id), {}))
        compact_rows.append(row)
        for model in sorted(set(expected_models) | set(failed)):
            detail_rows.append(
                {
                    "dawn_chorus_id": str(dawn_id),
                    "model": model,
                    "required_model": model in required_models,
                    "model_complete": model in done,
                    "error": failed.get(model, ""),
                }
            )
    return (
        pd.DataFrame(compact_rows, columns=QC_COMPACT_COLUMNS),
        pd.DataFrame(detail_rows, columns=QC_DETAIL_COLUMNS),
    )


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        worklist_path = output_path(config, "worklist_parquet")
        worklist = pd.read_parquet(worklist_path) if worklist_path.is_file() else pd.DataFrame()
        state_files = sorted(output_path(config, "inference_state_dir").glob("model=*/shard=*.json"))
        states = [load_task_state(path) for path in state_files]
        summary_path = output_path(config, "recording_summary_csv")
        summary = (
            pd.read_csv(summary_path, dtype={"dawn_chorus_id": "string"}, low_memory=False)
            if summary_path.is_file()
            else pd.DataFrame()
        )
        if not summary.empty:
            summary["dawn_chorus_id"] = summary["dawn_chorus_id"].map(normalise_id)
        compact, detailed = build_qc(worklist, states, configured_models(config), summary)
        atomic_write_csv(compact, output_path(config, "qc_compact_csv"))
        atomic_write_csv(detailed, output_path(config, "qc_detailed_csv"))
        status_counts = (
            {str(key): int(value) for key, value in compact["bioacoustic_status"].value_counts().items()}
            if not compact.empty
            else {}
        )
        atomic_write_json(
            output_path(config, "qc_state_json"),
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "created_utc": utc_now_iso(),
                "status": "complete",
                "worklist_rows": int(len(worklist)),
                "state_files": int(len(state_files)),
                "recording_rows": int(len(compact)),
                "status_counts": status_counts,
            },
        )
        print(f"Bioacoustic QC rows: {len(compact):,}")
        print(f"Status counts      : {json.dumps(status_counts, sort_keys=True)}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 6_6 bioacoustic QC: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

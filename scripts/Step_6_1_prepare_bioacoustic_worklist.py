#!/usr/bin/env python3
"""Step 6_1: Build the eligible, fingerprinted bioacoustic audio worklist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from common import atomic_write_csv, atomic_write_json, load_config, read_ids_file, utc_now_iso
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    atomic_write_parquet,
    audio_fingerprint,
    bio_config,
    configured_models,
    model_fingerprint,
    normalise_id,
    output_path,
    shard_for_id,
    truthy,
    work_key,
)

WORKLIST_COLUMNS = [
    "schema_version",
    "dawn_chorus_id",
    "source_path",
    "source_relative_path",
    "audio_fingerprint",
    "sample_rate_hz",
    "duration_seconds",
    "model",
    "model_fingerprint",
    "required_model",
    "classifier_available",
    "taxon_scope",
    "segment_seconds",
    "shard_index",
    "work_key",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def build_worklist(
    inventory: pd.DataFrame,
    config: dict,
    selected_ids: set[str] | None = None,
    registry_fingerprints: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    section = bio_config(config)
    models = configured_models(config)
    shard_count = int(section.get("shard_count", 16))
    inventory = inventory.copy()
    inventory["dawn_chorus_id"] = inventory["dawn_chorus_id"].map(normalise_id)
    inventory = inventory[inventory["dawn_chorus_id"] != ""]
    if selected_ids is not None:
        inventory = inventory[inventory["dawn_chorus_id"].isin(selected_ids)]

    valid = pd.Series(True, index=inventory.index)
    for column in ["probe_ok", "decode_ok", "duration_ok"]:
        if column in inventory.columns:
            valid &= inventory[column].map(truthy)
    if "has_issues" in inventory.columns:
        valid &= ~inventory["has_issues"].map(truthy)
    valid &= inventory["source_path"].astype(str).map(lambda value: Path(value).is_file())

    rejected = inventory.loc[~valid].copy()
    rejected["eligibility_status"] = "rejected"
    rejected["eligibility_issue_codes"] = (
        rejected["issues"].astype(str) if "issues" in rejected.columns else "inventory_issue"
    )
    accepted = inventory.loc[valid].copy()
    mtime_values = (
        accepted["mtime_ns"]
        if "mtime_ns" in accepted.columns
        else pd.Series(0, index=accepted.index)
    )
    accepted["_mtime"] = pd.to_numeric(mtime_values, errors="coerce").fillna(0)
    accepted = accepted.sort_values(
        ["dawn_chorus_id", "_mtime", "source_path"],
        ascending=[True, False, True],
    )
    duplicate_audio = accepted[accepted.duplicated("dawn_chorus_id", keep="first")].copy()
    if not duplicate_audio.empty:
        duplicate_audio["eligibility_status"] = "rejected"
        duplicate_audio["eligibility_issue_codes"] = "duplicate_valid_audio_for_id"
        rejected = pd.concat([rejected, duplicate_audio], ignore_index=True, sort=False)
    accepted = accepted.drop_duplicates("dawn_chorus_id", keep="first").drop(columns=["_mtime"])
    accepted["audio_fingerprint"] = accepted.apply(audio_fingerprint, axis=1)

    rows: list[dict] = []
    for row in accepted.to_dict("records"):
        dawn_id = str(row["dawn_chorus_id"])
        for model in models:
            model_fp = (registry_fingerprints or {}).get(
                model["name"],
                model_fingerprint(config, model),
            )
            rows.append(
                {
                    "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                    "dawn_chorus_id": dawn_id,
                    "source_path": str(row["source_path"]),
                    "source_relative_path": str(row.get("source_relative_path", "")),
                    "audio_fingerprint": str(row["audio_fingerprint"]),
                    "sample_rate_hz": pd.to_numeric(row.get("sample_rate_hz"), errors="coerce"),
                    "duration_seconds": pd.to_numeric(row.get("duration_seconds"), errors="coerce"),
                    "model": model["name"],
                    "model_fingerprint": model_fp,
                    "required_model": bool(model["required"]),
                    "classifier_available": bool(model["classifier"]),
                    "taxon_scope": str(model.get("taxon_scope", "")),
                    "segment_seconds": float(model["segment_seconds"]),
                    "shard_index": shard_for_id(dawn_id, shard_count),
                    "work_key": work_key(dawn_id, str(row["audio_fingerprint"]), model_fp),
                }
            )
    worklist = pd.DataFrame(rows, columns=WORKLIST_COLUMNS)
    return worklist, rejected


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        section = bio_config(config)
        inventory_path = Path(
            section.get(
                "audio_inventory_detailed_csv",
                config["audio_inventory"]["detailed_log"],
            )
        )
        if not inventory_path.is_file():
            raise FileNotFoundError(f"Audio inventory not found: {inventory_path}")
        inventory = pd.read_csv(inventory_path, low_memory=False, encoding="utf-8-sig")
        selected = read_ids_file(args.ids_file) if args.ids_file else None
        registry_path = output_path(config, "model_registry_json")
        if not registry_path.is_file():
            raise FileNotFoundError(
                f"Bioacoustic model registry not found: {registry_path}"
            )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("status") == "failed":
            raise RuntimeError("Bioacoustic model preflight registry has failed status.")
        registry_fingerprints = {
            str(model["name"]): str(model["model_fingerprint"])
            for model in registry.get("models", [])
            if model.get("name") and model.get("model_fingerprint")
        }
        worklist, rejected = build_worklist(
            inventory,
            config,
            selected,
            registry_fingerprints,
        )
        worklist_csv = output_path(config, "worklist_csv")
        worklist_parquet = output_path(config, "worklist_parquet")
        rejected_csv = output_path(config, "rejected_audio_csv")
        state_path = output_path(config, "worklist_state_json")

        if selected is not None and not args.force:
            if worklist_parquet.is_file():
                previous_worklist = pd.read_parquet(worklist_parquet)
                previous_worklist["dawn_chorus_id"] = previous_worklist[
                    "dawn_chorus_id"
                ].map(normalise_id)
                untouched = previous_worklist[
                    ~previous_worklist["dawn_chorus_id"].isin(selected)
                ]
                worklist = pd.concat(
                    [untouched, worklist],
                    ignore_index=True,
                    sort=False,
                ).drop_duplicates("work_key", keep="last")
            if rejected_csv.is_file():
                previous_rejected = pd.read_csv(
                    rejected_csv,
                    low_memory=False,
                    encoding="utf-8-sig",
                )
                if "dawn_chorus_id" in previous_rejected.columns:
                    previous_rejected["dawn_chorus_id"] = previous_rejected[
                        "dawn_chorus_id"
                    ].map(normalise_id)
                    untouched_rejected = previous_rejected[
                        ~previous_rejected["dawn_chorus_id"].isin(selected)
                    ]
                    rejected = pd.concat(
                        [untouched_rejected, rejected],
                        ignore_index=True,
                        sort=False,
                    )

        atomic_write_csv(worklist, worklist_csv)
        atomic_write_parquet(worklist, worklist_parquet)
        atomic_write_csv(rejected, rejected_csv)
        atomic_write_json(
            state_path,
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "created_utc": utc_now_iso(),
                "status": "complete",
                "inventory_path": str(inventory_path),
                "selected_ids_file": str(args.ids_file or ""),
                "eligible_recording_model_rows": int(len(worklist)),
                "eligible_recordings": int(worklist["dawn_chorus_id"].nunique()) if not worklist.empty else 0,
                "rejected_recordings": int(rejected["dawn_chorus_id"].nunique()) if not rejected.empty else 0,
                "models": [model["name"] for model in configured_models(config)],
            },
        )
        print(f"Eligible recording-model rows: {len(worklist):,}")
        print(f"Rejected audio rows           : {len(rejected):,}")
        print(f"Worklist                      : {worklist_parquet}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 6_1 worklist: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

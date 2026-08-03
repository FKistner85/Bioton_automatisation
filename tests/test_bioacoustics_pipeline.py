#!/usr/bin/env python3
"""Synthetic regression tests for Step 6 bioacoustic transformations."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Step_6_1_prepare_bioacoustic_worklist import build_worklist
import Step_6_2_generate_bioacoustic_embeddings as step62
from Step_6_2_generate_bioacoustic_embeddings import select_predictions
from Step_6_4_filter_germany_taxonomy import apply_filter
from Step_6_5_aggregate_bioacoustic_results import aggregate_predictions
from Step_6_6_bioacoustic_quality_control import build_qc
from Step_6_0_bioacoustic_model_preflight import (
    checkpoint_error_is_repairable,
    quarantine_checkpoint_trees,
)


def test_bioacoustic_data_flow() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        audio = root / "123_audio.wav"
        audio.write_bytes(b"synthetic-audio-placeholder")
        inventory = pd.DataFrame(
            [
                {
                    "dawn_chorus_id": "123",
                    "source_path": str(audio),
                    "source_relative_path": audio.name,
                    "size_bytes": audio.stat().st_size,
                    "mtime_ns": audio.stat().st_mtime_ns,
                    "sample_rate_hz": 48000,
                    "duration_seconds": 60,
                    "probe_ok": True,
                    "decode_ok": True,
                    "duration_ok": True,
                    "has_issues": False,
                    "issues": "",
                }
            ]
        )
        config = {
            "bioacoustics": {
                "bacpipe_version": "1.3.1",
                "preprocessing_version": "test",
                "classifier_threshold": 0.1,
                "classifier_top_k": 5,
                "shard_count": 4,
                "models": [
                    {
                        "name": "birdnet",
                        "required": True,
                        "classifier": True,
                        "taxon_scope": "birds",
                        "segment_seconds": 3,
                    },
                    {
                        "name": "perch_v2",
                        "required": True,
                        "classifier": True,
                        "taxon_scope": "multitaxon",
                        "segment_seconds": 5,
                    },
                ],
            }
        }
        worklist, rejected = build_worklist(inventory, config)
        assert len(worklist) == 2
        assert rejected.empty
        assert worklist["audio_fingerprint"].str.len().eq(64).all()
        assert worklist["work_key"].nunique() == 2

        predictions = pd.DataFrame(
            [
                {
                    "schema_version": "test",
                    "dawn_chorus_id": "123",
                    "audio_fingerprint": "a",
                    "model": "birdnet",
                    "model_fingerprint": "b",
                    "taxon_scope": "birds",
                    "segment_index": 0,
                    "segment_start_seconds": 0,
                    "segment_end_seconds": 3,
                    "species_raw": "Turdus merula",
                    "species_scientific": "Turdus merula",
                    "score_raw": 0.9,
                    "score": 0.9,
                    "rank_within_segment": 1,
                    "prediction_status": "raw_model_prediction",
                },
                {
                    "schema_version": "test",
                    "dawn_chorus_id": "123",
                    "audio_fingerprint": "a",
                    "model": "perch_v2",
                    "model_fingerprint": "c",
                    "taxon_scope": "multitaxon",
                    "segment_index": 0,
                    "segment_start_seconds": 0,
                    "segment_end_seconds": 5,
                    "species_raw": "Turdus merula",
                    "species_scientific": "Turdus merula",
                    "score_raw": 0.8,
                    "score": 0.8,
                    "rank_within_segment": 1,
                    "prediction_status": "raw_model_prediction",
                },
            ]
        )
        allowlist = pd.DataFrame(
            [
                {
                    "species_scientific": "Turdus merula",
                    "accepted_scientific_name": "Turdus merula",
                    "taxon_id": "gbif:2490719",
                    "taxon_group": "birds",
                    "present_in_germany": True,
                    "start_month": 1,
                    "end_month": 12,
                }
            ]
        )
        metadata = pd.DataFrame(
            [{"dawn_chorus_id": "123", "datetime_local": "2026-05-01T05:00:00"}]
        )
        filtered = apply_filter(predictions, allowlist, metadata)
        assert filtered["plausibility_status"].eq("accepted").all()
        summary, species = aggregate_predictions(filtered)
        assert summary.loc[0, "bioacoustic_species_count"] == 1
        assert summary.loc[0, "top_species_model_support"] == 2

        states = [
            {
                "model": "birdnet",
                "completed_ids": ["123"],
                "failed_by_id": {},
            },
            {
                "model": "perch_v2",
                "completed_ids": ["123"],
                "failed_by_id": {},
            },
        ]
        compact, detailed = build_qc(
            worklist,
            states,
            config["bioacoustics"]["models"],
            summary,
        )
        assert compact.loc[0, "bioacoustic_status"] == "validated"
        assert bool(compact.loc[0, "bioacoustic_required_models_complete"])
        assert len(detailed) == 2


def test_prediction_threshold_and_top_k() -> None:
    rows = [
        {
            "segment_index": 0,
            "species_raw": species,
            "score_raw": score,
        }
        for species, score in [
            ("Species A", 0.9),
            ("Species B", 0.8),
            ("Species C", 0.7),
            ("Species D", 0.05),
        ]
    ]
    selected = select_predictions(rows, threshold=0.1, top_k=2)
    assert [row["species_raw"] for row in selected] == ["Species A", "Species B"]
    assert all(row["score_raw"] >= 0.1 for row in selected)

    empty_summary, empty_species = aggregate_predictions(pd.DataFrame())
    assert "dawn_chorus_id" in empty_summary.columns
    assert "accepted_scientific_name" in empty_species.columns


def test_checkpoint_repair_helpers() -> None:
    assert checkpoint_error_is_repairable(
        "PytorchStreamReader failed finding central directory"
    )
    assert checkpoint_error_is_repairable(
        "File not found: birdnetv2.4.keras"
    )
    assert not checkpoint_error_is_repairable("unsupported model option")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "naturebeats").mkdir()
        (root / "beats").mkdir()
        (root / "naturebeats" / "naturebeats.pt").write_bytes(b"broken")
        (root / "beats" / "beats.pt").write_bytes(b"broken")
        moved = quarantine_checkpoint_trees(root, "naturebeats")
        assert len(moved) == 2
        assert not (root / "naturebeats").exists()
        assert not (root / "beats").exists()
        assert all(Path(path).exists() for path in moved)


def test_embedding_shard_verification_gate() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        worklist_path = root / "worklist.parquet"
        worklist_path.touch()
        state_root = root / "state"
        worklist = pd.DataFrame(
            [
                {
                    "dawn_chorus_id": "123",
                    "model": "birdnet",
                    "shard_index": 0,
                    "work_key": "work-123",
                }
            ]
        )
        config = {
            "bioacoustics": {
                "shard_count": 2,
                "worklist_parquet": str(worklist_path),
                "inference_state_dir": str(state_root),
                "models": [{"name": "birdnet", "required": True}],
            }
        }
        for shard_index in range(2):
            state_path = (
                state_root / "model=birdnet" / f"shard={shard_index:04d}.json"
            )
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "shard_count": 2,
                        "completed_work_keys": (
                            {"123": "work-123"} if shard_index == 0 else {}
                        ),
                        "failed_by_id": {},
                    }
                ),
                encoding="utf-8",
            )

        with patch.object(step62.pd, "read_parquet", return_value=worklist):
            assert step62.verify_shards(config) == 0
            broken_path = state_root / "model=birdnet" / "shard=0000.json"
            broken = json.loads(broken_path.read_text(encoding="utf-8"))
            broken["status"] = "partial"
            broken_path.write_text(json.dumps(broken), encoding="utf-8")
            assert step62.verify_shards(config) == 2


if __name__ == "__main__":
    test_bioacoustic_data_flow()
    test_prediction_threshold_and_top_k()
    test_checkpoint_repair_helpers()
    test_embedding_shard_verification_gate()
    print("test_bioacoustics_pipeline.py: OK")

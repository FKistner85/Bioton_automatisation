#!/usr/bin/env python3
"""Smoke tests for shared manifest helpers."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import (
    BATCH_STATUS_SCHEMA_VERSION,
    PROGRESS_SNAPSHOT_SCHEMA_VERSION,
    STEP_MANIFEST_SCHEMA_VERSION,
    atomic_write_json,
    finish_step_manifest,
    output_is_nonempty,
    start_step_manifest,
    write_batch_status,
    write_progress_snapshot,
)


def test_manifest_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        cfg = {
            "processed_root": str(root / "processed"),
        }
        input_file = root / "input.csv"
        input_file.write_text("id\n1\n", encoding="utf-8")
        output_file = root / "output.csv"
        output_file.write_text("id\n1\n", encoding="utf-8")

        manifest_path, manifest = start_step_manifest(
            cfg,
            "unit_step",
            config_path=root / "config.json",
            inputs=[input_file],
            outputs=[output_file],
            parameters={"mode": "test"},
            batch_count=1,
        )
        assert manifest_path.is_file()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == STEP_MANIFEST_SCHEMA_VERSION
        assert payload["status"] == "running"
        assert payload["input_fingerprints"][0]["exists"] is True

        finish_step_manifest(
            manifest_path,
            manifest,
            "complete",
            result={"rows": 1},
        )
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["status"] == "complete"
        assert payload["result"]["rows"] == 1

        batch_path = write_batch_status(
            root / "processed" / "_manifests" / "unit_step" / "batches",
            "batch 1",
            "complete",
            outputs=[output_file],
            result={"rows": 1},
        )
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        assert batch["schema_version"] == BATCH_STATUS_SCHEMA_VERSION
        assert batch["batch_id"] == "batch 1"
        assert batch["status"] == "complete"
        assert output_is_nonempty(output_file)

        progress_path = write_progress_snapshot(
            root / "progress.json",
            step_name="unit_step",
            total_batches=2,
            completed_batches=1,
        )
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        assert progress["schema_version"] == PROGRESS_SNAPSHOT_SCHEMA_VERSION
        assert progress["remaining_batches"] == 1


def test_atomic_json_replaces_file() -> None:
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "state.json"
        atomic_write_json(path, {"version": 1})
        atomic_write_json(path, {"version": 2})
        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}


if __name__ == "__main__":
    test_manifest_lifecycle()
    test_atomic_json_replaces_file()
    print("test_common_manifest.py: OK")

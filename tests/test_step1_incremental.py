#!/usr/bin/env python3
"""Synthetic regression test for changed-ID Step 1 upserts."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import Step_1_metadata_extraction as step1


def run_step(config: Path, ids_file: Path | None = None) -> None:
    argv = ["Step_1_metadata_extraction.py", "--config", str(config)]
    if ids_file is not None:
        argv.extend(["--ids-file", str(ids_file)])
    old_argv = sys.argv
    try:
        sys.argv = argv
        assert step1.main() == 0
    finally:
        sys.argv = old_argv


def test_changed_id_upsert() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "dawn.csv"
        status = root / "processed" / "step_1"
        fingerprint = status / "metadata_source_fingerprints.csv"
        config = root / "config.json"
        frame = pd.DataFrame(
            {
                "id": [1, 2],
                "lat": [49.0, 50.0],
                "lng": [8.0, 9.0],
                "datetime": ["2024-05-01 04:00:00", "2024-05-02 04:00:00"],
                "localtimes": ["", ""],
                "audio": ["audio-a", "audio-b"],
                "photo": ["photo-a", "photo-b"],
            }
        )
        frame.to_csv(source, index=False)
        config.write_text(
            json.dumps(
                {
                    "dawn_chorus_csv": str(source),
                    "status_dir": str(status),
                    "metadata_extraction": {
                        "timezone": "Europe/Berlin",
                        "fingerprint_csv": str(fingerprint),
                    },
                }
            ),
            encoding="utf-8",
        )
        run_step(config)

        frame.loc[frame["id"] == 1, "audio"] = "audio-a-new"
        frame.loc[frame["id"] == 2, "lat"] = 51.0
        frame.to_csv(source, index=False)
        ids_file = root / "ids.csv"
        pd.DataFrame({"dawn_chorus_id": [1, 2]}).to_csv(ids_file, index=False)
        run_step(config, ids_file)

        clean = pd.read_csv(status / "dawnchorus_metadata_clean.csv")
        assert len(clean) == 2
        assert clean.loc[clean["id"] == 1, "lat"].iloc[0] == 49.0
        assert clean.loc[clean["id"] == 2, "lat"].iloc[0] == 51.0
        fingerprints = pd.read_csv(fingerprint)
        assert len(fingerprints) == 2
        assert fingerprints["source_fingerprint"].nunique() == 2


if __name__ == "__main__":
    test_changed_id_upsert()
    print("test_step1_incremental.py: OK")

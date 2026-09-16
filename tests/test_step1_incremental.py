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
                "country": ["Germany", "Germany"],
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


def test_country_filter_removes_existing_non_german_id() -> None:
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
                "country": ["Germany", "Germany"],
            }
        )
        frame.to_csv(source, index=False)
        config.write_text(
            json.dumps(
                {
                    "dawn_chorus_csv": str(source),
                    "status_dir": str(status),
                    "metadata_extraction": {
                        "fingerprint_csv": str(fingerprint),
                        "country_column": "country",
                        "country_value": "Germany",
                    },
                }
            ),
            encoding="utf-8",
        )

        run_step(config)

        frame.loc[frame["id"] == 2, "country"] = "France"
        frame.to_csv(source, index=False)
        run_step(config)

        clean = pd.read_csv(status / "dawnchorus_metadata_clean.csv")
        assert clean["id"].tolist() == [1]
        fingerprints = pd.read_csv(fingerprint)
        assert fingerprints["dawn_chorus_id"].astype(int).tolist() == [1]


def test_scoped_policy_migration_does_not_acknowledge_other_ids() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = root / "config.json"
        source_path = root / "dawn.csv"
        source = pd.DataFrame({"id": [1, 2], "lat": [49., 49.], "lng": [8., 8.],
                               "datetime": ["2025-07-01T06:00:00Z"] * 2,
                               "localtimes": [""] * 2, "country": ["Germany"] * 2})
        source.to_csv(source_path, index=False)
        config.write_text(json.dumps({"dawn_chorus_csv": str(source_path), "status_dir": str(root)}))
        run_step(config)
        fingerprint_path = root / step1.FINGERPRINT_FILENAME
        previous = pd.read_csv(fingerprint_path)
        previous["metadata_fingerprint"] = "old-policy"
        previous["weather_fingerprint"] = "old-policy"
        previous.to_csv(fingerprint_path, index=False)
        ids = root / "ids.csv"
        pd.DataFrame({"id": [1]}).to_csv(ids, index=False)
        run_step(config, ids)
        partial = pd.read_csv(fingerprint_path).set_index("dawn_chorus_id")
        assert partial.loc[1, "metadata_fingerprint"] != "old-policy"
        assert partial.loc[2, "metadata_fingerprint"] == "old-policy"
        assert partial.loc[2, "weather_fingerprint"] == "old-policy"
        run_step(config)
        final = pd.read_csv(fingerprint_path)
        assert final["metadata_fingerprint"].ne("old-policy").all()


if __name__ == "__main__":
    test_changed_id_upsert()
    test_country_filter_removes_existing_non_german_id()
    test_scoped_policy_migration_does_not_acknowledge_other_ids()
    print("test_step1_incremental.py: OK")

#!/usr/bin/env python3
"""Synthetic tests for Sentinel score ID aliases."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Step_4_0_Sentinel2_inventory import load_scores, resolve_score_id_column


def test_dc_id_score_column() -> None:
    assert resolve_score_id_column(["system:index", "DC_id", "score"]) == "DC_id"
    with tempfile.TemporaryDirectory() as raw:
        score_csv = Path(raw) / "scores.csv"
        pd.DataFrame(
            {
                "DC_id": [123, 123, 456],
                "score": [0.4, 0.8, 0.5],
            }
        ).to_csv(score_csv, index=False)
        scores, issues = load_scores(score_csv, "DC_id")
        assert not issues
        assert scores["123"]["score"] == 0.8
        assert scores["123"]["score_row_count"] == 2
        assert scores["456"]["score"] == 0.5


if __name__ == "__main__":
    test_dc_id_score_column()
    print("test_sentinel_inventory.py: OK")

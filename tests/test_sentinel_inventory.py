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



def test_zero_score_and_master_fallback() -> None:
    import Step_7_0_update_master_table as master
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        score_csv = root / "scores.csv"
        pd.DataFrame({"DC_id": [1, 2, 3, 4, 4, 5], "score": [0, 0.01, None, 0, 0.8, -1]}).to_csv(score_csv, index=False)
        scores, _ = load_scores(score_csv)
        code = "too_cloudy_sentinel_not_available"
        assert code in scores["1"]["issues"]
        for key in ["2", "3", "4", "5"]:
            assert code not in scores[key]["issues"]
        compact = root / "compact.csv"
        pd.DataFrame({"dawn_chorus_id": [1, 2, 3], "sentinel_exists": [True, True, False],
                      "sentinel_has_issues": [False, False, True], "sentinel_quality_score": [0, 0.01, None]}).to_csv(compact, index=False)
        detail = root / "detail.csv"
        pd.DataFrame({"dawn_chorus_id": [1], "issues": ["raster_read_failed"]}).to_csv(detail, index=False)
        result = master.add_sentinel_status(pd.DataFrame({"dawn_chorus_id": ["1", "2", "3"]}),
                    {"sentinel2_inventory": {"compact_log": str(compact), "detailed_log": str(detail)}})
        assert result.iloc[0].sentinel_has_issues
        assert result.iloc[0].sentinel_exists
        assert result.iloc[0].sentinel_quality_score == 0
        assert code in result.iloc[0].sentinel_issue_codes
        assert "raster_read_failed" in result.iloc[0].sentinel_issue_codes
        assert not result.iloc[1].sentinel_has_issues
        assert code not in result.iloc[2].sentinel_issue_codes

if __name__ == "__main__":
    test_zero_score_and_master_fallback()
    test_dc_id_score_column()
    print("test_sentinel_inventory.py: OK")

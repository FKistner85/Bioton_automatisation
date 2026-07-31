#!/usr/bin/env python3
"""Synthetic regression tests for incremental and resume-critical behavior."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import output_is_nonempty, should_skip, source_signature, write_batch_status, write_run_meta


FORMATION_COLUMNS = [
    "Bogs",
    "Costal",
    "Forests",
    "Freshwater",
    "Grassland",
    "Permanent Glaciers",
    "Rocky habitats",
    "Temperate heath",
]


def new_ids(incoming: pd.Series, processed: pd.Series) -> set[int]:
    incoming_ids = set(pd.to_numeric(incoming, errors="coerce").dropna().astype(int))
    processed_ids = set(pd.to_numeric(processed, errors="coerce").dropna().astype(int))
    return incoming_ids - processed_ids


def ids_needing_media_download(compact_log: pd.DataFrame) -> set[int]:
    rows = compact_log.copy()
    rows["id"] = pd.to_numeric(rows["id"], errors="coerce")
    problem = (
        rows["exists"].astype(str).str.lower().ne("true")
        | rows["has_issues"].astype(str).str.lower().eq("true")
    )
    return set(rows.loc[problem, "id"].dropna().astype(int))


def validate_formation_status_matrix(frame: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    required = {
        "grid_id",
        "Majority_formation",
        "majority_formation_status",
        "majority_value",
        "second_value",
        "majority_delta",
        "majority_disputed",
        "n_formations",
        "n_lrts",
    }
    missing = required - set(frame.columns)
    if missing:
        issues.append(f"missing:{sorted(missing)}")
    for column in FORMATION_COLUMNS:
        if column in frame.columns and frame[column].max() > 10000:
            issues.append(f"formation_scaling:{column}")
    if "majority_delta" in frame.columns and frame["majority_delta"].max() > 10000:
        issues.append("majority_delta_scaling")
    if {"majority_delta", "majority_disputed"} <= set(frame.columns):
        expected = frame["majority_delta"] <= 200
        if not expected.equals(frame["majority_disputed"].astype(bool)):
            issues.append("majority_disputed_threshold")
    return issues


def test_new_id_detection() -> None:
    assert new_ids(pd.Series([1, 2, 3, 4]), pd.Series([1, 3])) == {2, 4}
    assert new_ids(pd.Series(["1", "bad", "5"]), pd.Series(["1"])) == {5}


def test_checkpoint_and_source_signature() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "source.csv"
        state = root / "state.json"
        source.write_text("id\n1\n", encoding="utf-8")
        signature = source_signature([source])
        write_run_meta(state, "unit", signature, [str(root / "out.csv")], 1)
        assert should_skip(state, signature)

        source.write_text("id\n1\n2\n", encoding="utf-8")
        changed_signature = source_signature([source])
        assert not should_skip(state, changed_signature)

        batch = write_batch_status(root / "batches", "chunk 1", "complete", outputs=[source])
        payload = json.loads(batch.read_text(encoding="utf-8"))
        assert payload["status"] == "complete"
        assert payload["output_fingerprints"][0]["exists"] is True


def test_formation_status_schema_and_scaling() -> None:
    frame = pd.DataFrame(
        {
            "grid_id": ["100mN1E1"],
            "Majority_formation": ["Grassland"],
            "majority_formation_status": ["A"],
            "Grassland": [6500],
            "Forests": [6300],
            "majority_value": [6500],
            "second_value": [6300],
            "majority_delta": [200],
            "majority_disputed": [True],
            "n_formations": [2],
            "2330_A": [6500],
            "n_lrts": [1],
        }
    )
    assert validate_formation_status_matrix(frame) == []

    broken = frame.copy()
    broken["majority_disputed"] = False
    assert "majority_disputed_threshold" in validate_formation_status_matrix(broken)


def test_10m_matrix_uses_centi_percent_and_keeps_formation_k() -> None:
    source = (
        SCRIPT_ROOT / "Step_2_4_generate_10m_formation_status_products.py"
    ).read_text(encoding="utf-8")
    assert 'ix["pct_of_cell"] = ix["ix_area"] / 100.0 * 100.0' in source
    assert 'x_fs = x_fs.loc[:, ~x_fs.columns.str.endswith("_K")]' not in source

    # 100 m2 is the area of a 10 m cell: full coverage must become 10000
    # after the shared percent * 100 integer conversion.
    full_cell_centi_percent = round((100.0 / 100.0 * 100.0) * 100)
    assert full_cell_centi_percent == 10000


def test_media_log_download_selection() -> None:
    log = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "exists": [True, False, True],
            "has_issues": [False, False, True],
        }
    )
    assert ids_needing_media_download(log) == {2, 3}


def test_weather_resume_uses_nonempty_files() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        done = root / "weather_1.csv"
        empty = root / "weather_2.csv"
        missing = root / "weather_3.csv"
        done.write_text("datetime,air_temperature_mean\n2020-01-01,4\n", encoding="utf-8")
        empty.write_text("", encoding="utf-8")
        assert output_is_nonempty(done)
        assert not output_is_nonempty(empty)
        assert not output_is_nonempty(missing)


if __name__ == "__main__":
    test_new_id_detection()
    test_checkpoint_and_source_signature()
    test_formation_status_schema_and_scaling()
    test_10m_matrix_uses_centi_percent_and_keeps_formation_k()
    test_media_log_download_selection()
    test_weather_resume_uses_nonempty_files()
    print("test_pipeline_regressions.py: OK")

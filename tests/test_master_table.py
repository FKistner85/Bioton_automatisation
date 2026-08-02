#!/usr/bin/env python3
"""Synthetic tests for the final master table builder."""

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

import Step_7_0_update_master_table as master


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def test_master_table_minimal_build() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        processed = root / "processed"
        status = processed / "step_1_metadata"
        weather = root / "PointData" / "Weather" / "Hostrada"
        output_csv = root / "Bio_O_Ton_Mastertable.csv"
        weather_inventory = processed / "step_5_1" / "weather_inventory_compact.csv"
        status_events = processed / "_control" / "status_events.csv"

        write_csv(
            status / "dawnchorus_metadata_clean.csv",
            pd.DataFrame(
                {
                    "id": [1],
                    "datetime": ["2024-05-01T04:30:00+02:00"],
                    "lat": [49.0],
                    "lon": [8.4],
                }
            ),
        )
        write_csv(
            status / "dawnchorus_metadata_log.csv",
            pd.DataFrame(
                {
                    "id": [1],
                    "datetime_source": ["localtimes"],
                    "conversion_needed": [True],
                    "conversion_step": ["unit_test"],
                }
            ),
        )
        write_csv(
            weather / "weather_1.csv",
            pd.DataFrame(
                {
                    "datetime": pd.date_range("2024-04-21", periods=264, freq="h"),
                    "air_temperature_mean": [10.0] * 264,
                    "cloud_cover": [50.0] * 264,
                    "humidity_relative": [70.0] * 264,
                    "radiation_downwelling": [100.0] * 264,
                    "wind_direction": [180.0] * 264,
                    "wind_speed": [3.0] * 264,
                }
            ),
        )
        write_csv(
            weather_inventory,
            pd.DataFrame(
                {
                    "dawn_chorus_id": [1],
                    "weather_exists": [True],
                    "weather_has_issues": [False],
                    "has_issues": [False],
                    "issue_codes": [""],
                }
            ),
        )
        config = {
            "dawn_chorus_csv": str(root / "dawn.csv"),
            "status_dir": str(status),
            "processed_root": str(processed),
            "pipeline_control": {
                "status_event_csv": str(status_events),
            },
            "audio_inventory": {},
            "photo_inventory": {},
            "sentinel2_inventory": {},
            "weather_download": {
                "output_dir": str(weather),
                "cache_dir": str(root / "cache"),
            },
            "weather_inventory": {
                "compact_log": str(weather_inventory),
                "expected_rows": 264,
                "expected_interval_seconds": 3600,
                "required_columns": [
                    "air_temperature_mean",
                    "cloud_cover",
                    "humidity_relative",
                    "radiation_downwelling",
                    "wind_direction",
                    "wind_speed",
                ],
            },
            "hostrada_raster_products": {
                "output_root": str(processed / "step_5_4_hostrada_raster_products"),
                "resolution_m": 100,
            },
            "hostrada_raster_quality_check": {
                "output_dir": str(processed / "step_5_5_hostrada_raster_quality_check"),
            },
            "master_table": {
                "output_csv": str(output_csv),
                "output_parquet": str(root / "Bio_O_Ton_Mastertable.parquet"),
                "summary_json": str(root / "Bio_O_Ton_Mastertable_summary.json"),
                "weather_qc_workers": 1,
            },
        }
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        old_argv = sys.argv
        try:
            sys.argv = ["Step_7_0_update_master_table.py", "--config", str(config_path)]
            assert master.main() == 0
        finally:
            sys.argv = old_argv

        result = pd.read_csv(output_csv)
        assert len(result) == 1
        assert "weather_raster_hostrada_10m_exists" not in result.columns
        assert result.loc[0, "weather_point_exists"] in {True, "True", "true", 1}
        assert result.loc[0, "weather_raster_hostrada_100m_issue_codes"] == "missing_raster"
        assert result.loc[0, "weather_point_status"] == "validated"
        assert "weather_raster_hostrada_100m_missing" in str(
            result.loc[0, "record_blocking_issue_codes"]
        )
        assert result.loc[0, "record_status"] in {"partial", "has_issues"}
        events = pd.read_csv(status_events)
        assert set(events["field"]) == {"record_lifecycle"}
        assert events.loc[0, "current_value"] == "added"

        weather_status = pd.read_csv(weather_inventory)
        weather_status["weather_has_issues"] = True
        weather_status["issue_codes"] = "missing_value"
        weather_status.to_csv(weather_inventory, index=False)
        old_argv = sys.argv
        try:
            sys.argv = ["Step_7_0_update_master_table.py", "--config", str(config_path)]
            assert master.main() == 0
        finally:
            sys.argv = old_argv
        events = pd.read_csv(status_events)
        assert "weather_point_status" in set(events["field"])
        status_change = events[events["field"] == "weather_point_status"].iloc[-1]
        assert status_change["previous_value"] == "validated"
        assert status_change["current_value"] == "has_issues"


def test_incremental_master_merge_preserves_unaffected_rows() -> None:
    columns = master.MASTER_COLUMNS
    previous = pd.DataFrame(
        [
            {"dawn_chorus_id": "1", "sound_status": "validated"},
            {"dawn_chorus_id": "2", "sound_status": "missing"},
        ]
    )
    updates = pd.DataFrame(
        [{"dawn_chorus_id": "2", "sound_status": "validated"}]
    )
    for frame in [previous, updates]:
        for column in columns:
            if column not in frame.columns:
                frame[column] = pd.NA

    merged = master.merge_master_rows(previous[columns], updates[columns])
    merged = merged.set_index("dawn_chorus_id")
    assert merged.loc["1", "sound_status"] == "validated"
    assert merged.loc["2", "sound_status"] == "validated"


def test_mixed_timezone_local_wall_times() -> None:
    values = pd.Series(
        [
            "2024-05-01T04:30:00+02:00",
            "2024-12-01T05:45:00+01:00",
            "invalid",
        ]
    )
    parsed = master.parse_local_wall_times(values)
    assert parsed.dt.strftime("%Y-%m-%d %H:%M:%S").tolist()[:2] == [
        "2024-05-01 04:30:00",
        "2024-12-01 05:45:00",
    ]
    assert pd.isna(parsed.iloc[2])


if __name__ == "__main__":
    test_master_table_minimal_build()
    test_incremental_master_merge_preserves_unaffected_rows()
    test_mixed_timezone_local_wall_times()
    print("test_master_table.py: OK")


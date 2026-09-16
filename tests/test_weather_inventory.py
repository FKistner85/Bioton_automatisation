#!/usr/bin/env python3
"""Synthetic tests for Step 5_1 weather inventory."""

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

import Step_5_1_Weather_inventory as inventory


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def test_weather_inventory_good_and_missing() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        weather_dir = root / "weather"
        processed = root / "processed"
        metadata_csv = root / "metadata.csv"
        config_path = root / "config.json"

        write_csv(
            metadata_csv,
            pd.DataFrame(
                {
                    "id": [1, 2],
                    "datetime": [
                        "2024-05-11T04:30:00+02:00",
                        "2024-05-11T04:35:00+02:00",
                    ],
                }
            ),
        )
        write_csv(
            weather_dir / "weather_1.csv",
            pd.DataFrame(
                {
                    "datetime": pd.date_range("2024-05-01", periods=264, freq="h"),
                    "air_temperature_mean": [10.0] * 264,
                    "cloud_cover": [50.0] * 264,
                    "humidity_relative": [70.0] * 264,
                    "radiation_downwelling": [100.0] * 264,
                    "wind_direction": [180.0] * 264,
                    "wind_speed": [3.0] * 264,
                }
            ),
        )

        config = {
            "weather_inventory": {
                "directory": str(weather_dir),
                "filename_glob": "weather_*.csv",
                "metadata_csv": str(metadata_csv),
                "metadata_id_column": "id",
                "metadata_datetime_column": "datetime",
                "detailed_log": str(processed / "weather_inventory_detailed.csv"),
                "file_list_log": str(processed / "weather_file_list.csv"),
                "missing_ids_log": str(processed / "weather_missing_ids.csv"),
                "compact_log": str(processed / "weather_inventory_compact.csv"),
                "required_columns": [
                    "datetime",
                    "air_temperature_mean",
                    "cloud_cover",
                    "humidity_relative",
                    "radiation_downwelling",
                    "wind_direction",
                    "wind_speed",
                ],
                "expected_rows": 264,
                "expected_interval_seconds": 3600,
                "temperature_min_C": -60,
                "temperature_max_C": 60,
                "humidity_min_percent": 0,
                "humidity_max_percent": 100,
                "max_nan_fraction": 0.0,
                "workers": 1,
                "state_file": str(processed / "state.json"),
            },
            "weather_download": {
                "preceding_days": 10,
                "input_timezone": "Europe/Berlin",
            },
        }
        config_path.write_text(json.dumps(config), encoding="utf-8")

        old_argv = sys.argv
        try:
            sys.argv = [
                "Step_5_1_Weather_inventory.py",
                "--config",
                str(config_path),
                "--list-only",
            ]
            assert inventory.main() == 0
        finally:
            sys.argv = old_argv
        file_list = pd.read_csv(processed / "weather_file_list.csv")
        missing_ids = pd.read_csv(processed / "weather_missing_ids.csv")
        assert file_list["dawn_chorus_id"].astype(str).tolist() == ["1"]
        assert missing_ids["dawn_chorus_id"].astype(str).tolist() == ["2"]

        old_argv = sys.argv
        try:
            sys.argv = ["Step_5_1_Weather_inventory.py", "--config", str(config_path)]
            assert inventory.main() == 0
        finally:
            sys.argv = old_argv

        compact = pd.read_csv(processed / "weather_inventory_compact.csv")
        by_id = {
            str(row["dawn_chorus_id"]): row
            for _, row in compact.iterrows()
        }
        assert str(by_id["1"]["weather_exists"]).lower() == "true"
        assert str(by_id["1"]["weather_has_issues"]).lower() == "false"
        assert str(by_id["2"]["weather_exists"]).lower() == "false"
        assert by_id["2"]["issue_codes"] == "missing_file"

        old_argv = sys.argv
        try:
            sys.argv = ["Step_5_1_Weather_inventory.py", "--config", str(config_path)]
            assert inventory.main() == 0
        finally:
            sys.argv = old_argv
        state = json.loads((processed / "state.json").read_text(encoding="utf-8"))
        assert state["weather_files_reused"] == 1
        assert state["weather_files_revalidated"] == 0


def test_dst_calendar_windows_and_real_defects() -> None:
    settings = {"required_columns": ["datetime", "air_temperature_mean"], "expected_rows": 264}
    download = {"preceding_days": 10, "input_timezone": "Europe/Berlin"}
    cases = [
        ("2025-03-30T06:00:00+02:00", "2025-03-20", "2025-03-31", 263),
        ("2025-04-01T06:00:00+02:00", "2025-03-22", "2025-04-02", 263),
        ("2025-10-26T06:00:00+01:00", "2025-10-16", "2025-10-27", 265),
        ("2025-05-11T06:00:00+02:00", "2025-05-01", "2025-05-12", 264),
    ]
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "weather_1.csv"
        for recording, start, end, count in cases:
            # Independent oracle: explicit calendar boundaries, not the pipeline helper.
            expected = pd.date_range(start, end, tz="Europe/Berlin", freq="h", inclusive="left").tz_localize(None)
            frame = pd.DataFrame({"datetime": expected, "air_temperature_mean": 10.0})
            write_csv(path, frame)
            result = inventory.inspect_weather_csv(path, recording, settings, download)
            assert result["expected_rows"] == count
            assert not result["has_issues"], result
            assert inventory.previous_row_is_reusable(result, path, recording, download, False)
            legacy = {key: value for key, value in result.items() if key != "time_qc_version"}
            assert not inventory.previous_row_is_reusable(legacy, path, recording, download, False)
            assert result["expected_first_datetime"] == pd.Timestamp(start).isoformat()
            assert result["expected_last_datetime"] == (pd.Timestamp(end) - pd.Timedelta(hours=1)).isoformat()

            # A real extra duplicate must still be rejected, even in autumn.
            broken = frame.copy()
            broken.loc[1, "datetime"] = broken.loc[0, "datetime"]
            write_csv(path, broken)
            result = inventory.inspect_weather_csv(path, recording, settings, download)
            assert "duplicate_datetime" in result["issues"]
            assert "unexpected_time_interval" in result["issues"]

            write_csv(path, frame.iloc[:-1])
            result = inventory.inspect_weather_csv(path, recording, settings, download)
            assert "unexpected_row_count" in result["issues"]
            assert "unexpected_time_window" in result["issues"]

        # The old fixed-264-hour spring product includes an extra previous-day hour.
        old_times = pd.date_range("2025-03-19 22:00", periods=264, tz="UTC", freq="h").tz_convert("Europe/Berlin").tz_localize(None)
        write_csv(path, pd.DataFrame({"datetime": old_times, "air_temperature_mean": 10.0}))
        result = inventory.inspect_weather_csv(path, cases[0][0], settings, download)
        assert "unexpected_row_count" in result["issues"]
        assert "unexpected_time_window" in result["issues"]

        result = inventory.inspect_weather_csv(path, "invalid", settings, download)
        assert "invalid_metadata_datetime" in result["issues"]


if __name__ == "__main__":
    test_weather_inventory_good_and_missing()
    test_dst_calendar_windows_and_real_defects()
    print("test_weather_inventory.py: OK")

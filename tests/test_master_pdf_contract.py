"""Consumer-contract regression cases from the 9 October 2026 master PDF."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools")]
import Step_7_0_update_master_table as master
import Step_5_1_Weather_inventory as weather
from export_ci_tec_master import COLUMNS
from audio_issue_policy import duration_notes_only, has_blocking_audio_issues


def ready_table(sources):
    table = pd.DataFrame({c: [pd.NA] * len(sources) for c in master.MASTER_COLUMNS})
    table["dawn_chorus_id"] = [str(i + 1) for i in range(len(sources))]
    table["timestamp_source"] = sources
    table["timestamp_change_reason"] = ["datetime_zero_utc_label_interpreted_as_German_walltime" if s == "datetime" else "local_walltime" for s in sources]
    table["datetime_local"] = "2025-05-01 06:00:00"
    table["datetime_utc"] = "2025-05-01T04:00:00Z"
    table["lat"], table["lon"] = 49., 8.
    for prefix in ("sound", "photo", "sentinel", "weather_point"):
        table[f"{prefix}_exists"] = True
        table[f"{prefix}_has_issues"] = False
    table["duration_seconds"] = 60.
    table["sentinel_quality_score"] = .8
    for size in ("100m", "10m"):
        table[f"grid_{size}_assignment_exists"] = True
        table[f"grid_{size}_has_majority_formation"] = True
        table[f"majority_formation_{size}"] = "Forests"
        table[f"majority_formation_status_{size}"] = "A"
    table["inside_lrt_polygon"] = True
    table["bioacoustic_status"] = "validated"
    table["bioacoustic_required_models_complete"] = True
    return table


class PDFContractTests(unittest.TestCase):
    def test_preserved_sentinel_scores_still_enforce_issue_flags(self):
        table = ready_table(["localtimes", "localtimes"])
        table["sentinel_quality_score"] = [0., None]
        result = master.add_agreement_and_ready_flags(table)
        self.assertEqual(result.sentinel_has_issues.tolist(), [True, True])
        self.assertFalse(result.ready_for_general_analysis.any())
        self.assertIn("too_cloudy_sentinel_not_available", result.sentinel_issue_codes.iloc[0])
        self.assertIn("quality_score_missing", result.sentinel_issue_codes.iloc[1])
    def test_full_and_incremental_writes_keep_all_rows_in_csv_and_parquet(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "datetime": ["2025-05-01T06:00:00+02:00"] * 3 + [None, "2025-05-01T06:00:00+02:00"],
                          "lat": [49.] * 5, "lon": [8.] * 5}).to_csv(root / "dawnchorus_metadata_clean.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "datetime_source": ["localtimes", "datetime", "localtimes", "localtimes", None]}).to_csv(root / "dawnchorus_metadata_log.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "lat": [49.] * 5, "lon": [8.] * 5,
                          "inside_lrt_polygon": [False] * 5, "lrt_polygon_count": [0] * 5}).to_csv(root / "points.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "has_issues": [False, True, True, True, True]}).to_csv(root / "audio.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "duration_seconds": [60., 45., 0., 39., None],
                          "issues": ["", "duration_not_60s", "invalid_duration", "duration_not_60s", "duration_unavailable"]}).to_csv(root / "audio_detail.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "weather_exists": [True] * 5,
                          "weather_has_issues": [True] * 5, "issue_codes": ["missing_value"] * 5}).to_csv(root / "weather.csv", index=False)
            pd.DataFrame({"id": [1, 2, 3, 4, 5], "sentinel_exists": [True] * 5,
                          "sentinel_has_issues": [False] * 5, "sentinel_quality_score": [.8, .8, 0., None, .8]}).to_csv(root / "sentinel.csv", index=False)
            cfg = {"status_dir": str(root), "processed_root": str(root / "processed"),
                   "point_lrt_assignment": {"output_csv": str(root / "points.csv")},
                   "audio_inventory": {"compact_log": str(root / "audio.csv"), "detailed_log": str(root / "audio_detail.csv")},
                   "weather_inventory": {"compact_log": str(root / "weather.csv")},
                   "sentinel2_inventory": {"compact_log": str(root / "sentinel.csv")}}
            config = root / "config.json"
            config.write_text(json.dumps(cfg))
            with patch.object(sys, "argv", ["master", "--config", str(config)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(master.main(), 0)
            csv = pd.read_csv(root / "Bio_O_Ton_Master.csv")
            parquet = pd.read_parquet(root / "Bio_O_Ton_Master.parquet")
            self.assertEqual(csv.dawn_chorus_id.tolist(), [1, 2, 3, 4, 5])
            self.assertEqual(csv.columns.tolist(), parquet.columns.tolist())
            self.assertEqual(csv.time_has_issues.tolist(), [False, False, False, False, True])
            self.assertEqual(csv.sound_has_issues.tolist(), [False, False, True, False, True])
            self.assertEqual(csv.duration_seconds.iloc[3], 39.)  # No >=40 filter on output.
            self.assertFalse(csv.weather_point_has_issues.any())
            self.assertTrue(csv.sentinel_has_issues.iloc[2])
            self.assertTrue(csv.sentinel_has_issues.iloc[3])
            # Simulate v6 master, then update only ID 1: retained fallback rows
            # must receive non-null flags and their migration must be logged.
            csv = csv.drop(columns="time_has_issues")
            csv["mastertable_schema_version"] = "2026-09-17-mastertable-v6"
            csv.to_csv(root / "Bio_O_Ton_Master.csv", index=False)
            pd.DataFrame({"id": [1]}).to_csv(root / "ids.csv", index=False)
            with patch.object(sys, "argv", ["master", "--config", str(config), "--ids-file", str(root / "ids.csv")]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(master.main(), 0)
            updated = pd.read_csv(root / "Bio_O_Ton_Master.csv")
            self.assertEqual(updated.dawn_chorus_id.tolist(), [1, 2, 3, 4, 5])
            self.assertEqual(updated.time_has_issues.tolist(), [False, False, False, False, True])
            self.assertFalse(updated.time_has_issues.isna().any())
            self.assertTrue(updated.mastertable_schema_version.eq(master.SCHEMA_VERSION).all())
            events = pd.read_csv(root / "processed/step_0_control/status_events.csv")
            self.assertTrue(((events.dawn_chorus_id == 2) & events.field.eq("time_has_issues")).any())

    def test_duration_notes_do_not_hide_technical_audio_errors(self):
        self.assertTrue(duration_notes_only("duration_not_60s:observed=45s,allowed=59-61s"))
        self.assertFalse(has_blocking_audio_issues(["duration_not_60s:observed=45s"]))
        self.assertTrue(has_blocking_audio_issues(["duration_not_60s:observed=45s", "pyav_decode_failed"]))
        self.assertFalse(duration_notes_only(""))
        self.assertFalse(duration_notes_only("duration_unavailable"))

    def test_legacy_duration_warning_is_informational_in_master(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pd.DataFrame({"id": [1, 2], "has_issues": [True, True]}).to_csv(root / "compact.csv", index=False)
            pd.DataFrame({"id": [1, 2], "duration_seconds": [45., 45.],
                          "issues": ["duration_not_60s:observed=45s", "duration_not_60s|pyav_decode_failed"]}).to_csv(root / "detail.csv", index=False)
            cfg = {"audio_inventory": {"compact_log": str(root / "compact.csv"), "detailed_log": str(root / "detail.csv")}}
            result = master.add_media_status(pd.DataFrame({"dawn_chorus_id": ["1", "2"]}), cfg, "audio_inventory", "sound")
            self.assertEqual(result.sound_has_issues.tolist(), [False, True])
            self.assertEqual(result.duration_seconds.tolist(), [45., 45.])

    def test_source_controls_clean_flags_but_audio_remains_usable(self):
        result = master.add_agreement_and_ready_flags(ready_table(["localtimes", "datetime", None, "unknown"]))
        self.assertEqual(result.time_has_issues.tolist(), [False, False, True, True])
        for field in ("ready_for_general_analysis", "ready_for_formation_analysis_100m",
                      "ready_for_formation_analysis_10m", "ready_for_direct_lrt_analysis"):
            self.assertEqual(result[field].tolist(), [True, True, False, False])
        self.assertTrue(result.ready_for_bioacoustic_analysis.all())
        self.assertNotIn("time_source_not_localtimes", result.record_blocking_issue_codes.iloc[1])

    def test_missing_provenance_and_legacy_string_flags_are_migrated(self):
        table = pd.DataFrame({"timestamp_source": ["localtimes", "datetime", ""],
                              "time_has_issues": [True, False, False],
                              "ready_for_general_analysis": ["True", "True", "False"],
                              "record_status": ["validated"] * 3})
        result = master.refresh_time_quality(table)
        self.assertEqual(result.ready_for_general_analysis.tolist(), [False, False, False])
        self.assertEqual(result.record_status.tolist(), ["partial", "partial", "partial"])
        result = master.refresh_time_quality(pd.DataFrame({"dawn_chorus_id": ["1"]}))
        self.assertEqual(result.time_has_issues.tolist(), [True])

    def test_no_time_log_does_not_claim_a_trusted_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pd.DataFrame({"id": [1], "datetime": ["2025-05-01T06:00:00+02:00"],
                          "lat": [49.], "lon": [8.]}).to_csv(root / "dawnchorus_metadata_clean.csv", index=False)
            result = master.build_base_table({"status_dir": str(root)}, root / "master.csv", "now")
            self.assertTrue(result.time_has_issues.iloc[0])
            self.assertEqual(result.datetime_local.iloc[0], "2025-05-01 06:00:00")

    def test_checked_audio_duration_reaches_master_and_missing_qc_is_flagged(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pd.DataFrame({"id": [1, 2], "has_issues": [False, False]}).to_csv(root / "compact.csv", index=False)
            pd.DataFrame({"id": [1, 1], "duration_seconds": [45., 60.], "issues": ["", ""]}).to_csv(root / "detail.csv", index=False)
            cfg = {"audio_inventory": {"compact_log": str(root / "compact.csv"), "detailed_log": str(root / "detail.csv")}}
            result = master.add_media_status(pd.DataFrame({"dawn_chorus_id": ["1", "2", "3"]}), cfg, "audio_inventory", "sound")
            self.assertEqual(result.duration_seconds.iloc[0], 45.)
            self.assertTrue(result.sound_has_issues.iloc[1])
            self.assertIn("duration_unavailable", result.sound_issue_codes.iloc[1])
            self.assertFalse(result.sound_exists.iloc[2])

    def test_weather_values_only_are_informational_but_structural_errors_block(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "compact.csv"
            pd.DataFrame({"id": [1, 2, 3], "weather_exists": [True] * 3,
                          "weather_has_issues": [True, True, None],
                          "issue_codes": ["missing_value", "missing_value|unexpected_row_count", "missing_value"]}).to_csv(path, index=False)
            result = master.add_weather_point_status(pd.DataFrame({"dawn_chorus_id": ["1", "2", "3", "4"]}),
                                                     {"weather_inventory": {"compact_log": str(path)}})
            self.assertEqual(result.weather_point_has_issues.tolist(), [False, True, True, True])
            self.assertEqual(result.weather_point_issue_codes.iloc[0], "missing_value")
            self.assertIn("qc_not_run", result.weather_point_issue_codes.iloc[2])

    def test_weather_inspection_and_cached_compact_follow_pdf(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "weather_1.csv"
            frame = pd.DataFrame({"datetime": pd.date_range("2025-04-21", periods=264, freq="h"), "air_temperature_mean": [10.] * 264})
            frame.loc[0, "air_temperature_mean"] = None
            frame.to_csv(path, index=False)
            settings = {"required_columns": ["datetime", "air_temperature_mean"], "max_nan_fraction": 0.0}
            result = weather.inspect_weather_csv(path, "2025-05-01T06:00:00+02:00", settings, {})
            self.assertEqual(result["issues"], "missing_value")
            self.assertFalse(result["has_issues"])
            result["has_issues"] = True  # Cached pre-v7 QC.
            compact = weather.compact_from_detail(pd.DataFrame([result]))
            self.assertEqual(str(compact.weather_has_issues.iloc[0]).lower(), "false")

    def test_image_without_quality_score_cannot_pass_clean_filter(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "sentinel.csv"
            pd.DataFrame({"id": [1], "sentinel_exists": [True], "sentinel_has_issues": [False]}).to_csv(path, index=False)
            result = master.add_sentinel_status(pd.DataFrame({"dawn_chorus_id": ["1"]}),
                                               {"sentinel2_inventory": {"compact_log": str(path)}})
            self.assertTrue(result.sentinel_has_issues.iloc[0])
            self.assertIn("quality_score_missing", result.sentinel_issue_codes.iloc[0])

    def test_machine_schema_and_optional_export_expose_pdf_fields(self):
        schema = json.loads((ROOT / "schemas/master_table.schema.json").read_text())
        self.assertEqual(schema["schema_version"], master.SCHEMA_VERSION)
        self.assertEqual(len(master.MASTER_COLUMNS), 107)
        for column in ("time_has_issues", "duration_seconds", "inside_lrt_polygon",
                       "grid_100m_has_majority_formation", "grid_10m_has_majority_formation"):
            self.assertIn(column, master.MASTER_COLUMNS)
            self.assertIn(column, schema["required"])
            self.assertIn(column, COLUMNS)


if __name__ == "__main__":
    unittest.main()

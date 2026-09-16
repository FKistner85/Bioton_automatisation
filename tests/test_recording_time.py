"""Explicit expected clock values, including both German DST transitions."""
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools")]
from recording_time import resolve_recording_time, german_wall_times
import Step_1_metadata_extraction as step1
import Step_7_0_update_master_table as master
import plan_pipeline_run as planner


def test_utc_fallback_and_transitions():
    cases = [
        ("2025-01-15T16:03:00Z", "2025-01-15T17:03:00+01:00"),
        ("2025-07-15T16:03:00+00:00", "2025-07-15T18:03:00+02:00"),
        ("2025-03-30T00:59:59Z", "2025-03-30T01:59:59+01:00"),
        ("2025-03-30T01:00:00Z", "2025-03-30T03:00:00+02:00"),
        ("2025-10-26T00:59:59Z", "2025-10-26T02:59:59+02:00"),
        ("2025-10-26T01:00:00Z", "2025-10-26T02:00:00+01:00"),
        ("2025-07-15T23:30:00Z", "2025-07-16T01:30:00+02:00"),
        ("2025-01-15T23:30:00Z", "2025-01-16T00:30:00+01:00"),
        ("2020-05-04T05:57:00+00:00", "2020-05-04T07:57:00+02:00"),
        ("2025-07-15T11:00:00-04:00", "2025-07-15T17:00:00+02:00"),
    ]
    for raw, expected in cases:
        result = resolve_recording_time(" ", raw)
        assert result["datetime_clean"] == expected, (raw, result)
        assert result["timestamp_status"] == "validated"


def test_transitions_for_every_recording_year():
    from datetime import date, timedelta
    # Explicit EU calendar rule for the audited 2011-2026 period, independent
    # of the conversion library's transition lookup.
    for year in range(2011, 2027):
        for month, hour, before_offset, after_offset in [(3, "03", "+01:00", "+02:00"), (10, "02", "+02:00", "+01:00")]:
            end = date(year, month, 31)
            sunday = end - timedelta(days=(end.weekday() + 1) % 7)
            day = sunday.isoformat()
            before_hour = "01" if month == 3 else "02"
            assert resolve_recording_time("", f"{day}T00:59:59Z")["datetime_clean"] == f"{day}T{before_hour}:59:59{before_offset}"
            assert resolve_recording_time("", f"{day}T01:00:00Z")["datetime_clean"] == f"{day}T{hour}:00:00{after_offset}"


def test_local_clock_always_wins():
    for local in ["2022-04-05T11:14:20-04:00", "2022-04-05T11:14:20Z", "2022-04-05 11:14:20"]:
        result = resolve_recording_time(local, "2022-04-05T15:14:20+00:00")
        assert result["datetime_clean"] == "2022-04-05T11:14:20+02:00"
        assert "utc_local_conflict" in result["timestamp_issue_codes"]
        assert result["selected_minus_reference_seconds"] == -21600
    result = resolve_recording_time("2022-05-28T09:12:27+02:00", "2022-05-28T09:12:27Z")
    assert result["datetime_clean"] == "2022-05-28T09:12:27+02:00"
    assert result["timestamp_issue_codes"] == "utc_local_conflict"


def test_invalid_local_never_falls_back():
    for local, code in [("bad", "localtimes_unparseable"),
                        ("2025-03-30T02:30:00+01:00", "nonexistent_localtime"),
                        ("2025-10-26T02:30:00", "ambiguous_localtime_unresolved")]:
        result = resolve_recording_time(local, "2025-01-01T06:00:00Z")
        assert pd.isna(result["datetime_clean"])
        assert result["datetime_source"] == "localtimes"
        assert code in result["timestamp_issue_codes"]


def test_autumn_fold_evidence_and_conflict():
    for offset, utc in [("+02:00", "00:30:00"), ("+01:00", "01:30:00")]:
        expected = f"2025-10-26T02:30:00{offset}"
        assert resolve_recording_time(expected, "")["datetime_clean"] == expected
        assert resolve_recording_time("2025-10-26T02:30:00", f"2025-10-26T{utc}Z")["datetime_clean"] == expected
    result = resolve_recording_time("2025-10-26T02:30:00+01:00", "2025-10-26T00:30:00Z")
    assert result["datetime_clean"] == "2025-10-26T02:30:00+01:00"
    assert "utc_local_conflict" in result["timestamp_issue_codes"]


def test_missing_and_fractional_inputs():
    assert resolve_recording_time(None, None)["timestamp_status"] == "invalid"
    result = resolve_recording_time(None, "2025-01-01 06:00:00")
    assert result["datetime_clean"] == "2025-01-01T07:00:00+01:00"
    assert "datetime_timezone_missing_assumed_utc" in result["timestamp_issue_codes"]
    result = resolve_recording_time("2025-07-01T06:00:00.123+02:00", "2025-07-01T04:00:00.456Z")
    assert result["datetime_clean"] == "2025-07-01T06:00:00+02:00"
    assert result["timestamp_status"] == "validated"
    try:
        resolve_recording_time(None, "2025-01-01T06:00:00Z", "UTC")
    except ValueError:
        pass
    else:
        raise AssertionError("A non-German output timezone must fail")


def test_extraction_to_master_keeps_clock_and_utc():
    source = pd.DataFrame({"id": [1, 2, 3, 4], "lat": [49.] * 4, "lng": [8.] * 4,
        "datetime": ["2025-01-15T06:00:00Z", "2025-07-15T06:00:00Z",
                     "2025-10-26T00:30:00Z", "2025-10-26T01:30:00Z"],
        "localtimes": ["", "", "2025-10-26T02:30:00+02:00", "2025-10-26T02:30:00+01:00"]})
    clean, log = step1.build_outputs(source, "Europe/Berlin")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        clean.to_csv(root / step1.CLEAN_FILENAME, index=False)
        log.to_csv(root / step1.LOG_FILENAME, index=False)
        result = master.build_base_table({"status_dir": str(root)}, root / "master.csv", "now")
        assert result["datetime_local"].tolist() == ["2025-01-15 07:00:00", "2025-07-15 08:00:00", "2025-10-26 02:30:00", "2025-10-26 02:30:00"]
        assert result["datetime_utc"].tolist() == source["datetime"].tolist()
    planned = planner.build_fingerprints(source.assign(dawn_chorus_id=source.id.astype(str)))
    pd.testing.assert_frame_equal(step1.build_fingerprints(source), planned)
    import hashlib
    for row in source.itertuples(index=False):
        raw = source.loc[source.id == row.id].iloc[0]
        old_metadata = hashlib.sha256((step1.hash_values(raw, step1.FINGERPRINT_GROUPS["metadata_fingerprint"]) + "\x1ftimezone=Europe/Berlin").encode()).hexdigest()
        current = planned.loc[planned.dawn_chorus_id == str(row.id)].iloc[0]
        assert current.metadata_fingerprint != old_metadata
        assert current.weather_fingerprint != step1.hash_values(raw, step1.FINGERPRINT_GROUPS["weather_fingerprint"])


def test_german_month_and_variant_context_refresh():
    import Step_7_1_update_formation_variant_table as variants
    values = pd.Series(["2025-04-01T00:30:00+02:00", "2025-01-01T00:30:00+01:00", "2025-04-01 00:30:00"])
    assert german_wall_times(values).dt.month.tolist() == [4, 1, 4]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        metadata_path, master_path = root / "metadata.csv", root / "master.csv"
        pd.DataFrame({"id": [1], "lat": [49.], "lon": [8.], "datetime": [values[0]]}).to_csv(metadata_path, index=False)
        pd.DataFrame({"dawn_chorus_id": [1], "datetime_local": ["2025-03-31 22:30:00"], "datetime_utc": ["2025-03-31T20:30:00Z"]}).to_csv(master_path, index=False)
        config = {"point_lrt_assignment": {"metadata_csv": str(metadata_path)}, "master_table": {"output_csv": str(master_path)}}
        metadata = variants.load_metadata(config)
        context = variants.load_recording_context(config, metadata)
        assert context.recording_month.tolist() == [4]
        assert context.datetime_local.tolist() == ["2025-04-01 00:30:00"]
        assert context.datetime_utc.tolist() == ["2025-03-31T22:30:00Z"]


def test_changed_day_invalidates_preserved_weather_and_sentinel():
    table = pd.DataFrame({"dawn_chorus_id": ["1", "2"], "date_local": ["2025-07-02", "2025-07-01"]})
    previous = pd.DataFrame({"dawn_chorus_id": ["1", "2"], "date_local": ["2025-07-01"] * 2,
        "weather_point_exists": [True] * 2, "weather_point_has_issues": [False] * 2,
        "weather_point_issue_codes": [""] * 2, "sentinel_exists": [True] * 2,
        "sentinel_has_issues": [False] * 2, "sentinel_issue_codes": [""] * 2})
    result = master.add_preserved_nonformation_domains(table, previous, {})
    assert result.weather_point_has_issues.tolist() == [True, False]
    assert result.sentinel_has_issues.tolist() == [True, False]
    assert result.weather_point_exists.all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(name + ": OK")

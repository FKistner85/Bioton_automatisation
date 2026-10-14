"""PDF 2026-10-13 (user-supplied) is normative; verify without changing it."""
import sys
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools")]
from recording_time import resolve_recording_time
import Step_1_metadata_extraction as step1
import Step_7_0_update_master_table as master

SAMPLES = {
    9812463: ("2011-03-26T05:31:00+00:00", "2011-03-26 05:31:00"),
    9812260: ("2014-06-17T06:00:00+00:00", "2014-06-17 06:00:00"),
    9813693: ("2020-01-01T05:45:00+00:00", "2020-01-01 05:45:00"),
    9813353: ("2020-03-14T07:47:00+00:00", "2020-03-14 07:47:00"),
    9814086: ("2020-03-17T06:26:00+00:00", "2020-03-17 06:26:00"),
    9815166: ("2020-05-04T05:57:00+00:00", "2020-05-04 05:57:00"),
    9815051: ("2020-05-06T05:30:00+00:00", "2020-05-06 05:30:00"),
    9814704: ("2020-05-08T20:21:00+00:00", "2020-05-08 20:21:00"),
    9814726: ("2020-05-09T05:06:00+00:00", "2020-05-09 05:06:00"),
    9813276: ("2020-05-16T04:17:00+00:00", "2020-05-16 04:17:00"),
    9813997: ("2020-05-20T04:42:00+00:00", "2020-05-20 04:42:00"),
    9813130: ("2020-05-27T04:48:00+00:00", "2020-05-27 04:48:00"),
    9812561: ("2020-06-07T04:40:00+00:00", "2020-06-07 04:40:00"),
    9904149: ("2021-05-23T06:49:00+00:00", "2021-05-23 06:49:00"),
}

def test_website_verified_samples_as_readme_master_clocks(tmp_path):
    source = pd.DataFrame([{"id": key, "lat": 49., "lng": 8., "datetime": dt, "localtimes": ""}
                           for key, (dt, _) in SAMPLES.items()])
    clean, log = step1.build_outputs(source, "Europe/Berlin")
    clean.to_csv(tmp_path / step1.CLEAN_FILENAME, index=False)
    log.to_csv(tmp_path / step1.LOG_FILENAME, index=False)
    out = master.build_base_table({"status_dir": str(tmp_path)}, tmp_path / "master.csv", "now")
    for row in out.itertuples(index=False):
        raw, wanted = SAMPLES[int(row.dawn_chorus_id)]
        assert row.datetime_local == wanted
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", row.datetime_local)
        assert row.date_local == wanted[:10]
        assert row.time_local == wanted[-8:]
        assert row.timestamp_source == "datetime"  # PDF source provenance
        assert not bool(row.time_has_issues)  # Checked fallback has valid clock; source remains datetime
        expected_utc = pd.Timestamp(raw[:19]).tz_localize("Europe/Berlin").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        assert row.datetime_utc == expected_utc


def test_localtimes_issue_flag_requires_qc(tmp_path):
    source = pd.DataFrame([{"id": 1, "lat": 49., "lng": 8., "localtimes": "2020-05-04T05:57:00+02:00", "datetime": "2020-05-04T03:57:00Z"},
                           {"id": 2, "lat": 49., "lng": 8., "localtimes": "2020-05-04T05:57:00+02:00", "datetime": "2020-05-04T05:57:00Z"}])
    clean, log = step1.build_outputs(source, "Europe/Berlin")
    clean.to_csv(tmp_path / step1.CLEAN_FILENAME, index=False)
    log.to_csv(tmp_path / step1.LOG_FILENAME, index=False)
    out = master.build_base_table({"status_dir": str(tmp_path)}, tmp_path / "master.csv", "now")
    assert out.time_has_issues.tolist() == [False, True]
    assert out.datetime_local.tolist() == ["2020-05-04 05:57:00"] * 2


def test_fingerprint_scoped_to_changed_policy():
    source = pd.DataFrame([{"id": 1, "lat": 49., "lng": 8., "datetime": "2020-05-04T05:57:00Z", "localtimes": ""},
                           {"id": 2, "lat": 49., "lng": 8., "datetime": "2020-05-04T03:57:00Z", "localtimes": "2020-05-04T05:57:00+02:00"}])
    current = step1.build_fingerprints(source).set_index("dawn_chorus_id")
    legacy = step1.build_fingerprints(source, legacy_fallback=True).set_index("dawn_chorus_id")
    assert current.loc["1", "metadata_fingerprint"] != legacy.loc["1", "metadata_fingerprint"]
    assert current.loc["2", "metadata_fingerprint"] == legacy.loc["2", "metadata_fingerprint"]


def test_timestamp_conflict_survives_master_only_refresh():
    row = pd.DataFrame({"timestamp_source": ["localtimes"], "datetime_local": ["2020-05-04 05:57:00"],
                        "datetime_utc": ["2020-05-04T03:57:00Z"], "time_issue_codes": ["utc_local_conflict"],
                        "time_has_issues": [True], "ready_for_general_analysis": ["True"]})
    result = master.refresh_time_quality(row)
    assert bool(result.time_has_issues.iloc[0])
    assert not bool(result.ready_for_general_analysis.iloc[0])
    assert "time_validation_failed" in result.record_blocking_issue_codes.iloc[0] if "record_blocking_issue_codes" in result else True


def test_sentinel_utc_day_drift_is_sticky_until_review(tmp_path):
    current = pd.DataFrame({"dawn_chorus_id": ["1", "2"],
                            "datetime_utc": ["2020-05-07T23:00:00Z", "2020-05-08T04:00:00Z"],
                            "sentinel_exists": [True, True], "sentinel_quality_score": [0.7, 0.8],
                            "sentinel_has_issues": [False, False], "sentinel_issue_codes": ["", ""]})
    previous = pd.DataFrame({"dawn_chorus_id": ["1", "2"],
                             "datetime_utc": ["2020-05-08T00:00:00Z", "2020-05-08T04:00:00Z"],
                             "sentinel_issue_codes": ["", ""]})
    flagged = master.preserve_sentinel_time_selection_warnings(current.copy(), previous, {})
    assert flagged.sentinel_has_issues.tolist() == [True, False]
    # Subsequent incremental jobs that have not re-selected the scene cannot clear it.
    previous2 = flagged[["dawn_chorus_id", "datetime_utc", "sentinel_issue_codes"]].copy()
    again = master.preserve_sentinel_time_selection_warnings(current.copy(), previous2, {})
    assert again.sentinel_has_issues.tolist() == [True, False]
    reviewed = tmp_path / "reviewed.csv"
    pd.DataFrame({"dawn_chorus_id": [1], "reviewed": [True]}).to_csv(reviewed, index=False)
    resolved = master.preserve_sentinel_time_selection_warnings(again.copy(), previous2,
                {"master_table": {"sentinel_time_rechecked_ids_csv": str(reviewed)}})
    assert resolved.sentinel_has_issues.tolist() == [False, False]
    assert resolved.sentinel_issue_codes.tolist() == ["", ""]


def test_time_audit_treats_new_source_ids_as_new_not_modified(tmp_path):
    from audit_recording_times import audit
    source = tmp_path / 'source.csv'
    pd.DataFrame({
        'id': [1, 2], 'country': ['Germany', 'Germany'], 'lat': [49.,49.], 'lng':[8.,8.],
        'datetime': ['2020-05-04T05:57:00Z', '2020-05-04T03:57:00Z'],
        'localtimes': ['', '2020-05-04T05:57:00+02:00'],
    }).to_csv(source, index=False)
    baseline = tmp_path / 'old_master.csv'
    pd.DataFrame({'dawn_chorus_id':[1], 'datetime_local':['2020.05.04 07:57:00'],
                  'datetime_utc':['2020-05-04T05:57:00Z']}).to_csv(baseline, index=False)
    result = audit(source, baseline, tmp_path / 'report')
    assert result['rows'] == 2
    assert result['previously_in_master'] == 1
    assert result['new_since_baseline'] == 1
    assert result['clock_changes'] == 1
    assert result['local_date_changes'] == 0
    assert result['utc_date_changes'] == 0
    assert pd.read_csv(tmp_path / 'report' / 'recording_time_changes.csv').id.tolist() == [1]

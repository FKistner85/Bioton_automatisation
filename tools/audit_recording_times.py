"""Audit every source row and optionally validate the regenerated master.

Independent pandas timezone conversions check the zoneinfo-based extractor.
No source or production product is modified by this tool.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import Step_1_metadata_extraction as step1
from recording_time import TIME_POLICY_VERSION


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def audit(source_path, baseline_path, output, master_path=None, short_path=None):
    output.mkdir(parents=True, exist_ok=True)
    source = step1.read_source(source_path, country_column="country", country_value="Germany")
    clean, log = step1.build_outputs(source, "Europe/Berlin")
    local = source.localtimes.astype("string").str.strip().replace("", pd.NA)
    present = local.notna()
    reference = pd.to_datetime(source.datetime, format="mixed", utc=True, errors="coerce")
    actual_utc = pd.to_datetime(clean.datetime, format="mixed", utc=True, errors="coerce")
    actual_local = actual_utc.dt.tz_convert("Europe/Berlin").dt.tz_localize(None)
    raw_local_clock = pd.to_datetime(local.str.replace(r"(Z|[+-]\d{2}:?\d{2})$", "", regex=True), format="mixed", errors="coerce")
    # All present local clock components must survive, at product precision.
    local_matches = actual_local[present].eq(raw_local_clock[present].dt.floor("s"))
    fallback_matches = actual_utc[~present].eq(reference[~present].dt.floor("s"))
    assert local_matches.all(), "A supplied local clock changed or could not be resolved; inspect source"
    assert fallback_matches.all(), "UTC fallback failed independent instant comparison"
    assert actual_utc.notna().all(), "Unresolved recording timestamps"
    # Independently require the selected offset to be the Berlin offset.
    for raw, utc in zip(clean.datetime, actual_utc):
        assert pd.Timestamp(raw).utcoffset() == utc.tz_convert("Europe/Berlin").utcoffset()
    assert len(source) == source.id.nunique() == len(clean)
    audit_rows = log.copy()
    audit_rows["datetime_local"] = actual_local.dt.strftime("%Y-%m-%d %H:%M:%S")
    audit_rows["datetime_utc"] = actual_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    before = pd.read_csv(baseline_path, dtype={"dawn_chorus_id": "Int64"}, low_memory=False).set_index("dawn_chorus_id")
    old_raw = source.id.map(before.datetime_local).astype("string")
    old_local = pd.to_datetime(old_raw.str.replace(r"(Z|[+-]\d{2}:?\d{2})$", "", regex=True), format="mixed", errors="coerce")
    audit_rows["previous_datetime_local"] = old_raw
    audit_rows["clock_change_seconds"] = (actual_local - old_local).dt.total_seconds()
    audit_rows["local_date_changed"] = actual_local.dt.date.ne(old_local.dt.date)
    old_utc = pd.to_datetime(source.id.map(before.datetime_utc), utc=True, errors="coerce", format="mixed")
    audit_rows["utc_date_changed"] = actual_utc.dt.date.ne(old_utc.dt.date)
    changed = audit_rows.clock_change_seconds.ne(0)
    issues = Counter(code for value in log.timestamp_issue_codes for code in value.split("|") if code)
    # Calendar windows containing a German offset change require DST-aware QC.
    day = actual_local.dt.normalize()
    starts = (day - pd.Timedelta(days=10)).dt.tz_localize("Europe/Berlin").dt.tz_convert("UTC")
    ends = (day + pd.Timedelta(days=1)).dt.tz_localize("Europe/Berlin").dt.tz_convert("UTC")
    audit_rows["expected_weather_hours_10_preceding_days"] = ((ends - starts).dt.total_seconds() / 3600).astype(int)
    audit_rows.to_csv(output / "recording_time_audit_all.csv", index=False)
    audit_rows[changed].to_csv(output / "recording_time_changes.csv", index=False)
    audit_rows[log.timestamp_status.ne("validated") | log.coordinate_check.ne("within_broad_germany_bounds")].to_csv(output / "recording_time_conflicts.csv", index=False)
    audit_rows.loc[audit_rows.local_date_changed, ["id", "previous_datetime_local", "datetime_local"]].to_csv(output / "weather_changed_date_ids.csv", index=False)
    audit_rows.loc[audit_rows.utc_date_changed, ["id", "datetime_local", "datetime_utc"]].to_csv(output / "sentinel_changed_utc_date_ids.csv", index=False)
    audit_rows.loc[audit_rows.expected_weather_hours_10_preceding_days.ne(264), ["id", "datetime_local", "expected_weather_hours_10_preceding_days"]].to_csv(output / "weather_dst_window_ids.csv", index=False)
    summary = {
        "policy": TIME_POLICY_VERSION, "source": str(source_path), "source_sha256": sha(source_path),
        "baseline": str(baseline_path), "baseline_sha256": sha(baseline_path),
        "rows": len(source), "localtimes_present_preserved": int(present.sum()), "utc_fallback": int((~present).sum()),
        "unresolved": int(actual_utc.isna().sum()), "local_clock_mismatches": int((~local_matches).sum()),
        "utc_fallback_mismatches": int((~fallback_matches).sum()),
        "clock_changes": int(changed.sum()), "clock_change_seconds_counts": {str(k): int(v) for k,v in audit_rows.loc[changed, "clock_change_seconds"].value_counts().items()},
        "local_date_changes": int(audit_rows.local_date_changed.sum()),
        "utc_date_changes": int(audit_rows.utc_date_changed.sum()),
        "timestamp_status_counts": log.timestamp_status.value_counts().to_dict(), "issue_counts": dict(issues),
        "coordinate_check_counts": log.coordinate_check.value_counts().to_dict(),
        "weather_window_hour_counts": {str(k): int(v) for k,v in audit_rows.expected_weather_hours_10_preceding_days.value_counts().items()},
        "datetime_min": str(actual_local.min()), "datetime_max": str(actual_local.max()),
    }
    if master_path:
        master = pd.read_csv(master_path, dtype=str, keep_default_na=False).set_index("dawn_chorus_id")
        assert set(master.index) == set(source.id.astype(str)) and master.index.is_unique
        expected = audit_rows.assign(dawn_chorus_id=source.id.astype(str)).set_index("dawn_chorus_id")
        master = master.loc[expected.index]
        for col in ["datetime_local", "datetime_utc"]:
            assert master[col].eq(expected[col]).all(), col
        for col in ["lat", "lon"]:
            expected_coords = source.set_index(source.id.astype(str))["lat" if col == "lat" else "lng"]
            assert pd.to_numeric(master[col]).eq(pd.to_numeric(expected_coords.loc[master.index])).all(), col
        summary["master"] = str(master_path)
        summary["master_sha256"] = sha(master_path)
        summary["master_all_rows_verified"] = True
        if short_path:
            short = pd.read_csv(short_path, dtype=str, keep_default_na=False).set_index("dawn_chorus_id")
            assert short.index.is_unique and set(short.index) == set(master.index)
            pd.testing.assert_frame_equal(short.loc[master.index], master[short.columns], check_names=False)
            summary["short_master"] = str(short_path)
            summary["short_master_sha256"] = sha(short_path)
            summary["short_all_cells_verified"] = True
    (output / "recording_time_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--short", type=Path)
    args = parser.parse_args()
    audit(args.source, args.baseline, args.output, args.master, args.short)

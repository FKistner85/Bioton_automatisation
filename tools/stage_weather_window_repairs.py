"""Stage strictly subtractive weather repairs locally, never modify LSDF files."""
from __future__ import annotations
import csv
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import Step_5_1_Weather_inventory as inventory


def trim_extra_boundary_rows(source: Path, target: Path, recording: str):
    """Only remove hours outside the window; never fill, shift or deduplicate."""
    with source.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    header, data = rows[0], rows[1:]
    column = header.index('datetime')
    parsed = pd.to_datetime([row[column] for row in data], errors='raise')
    day = pd.Timestamp(recording).normalize()
    expected = pd.date_range(day-pd.Timedelta(days=10), day+pd.Timedelta(days=1), tz='Europe/Berlin', freq='h', inclusive='left').tz_localize(None)
    mask = parsed.isin(expected)
    retained = [row for row, keep in zip(data, mask) if keep]
    kept = parsed[mask]
    if not kept.sort_values().equals(expected.sort_values()):
        raise ValueError('Missing or duplicated expected hours; cannot repair by trimming')
    if len(retained) >= len(data):
        raise ValueError('No removable outside-window rows')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(retained)
    with target.open(encoding='utf-8', newline='') as handle:
        verified = list(csv.reader(handle))
    assert verified == [header, *retained], 'Retained measurement strings changed'
    return len(data)-len(retained)


def main():
    out = ROOT / 'output/weather_review'
    checks = pd.read_csv(out / 'weather_checks.csv', dtype=str, keep_default_na=False)
    config = json.loads((ROOT / 'config.horeka.json').read_text())
    candidates = checks.loc[pd.to_numeric(checks.missing_hours, errors='coerce').eq(0) & pd.to_numeric(checks.extra_hours, errors='coerce').gt(0)]
    records = []
    for row in candidates.to_dict('records'):
        source = out / 'weather_cache' / row['filename']
        target = out / 'staged_weather' / row['filename']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
        removed = trim_extra_boundary_rows(source, target, row['datetime_local'])
        result = inventory.inspect_weather_csv(target, row['datetime_local'], config['weather_inventory'], config['weather_download'])
        assert result['datetime_interval_ok'] and result['expected_time_window_ok']
        assert result['issues'] in ('', 'missing_value'), result
        records.append({'dawn_chorus_id': row['dawn_chorus_id'], 'removed_rows': removed,
                        'old_codes': row['old_codes'], 'checked_before_codes': row['issues'],
                        'staged_codes': result['issues'], 'source_sha256': row['sha256'],
                        'staged_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'staged_file': str(target.relative_to(out))})
    pd.DataFrame(records).to_csv(out / 'staged_repair_manifest.csv', index=False)
    summary = {'staged_files': len(records), 'fully_clean_after_staging': sum(r['staged_codes']=='' for r in records),
               'missing_values_remain': sum(r['staged_codes']=='missing_value' for r in records),
               'removed_rows': sum(r['removed_rows'] for r in records),
               'retained_measurement_strings_unchanged': True, 'lsdf_modified': False,
               'master_modified': False}
    (out / 'repair_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

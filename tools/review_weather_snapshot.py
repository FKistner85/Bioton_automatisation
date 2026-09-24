"""Read-only LSDF weather review; all outputs remain in a separate local folder."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import Step_5_1_Weather_inventory as inventory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/weather_review')
    parser.add_argument('--weather-dir', type=Path, default=Path('L:/PointData/Weather/Hostrada'))
    args = parser.parse_args()
    out = args.output
    snapshot = out / 'snapshot'
    m = pd.read_csv(snapshot / 'Bio_O_Ton_Master.csv', dtype=str, keep_default_na=False)
    meta = pd.read_csv(snapshot / 'metadata.csv', dtype=str, keep_default_na=False).set_index('id')
    compact = pd.read_csv(snapshot / 'inventory_compact.csv', dtype=str, keep_default_na=False).set_index('dawn_chorus_id')
    assert m.dawn_chorus_id.is_unique and meta.index.is_unique and compact.index.is_unique
    local = pd.to_datetime(m.dawn_chorus_id.map(meta.datetime), format='mixed', utc=True).dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
    assert local.eq(pd.to_datetime(m.datetime_local)).all(), 'Master and metadata clocks differ'
    codes = m.dawn_chorus_id.map(compact.issue_codes)
    flagged = m.weather_point_has_issues.str.lower().eq('true') | codes.fillna('').ne('') | codes.ne(m.weather_point_issue_codes)
    control = m.loc[~flagged].sample(n=min(500, int((~flagged).sum())), random_state=20260923)
    selected = pd.concat([m.loc[flagged], control]).drop_duplicates('dawn_chorus_id')
    selected[['dawn_chorus_id', 'datetime_local', 'weather_point_issue_codes']].to_csv(out / 'selected_ids.csv', index=False)
    config = json.loads((ROOT / 'config.horeka.json').read_text(encoding='utf-8'))
    cache = out / 'weather_cache'
    cache.mkdir(exist_ok=True)
    results_path = out / 'file_checks.jsonl'
    done = {}
    if results_path.exists():
        done = {r['dawn_chorus_id']: r for r in (json.loads(line) for line in results_path.read_text().splitlines())}
    def check(row):
        ident = row['dawn_chorus_id']
        source = args.weather_dir / f'weather_{ident}.csv'
        dest = cache / source.name
        result = dict(dawn_chorus_id=ident, old_codes=row['weather_point_issue_codes'],
                      inventory_codes=compact.loc[ident, 'issue_codes'],
                      datetime_local=row['datetime_local'], control=not bool(flagged.loc[row['Index']]),
                      source=str(source))
        try:
            before = source.stat()
            shutil.copyfile(source, dest)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise OSError('Source changed during copy')
            checked = inventory.inspect_weather_csv(dest, row['datetime_local'], config['weather_inventory'], config['weather_download'])
            result.update(checked)
            result['sha256'] = sha(dest)
            result['source_mtime_ns'] = before.st_mtime_ns
            frame = pd.read_csv(dest)
            parsed = pd.to_datetime(frame.get('datetime', pd.Series(dtype=str)), errors='coerce')
            day = pd.Timestamp(row['datetime_local']).normalize()
            # Independent calendar-boundary oracle; do not reuse pipeline time helper.
            expected = pd.date_range(day - pd.Timedelta(days=10), day + pd.Timedelta(days=1), freq='h', tz='Europe/Berlin', inclusive='left').tz_localize(None)
            observed_counts = parsed.value_counts()
            expected_counts = expected.value_counts()
            delta = observed_counts.subtract(expected_counts, fill_value=0)
            result['missing_hours'] = int(-delta[delta < 0].sum())
            result['extra_hours'] = int(delta[delta > 0].sum())
            result['independent_time_ok'] = bool(parsed.notna().all() and (delta == 0).all())
            assert result['independent_time_ok'] == checked['datetime_interval_ok']
            result['classification'] = ('verified_clean' if not checked['has_issues'] else
                'values_only' if checked['issues'] == 'missing_value' else 'time_or_structure_issue')
        except FileNotFoundError:
            # Missing is only a file conclusion if the mounted directory remains readable.
            if not args.weather_dir.is_dir():
                result.update(classification='access_error', error='weather directory unavailable')
            else:
                result.update(classification='missing_file', weather_exists=False, has_issues=True, issues='missing_file')
        except Exception as exc:
            result.update(classification='access_or_check_error', error=f'{type(exc).__name__}: {exc}')
        return result
    tasks = [r._asdict() for r in selected.itertuples() if r.dawn_chorus_id not in done]
    print(f'Selected {len(selected)}, remaining {len(tasks)}, controls {len(control)}', flush=True)
    with results_path.open('a', encoding='utf-8') as log, ThreadPoolExecutor(max_workers=8) as pool:
        for index, future in enumerate(as_completed([pool.submit(check, row) for row in tasks]), 1):
            result = future.result()
            done[result['dawn_chorus_id']] = result
            log.write(json.dumps(result, default=str) + '\n')
            log.flush()
            if index % 250 == 0:
                print(f'Checked {index}/{len(tasks)}', flush=True)
    rows = pd.DataFrame([done[i] for i in selected.dawn_chorus_id])
    rows.to_csv(out / 'weather_checks.csv', index=False)
    summary = {'master_rows': len(m), 'selected': len(selected), 'controls': len(control),
               'classifications': rows.classification.value_counts().to_dict(),
               'master_metadata_clock_mismatches': 0,
               'master_inventory_code_mismatches': int(codes.ne(m.weather_point_issue_codes).sum()),
               'snapshot_sha256': {p.name: sha(p) for p in snapshot.iterdir() if p.is_file()}}
    (out / 'audit_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()

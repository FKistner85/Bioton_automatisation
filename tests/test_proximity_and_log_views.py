"""Regression coverage for advisory flags and nondestructive Slurm log views."""
import math
from pathlib import Path
import sys
import tempfile
import random

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools")]
from spatiotemporal_duplicates import proximity_flags, EARTH_RADIUS_M
from organize_slurm_logs import organize


def frame(rows):
    return pd.DataFrame(rows, columns=["dawn_chorus_id", "lat", "lon", "datetime_utc"])


def test_proximity():
    degree = 180 / math.pi / EARTH_RADIUS_M
    table = frame([
        ("a", 0, 0, "2024-05-01T00:00:00Z"),
        ("b", 0, 10 * degree, "2024-05-01T00:05:00Z"),
        ("c", 0, 20 * degree, "2024-05-01T00:10:00Z"),
        ("d", 0, 20 * degree, "2024-05-01T00:40:01Z"),
        ("e", None, 0, "2024-05-01T00:00:00Z"),
        ("f", 0, 0, "2024-05-01 00:00:00"),
    ])
    flags = proximity_flags(table)
    assert flags.duplicate_neighbor_count.iloc[:4].tolist() == [1, 2, 1, 0]
    assert flags.spatiotemporal_cluster_size.iloc[:4].tolist() == [3, 3, 3, 1]
    assert pd.isna(flags.duplicate_candidate.iloc[4])
    assert pd.isna(flags.duplicate_candidate.iloc[5])
    shuffled = table.iloc[::-1]
    pd.testing.assert_frame_equal(flags, proximity_flags(shuffled).sort_index())
    # Opposite sides of the date line, and UTC-offset equivalence.
    wrap = frame([("1", 0, 179.99999, "2024-10-27T02:30:00+02:00"),
                  ("2", 0, -179.99999, "2024-10-27T00:30:00Z"),
                  ("3", 0, -179.99999, "2024-10-27T02:30:00+01:00")])
    assert proximity_flags(wrap).duplicate_candidate.tolist() == [True, True, False]
    assert proximity_flags(frame([])).empty
    try:
        proximity_flags(table, {"duplicate_distance_m": -1})
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid threshold accepted")


def test_log_views():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        names = ["20260824T135539Z_bio_step62_5106467_0.out",
                 "20260824T135539Z_bio_step62_5106467_1.err",
                 "20260824T135539Z_bio_master_final_5106473.out"]
        for name in names:
            (root / name).write_text(name)
        result = organize(root)
        assert result['steps'] == 2
        assert len(list((root / 'current' / 'bio_step62').iterdir())) == 2
        assert organize(root) == result
        newer = "20260917T100000Z_bio_step62_6000000_0.out"
        (root / newer).write_text('new')
        unrelated = root / 'current' / 'bio_step62' / 'notes.txt'
        unrelated.write_text('keep')
        organize(root)
        assert sorted(p.name for p in unrelated.parent.iterdir()) == [newer, 'notes.txt']
        for name in names:
            assert (root / name).read_text() == name
        assert len(list((root / 'archive').rglob('*.out'))) == 3
        # Hard links follow writes to original files without copying data.
        (root / newer).write_text('updated')
        assert (root / 'current' / 'bio_step62' / newer).read_text() == 'updated'


def test_against_brute_force():
    rng = random.Random(17)
    base = pd.Timestamp('2026-05-01T00:00:00Z')
    rows = [(str(i), 49 + rng.uniform(-.0002, .0002), 8 + rng.uniform(-.0002, .0002),
             (base + pd.Timedelta(seconds=rng.randrange(900))).isoformat()) for i in range(150)]
    result = proximity_flags(frame(rows))
    expected = [0] * len(rows)
    for i, (_, lat, lon, t) in enumerate(rows):
        for j in range(i):
            _, lat2, lon2, t2 = rows[j]
            hav = math.sin(math.radians(lat-lat2)/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(lat2))*math.sin(math.radians(lon-lon2)/2)**2
            distance = 2*EARTH_RADIUS_M*math.asin(math.sqrt(hav))
            if distance <= 10 and abs((pd.Timestamp(t)-pd.Timestamp(t2)).total_seconds()) <= 300:
                expected[i] += 1
                expected[j] += 1
    assert result.duplicate_neighbor_count.tolist() == expected


def test_incremental_master_neighbors():
    import Step_7_0_update_master_table as master
    from unittest.mock import patch
    import json
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        metadata = root / 'metadata'
        metadata.mkdir()
        clean = pd.DataFrame({'id': [1], 'lat': [49], 'lng': [8],
                              'datetime': ['2026-05-01T08:00:00+02:00']})
        clean.to_csv(metadata / 'dawnchorus_metadata_clean.csv', index=False)
        assignment=root/'points.csv'
        pd.DataFrame({'id':[1,2], 'lat':[49,49], 'lon':[8,8],
                      'inside_lrt_polygon':[False,False], 'lrt_polygon_count':[0,0]}).to_csv(assignment,index=False)
        config = root / 'config.json'
        config.write_text(json.dumps({'status_dir': str(metadata), 'processed_root': str(root),
                                     'point_lrt_assignment':{'output_csv':str(assignment)},
                                     'dawn_chorus_csv': str(root / 'unused.csv')}))
        with patch.object(sys, 'argv', ['master', '--config', str(config)]):
            assert master.main() == 0
        output = root / 'Bio_O_Ton_Master.csv'
        first = pd.read_csv(output)
        assert not first.duplicate_candidate.iloc[0]
        clean = pd.concat([clean, clean.assign(id=2)], ignore_index=True)
        clean.to_csv(metadata / 'dawnchorus_metadata_clean.csv', index=False)
        ids = root / 'ids.csv'
        ids.write_text('dawn_chorus_id\n2\n')
        with patch.object(sys, 'argv', ['master', '--config', str(config), '--ids-file', str(ids)]):
            assert master.main() == 0
        result = pd.read_csv(output)
        assert result.duplicate_candidate.tolist() == [True, True]
        assert result.spatiotemporal_cluster_size.tolist() == [2, 2]
        assert result.sound_status.iloc[0] == first.sound_status.iloc[0]


if __name__ == '__main__':
    test_proximity()
    test_log_views()
    test_against_brute_force()
    test_incremental_master_neighbors()
    print('test_proximity_and_log_views.py: OK')

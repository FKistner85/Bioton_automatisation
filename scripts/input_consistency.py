"""Checks shared by planning, point assignment and master publication."""
from pathlib import Path

import pandas as pd


def indexed_points(frame):
    frame = frame.copy()
    key = next((c for c in ('dawn_chorus_id', 'id') if c in frame), None)
    if key is None:
        return pd.DataFrame(columns=['lat', 'lon'], index=pd.Index([], name='id'))
    ids = pd.to_numeric(frame[key], errors='coerce').astype('Int64').astype('string')
    frame.index = ids
    frame = frame.loc[ids.notna().to_numpy()]
    if 'lon' not in frame and 'lng' in frame:
        frame['lon'] = frame['lng']
    return frame


def point_output_gaps(points, output, log_path=None):
    """Return missing/stale/duplicate IDs; an explicit negative match is valid."""
    source = indexed_points(points)
    path = Path(output)
    if not path.is_file() or not path.stat().st_size:
        return set(source.index.astype(str))
    actual = indexed_points(pd.read_csv(path, low_memory=False))
    duplicate = set(actual.index[actual.index.duplicated(False)].astype(str))
    actual = actual.loc[~actual.index.duplicated(keep='last')]
    # Older Step-2.2 tables kept coordinates only in their paired processing log.
    if not {'lat', 'lon'}.issubset(actual.columns) and log_path and Path(log_path).is_file():
        log = indexed_points(pd.read_csv(log_path, low_memory=False))
        duplicate.update(log.index[log.index.duplicated(False)].astype(str))
        log = log.loc[~log.index.duplicated(keep='last')]
        for column in ('lat', 'lon'):
            if column not in actual and column in log:
                actual[column] = log[column].reindex(actual.index)
    gaps = set(source.index.difference(actual.index).astype(str)) | duplicate
    shared = source.index.intersection(actual.index)
    for column in ('lat', 'lon'):
        if column not in source or column not in actual:
            gaps.update(shared.astype(str))
            continue
        a = pd.to_numeric(source.loc[shared, column], errors='coerce')
        b = pd.to_numeric(actual.loc[shared, column], errors='coerce')
        same = (a.isna() & b.isna()) | a.sub(b).abs().le(1e-9)
        gaps.update(shared[~same].astype(str))
    return gaps & set(source.index.astype(str))


def require_point_coverage(points, config):
    path = config.get('point_lrt_assignment', {}).get('output_csv', '')
    gaps = point_output_gaps(points, path, config.get('point_lrt_assignment', {}).get('log_csv'))
    if gaps:
        raise ValueError(
            f'POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated '
            f'or at different coordinates in {path}. Run Step 2.2 first; '
            'the existing master has not been replaced.'
        )


def guard_source_population(current_ids, previous_ids, settings=None):
    """Reject a truncated snapshot before any metadata or master is changed.

    Normal individual deletions still propagate. An intentional large reduction
    requires the explicit metadata_extraction.allow_large_source_reduction flag.
    """
    current = {str(int(v)) for v in current_ids}
    previous = {str(int(v)) for v in previous_ids}
    settings = settings or {}
    removed = previous - current
    if (previous and len(removed) > max(10, len(previous) * 0.2)
            and not settings.get('allow_large_source_reduction', False)):
        raise ValueError(
            f'SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; '
            f'{len(removed)} of {len(previous)} existing IDs would disappear. '
            'Restore the complete original source. For an intentional reduction '
            'set metadata_extraction.allow_large_source_reduction=true explicitly.'
        )

"""Advisory proximity flags; never remove recordings or alter readiness.

Spatial hashing of Earth-centred coordinates plus a sliding UTC window avoids
an all-pairs distance matrix. Clusters are connected components, not cliques.
"""
from collections import defaultdict, deque
from datetime import datetime
from itertools import product
import math

import pandas as pd

FLAG_COLUMNS = [
    "proximity_check_status", "duplicate_candidate", "duplicate_neighbor_count",
    "spatiotemporal_cluster_id", "spatiotemporal_cluster_size",
]
EARTH_RADIUS_M = 6371008.8


def proximity_flags(table, settings=None):
    settings = settings or {}
    radius = float(settings.get("duplicate_distance_m", 10))
    seconds = float(settings.get("duplicate_seconds", 300))
    cluster_radius = float(settings.get("cluster_distance_m", 50))
    cluster_seconds = float(settings.get("cluster_seconds", 1800))
    if not all(math.isfinite(v) and v > 0 for v in (radius, seconds, cluster_radius, cluster_seconds)):
        raise ValueError("Proximity thresholds must be finite and positive")
    if radius > cluster_radius or seconds > cluster_seconds:
        raise ValueError("Cluster thresholds must include duplicate thresholds")
    if cluster_radius > math.pi * EARTH_RADIUS_M:
        raise ValueError("Cluster radius cannot exceed half Earth's circumference")
    ids = table["dawn_chorus_id"].astype(str).tolist()
    if len(set(ids)) != len(ids):
        raise ValueError("Proximity input must contain unique recording IDs")
    n = len(ids)
    parents = list(range(n))
    counts = [0] * n
    valid = [False] * n
    points = []
    for i, row in enumerate(table[["lat", "lon", "datetime_utc"]].itertuples(index=False, name=None)):
        try:
            lat, lon = float(row[0]), float(row[1])
            timestamp = datetime.fromisoformat(str(row[2]).replace("Z", "+00:00"))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or timestamp.utcoffset() is None:
                continue
            lat, lon = math.radians(lat), math.radians(lon)
            xyz = (EARTH_RADIUS_M * math.cos(lat) * math.cos(lon),
                   EARTH_RADIUS_M * math.cos(lat) * math.sin(lon), EARTH_RADIUS_M * math.sin(lat))
            points.append((timestamp.timestamp(), i, xyz))
            valid[i] = True
        except (TypeError, ValueError, OverflowError):
            continue

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    buckets = defaultdict(dict)
    active = deque()
    offsets = list(product((-1, 0, 1), repeat=3))
    # Chord and great-circle distance have equivalent threshold tests.
    direct_chord = 2 * EARTH_RADIUS_M * math.sin(radius / (2 * EARTH_RADIUS_M))
    cluster_chord = 2 * EARTH_RADIUS_M * math.sin(cluster_radius / (2 * EARTH_RADIUS_M))
    for t, i, xyz in sorted(points):
        while active and t - active[0][0] > cluster_seconds:
            _, old_i, old_cell = active.popleft()
            del buckets[old_cell][old_i]
            if not buckets[old_cell]:
                del buckets[old_cell]
        cell = tuple(math.floor(v / cluster_radius) for v in xyz)
        for delta in offsets:
            neighbor = tuple(a + b for a, b in zip(cell, delta))
            for j, (other_t, other_xyz) in buckets.get(neighbor, {}).items():
                d2 = sum((a - b) ** 2 for a, b in zip(xyz, other_xyz))
                if d2 <= cluster_chord ** 2 + 1e-8:
                    a, b = find(i), find(j)
                    parents[a] = b
                    if t - other_t <= seconds and d2 <= direct_chord ** 2 + 1e-8:
                        counts[i] += 1
                        counts[j] += 1
        buckets[cell][i] = (t, xyz)
        active.append((t, i, cell))
    groups = defaultdict(list)
    for i in range(n):
        if valid[i]:
            groups[find(i)].append(i)
    labels, sizes = [""] * n, [0] * n
    for members in groups.values():
        label = "st_" + min(ids[i] for i in members) if len(members) > 1 else ""
        for i in members:
            labels[i], sizes[i] = label, len(members)
    return pd.DataFrame({
        "proximity_check_status": ["checked" if v else "missing_or_invalid_space_time" for v in valid],
        "duplicate_candidate": pd.array([c > 0 if v else pd.NA for c, v in zip(counts, valid)], dtype="boolean"),
        "duplicate_neighbor_count": pd.array([c if v else pd.NA for c, v in zip(counts, valid)], dtype="Int64"),
        "spatiotemporal_cluster_id": labels,
        "spatiotemporal_cluster_size": pd.array([s if v else pd.NA for s, v in zip(sizes, valid)], dtype="Int64"),
    }, index=table.index)

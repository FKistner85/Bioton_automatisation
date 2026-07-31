#!/usr/bin/env python3
"""Synthetic tests for incremental weather selection and Slurm sharding."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# These selection tests do not access HTTP, NetCDF or projections. Lightweight
# stubs keep them runnable in the repository's minimal local test runtime.
sys.modules.setdefault("requests", types.ModuleType("requests"))
sys.modules.setdefault("xarray", types.ModuleType("xarray"))
pyproj_stub = types.ModuleType("pyproj")
pyproj_stub.Transformer = object
sys.modules.setdefault("pyproj", pyproj_stub)
tqdm_stub = types.ModuleType("tqdm")
tqdm_stub.tqdm = lambda iterable=None, *args, **kwargs: iterable
sys.modules.setdefault("tqdm", tqdm_stub)

from Step_5_2_download_weather_data import (
    load_input_recordings,
    recording_shard,
    select_recordings,
    verify_requested_outputs,
)


def test_incremental_scope_and_shards() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "metadata.csv"
        pd.DataFrame(
            {
                "id": [1.0, 2.0, 3.0, 4.0],
                "lat": [49.0] * 4,
                "lon": [8.0] * 4,
                "datetime": ["2024-05-01T05:00:00+02:00"] * 4,
            }
        ).to_csv(source, index=False)
        recordings = load_input_recordings(source)
        assert recordings["ID"].tolist() == ["1", "2", "3", "4"]
        selected = select_recordings(
            recordings,
            {"2", "4"},
            ids_file_supplied=True,
            task_index=0,
            task_count=1,
        )
        assert selected["ID"].tolist() == ["2", "4"]
        shard_union: set[str] = set()
        for task_index in range(3):
            shard = select_recordings(
                recordings,
                set(recordings["ID"]),
                ids_file_supplied=True,
                task_index=task_index,
                task_count=3,
            )
            assert shard_union.isdisjoint(set(shard["ID"]))
            shard_union.update(shard["ID"])
        assert shard_union == {"1", "2", "3", "4"}
        assert recording_shard("4", 3) == 1


def test_weather_output_verification() -> None:
    with tempfile.TemporaryDirectory() as raw:
        output_dir = Path(raw)
        (output_dir / "weather_1.csv").write_text("datetime,value\nx,1\n")
        complete, missing = verify_requested_outputs(output_dir, {"1", "2"})
        assert complete == ["1"]
        assert missing == ["2"]


if __name__ == "__main__":
    test_incremental_scope_and_shards()
    test_weather_output_verification()
    print("test_weather_download_selection.py: OK")

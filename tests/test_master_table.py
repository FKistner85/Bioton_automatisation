#!/usr/bin/env python3
"""Synthetic tests for the final master table builder."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import Step_7_0_update_master_table as master
from common import (
    attach_optional_grid_majority,
    susi_10m_grid_id_from_parent,
)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def test_master_table_minimal_build() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        processed = root / "processed"
        status = processed / "step_1_metadata"
        weather = root / "PointData" / "Weather" / "Hostrada"
        output_csv = root / "Bio_O_Ton_Master.csv"
        weather_inventory = processed / "step_5_1" / "weather_inventory_compact.csv"
        status_events = processed / "_control" / "status_events.csv"

        write_csv(
            status / "dawnchorus_metadata_clean.csv",
            pd.DataFrame(
                {
                    "id": [1],
                    "datetime": ["2024-05-01T04:30:00+02:00"],
                    "lat": [49.0],
                    "lon": [8.4],
                }
            ),
        )
        write_csv(
            status / "dawnchorus_metadata_log.csv",
            pd.DataFrame(
                {
                    "id": [1],
                    "datetime_source": ["localtimes"],
                    "conversion_needed": [True],
                    "conversion_step": ["unit_test"],
                }
            ),
        )
        write_csv(
            weather / "weather_1.csv",
            pd.DataFrame(
                {
                    "datetime": pd.date_range("2024-04-21", periods=264, freq="h"),
                    "air_temperature_mean": [10.0] * 264,
                    "cloud_cover": [50.0] * 264,
                    "humidity_relative": [70.0] * 264,
                    "radiation_downwelling": [100.0] * 264,
                    "wind_direction": [180.0] * 264,
                    "wind_speed": [3.0] * 264,
                }
            ),
        )
        write_csv(
            weather_inventory,
            pd.DataFrame(
                {
                    "dawn_chorus_id": [1],
                    "weather_exists": [True],
                    "weather_has_issues": [False],
                    "has_issues": [False],
                    "issue_codes": [""],
                }
            ),
        )
        config = {
            "dawn_chorus_csv": str(root / "dawn.csv"),
            "status_dir": str(status),
            "processed_root": str(processed),
            "pipeline_control": {
                "status_event_csv": str(status_events),
            },
            "audio_inventory": {},
            "photo_inventory": {},
            "sentinel2_inventory": {},
            "weather_download": {
                "output_dir": str(weather),
                "cache_dir": str(root / "cache"),
            },
            "weather_inventory": {
                "compact_log": str(weather_inventory),
                "expected_rows": 264,
                "expected_interval_seconds": 3600,
                "required_columns": [
                    "air_temperature_mean",
                    "cloud_cover",
                    "humidity_relative",
                    "radiation_downwelling",
                    "wind_direction",
                    "wind_speed",
                ],
            },
            "hostrada_raster_products": {
                "output_root": str(processed / "step_5_4_hostrada_raster_products"),
                "resolution_m": 100,
            },
            "hostrada_raster_quality_check": {
                "output_dir": str(processed / "step_5_5_hostrada_raster_quality_check"),
            },
            "master_table": {
                "output_csv": str(output_csv),
                "output_parquet": str(root / "Bio_O_Ton_Master.parquet"),
                "summary_json": str(root / "Bio_O_Ton_Master_summary.json"),
                "weather_qc_workers": 1,
            },
        }
        # A checked negative match is distinct from an unprocessed recording.
        point_output = root / 'points.csv'
        write_csv(point_output, pd.DataFrame({'id': [1], 'lat': [49.0], 'lon': [8.4],
            'inside_lrt_polygon': [False], 'lrt_polygon_count': [0]}))
        config['point_lrt_assignment'] = {'output_csv': str(point_output)}
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        old_argv = sys.argv
        try:
            sys.argv = ["Step_7_0_update_master_table.py", "--config", str(config_path)]
            assert master.main() == 0
        finally:
            sys.argv = old_argv

        result = pd.read_csv(output_csv)
        assert len(result) == 1
        assert "weather_raster_hostrada_10m_exists" not in result.columns
        assert result.loc[0, "weather_point_exists"] in {True, "True", "true", 1}
        assert result.loc[0, "weather_raster_hostrada_100m_issue_codes"] == "missing_raster"
        assert result.loc[0, "weather_point_status"] == "validated"
        assert "weather_raster_hostrada_100m_missing" not in str(
            result.loc[0, "record_blocking_issue_codes"]
        )
        assert result.loc[0, "ready_for_formation_weather_raster_analysis_100m"] in {
            False, "False", "false", 0
        }
        assert result.loc[0, "record_status"] in {"partial", "has_issues"}
        events = pd.read_csv(status_events)
        assert set(events["field"]) == {"record_lifecycle"}
        assert events.loc[0, "current_value"] == "added"

        weather_status = pd.read_csv(weather_inventory)
        weather_status["weather_has_issues"] = True
        weather_status["issue_codes"] = "missing_value"
        weather_status.to_csv(weather_inventory, index=False)
        old_argv = sys.argv
        try:
            sys.argv = ["Step_7_0_update_master_table.py", "--config", str(config_path)]
            assert master.main() == 0
        finally:
            sys.argv = old_argv
        events = pd.read_csv(status_events)
        assert "weather_point_status" in set(events["field"])
        status_change = events[events["field"] == "weather_point_status"].iloc[-1]
        assert status_change["previous_value"] == "validated"
        assert status_change["current_value"] == "has_issues"

        def run_master(extra: list[str] | None = None) -> int:
            previous_argv = sys.argv
            try:
                sys.argv = ["Step_7_0_update_master_table.py", "--config", str(config_path), *(extra or [])]
                return master.main()
            finally:
                sys.argv = previous_argv

        def add_obsolete_row() -> None:
            existing = pd.read_csv(output_csv)
            obsolete = existing.iloc[[0]].copy()
            obsolete["dawn_chorus_id"] = 999
            write_csv(output_csv, pd.concat([existing, obsolete], ignore_index=True))

        # Full rebuild: the obsolete row is absent from clean metadata and must go.
        add_obsolete_row()
        assert run_master() == 0
        assert pd.read_csv(output_csv)["dawn_chorus_id"].tolist() == [1]
        events = pd.read_csv(status_events)
        assert ((events["dawn_chorus_id"] == 999) & (events["current_value"] == "deleted")).any()

        # Deletion-only incremental run: remove exactly the requested obsolete ID.
        add_obsolete_row()
        before = pd.read_csv(output_csv).query("dawn_chorus_id == 1").reset_index(drop=True)
        ids_file = root / "ids.csv"
        write_csv(ids_file, pd.DataFrame({"dawn_chorus_id": [999]}))
        assert run_master(["--ids-file", str(ids_file)]) == 0
        after = pd.read_csv(output_csv)
        pd.testing.assert_frame_equal(after, before)
        events = pd.read_csv(status_events)
        assert len(events[(events["dawn_chorus_id"] == 999) & (events["current_value"] == "deleted")]) == 2

        # An absent input is an error, not authorization to empty the master.
        clean_path = status / "dawnchorus_metadata_clean.csv"
        clean_bytes = clean_path.read_bytes()
        clean_path.unlink()
        assert run_master() == 1
        pd.testing.assert_frame_equal(pd.read_csv(output_csv), before)
        clean_path.write_bytes(clean_bytes)

        # A valid, header-only clean product means every source ID was removed.
        write_csv(clean_path, pd.DataFrame(columns=["id", "datetime", "lat", "lon"]))
        assert run_master() == 0
        assert pd.read_csv(output_csv).empty
        events = pd.read_csv(status_events)
        assert ((events["dawn_chorus_id"] == 1) & (events["current_value"] == "deleted")).any()


def test_incremental_master_merge_preserves_unaffected_rows() -> None:
    columns = master.MASTER_COLUMNS
    previous = pd.DataFrame(
        [
            {"dawn_chorus_id": "1", "sound_status": "validated"},
            {"dawn_chorus_id": "2", "sound_status": "missing"},
        ]
    )
    updates = pd.DataFrame(
        [{"dawn_chorus_id": "2", "sound_status": "validated"}]
    )
    for frame in [previous, updates]:
        for column in columns:
            if column not in frame.columns:
                frame[column] = pd.NA

    merged = master.merge_master_rows(previous[columns], updates[columns])
    merged = merged.set_index("dawn_chorus_id")
    assert merged.loc["1", "sound_status"] == "validated"
    assert merged.loc["2", "sound_status"] == "validated"
    pd.testing.assert_frame_equal(
        master.merge_master_rows(previous, pd.DataFrame()), previous.reset_index(drop=True)
    )
    deleted = master.merge_master_rows(previous, pd.DataFrame(), replace_ids={"2"})
    assert deleted["dawn_chorus_id"].tolist() == ["1"]


def test_default_output_paths_use_master_basename() -> None:
    root = Path("C:/temporary/project")
    csv_path, parquet_path, summary_path = master.output_paths(
        {}, root / "config.json"
    )
    assert csv_path == root / "Bio_O_Ton_Master.csv"
    assert parquet_path == root / "Bio_O_Ton_Master.parquet"
    assert summary_path == root / "Bio_O_Ton_Master_summary.json"


def test_susi_10m_grid_id_uses_the_parent_inspire_nomenclature() -> None:
    assert (
        susi_10m_grid_id_from_parent(
            "100mN6283E1192", 119200.1, 628300.1
        )
        == "10mN62830E11920"
    )
    assert (
        susi_10m_grid_id_from_parent(
            "100mN6283E1192", 119299.9, 628399.9
        )
        == "10mN62839E11929"
    )


def test_optional_majority_keeps_every_inspire_grid_cell() -> None:
    grid = pd.DataFrame({"grid_id": ["100mN1E1", "100mN1E2"]})
    majority = pd.DataFrame(
        {
            "grid_id": ["100mN1E1"],
            "majority_formation": ["Forests"],
        }
    )
    result = attach_optional_grid_majority(grid, majority, "grid_id")
    assert result["grid_id"].tolist() == ["100mN1E1", "100mN1E2"]
    assert result.loc[0, "majority_formation"] == "Forests"
    assert pd.isna(result.loc[1, "majority_formation"])


def test_10m_grid_assignment_exists_without_a_majority_product() -> None:
    original = master.compute_10m_grid_ids
    try:
        master.compute_10m_grid_ids = lambda table: pd.Series(
            ["10mN62830E11920"], index=table.index, dtype="string"
        )
        result = master.add_10m_formation(
            pd.DataFrame({"dawn_chorus_id": [1]}),
            {"susi_10m_products": {"final_parquet": ""}},
        )
    finally:
        master.compute_10m_grid_ids = original
    assert result.loc[0, "grid_10m_id"] == "10mN62830E11920"
    assert result.loc[0, "grid_10m_assignment_exists"]
    assert not result.loc[0, "grid_10m_has_majority_formation"]


def test_focused_refresh_preserves_nonformation_domains() -> None:
    current = pd.DataFrame({"dawn_chorus_id": ["1", "2"]})
    previous = pd.DataFrame(
        {
            "dawn_chorus_id": ["1", "3"],
            "sound_exists": [True, False],
            "sound_has_issues": [False, True],
            "weather_point_exists": [True, True],
            "weather_point_has_issues": [False, False],
            "formation_variant_count_expected": [12, 12],
        }
    )

    result = master.add_preserved_nonformation_domains(
        current,
        previous,
        {"lrt_variants": {"primary_suffix": "no_K_post2017"}},
    ).set_index("dawn_chorus_id")

    assert bool(result.loc["1", "sound_exists"])
    assert not bool(result.loc["1", "sound_has_issues"])
    assert pd.isna(result.loc["2", "sound_exists"])
    assert result.loc["1", "formation_variant_count_expected"] == 12
    assert result.loc["1", "formation_primary_variant"] == "no_K_post2017"


def test_mixed_timezone_local_wall_times() -> None:
    values = pd.Series(
        [
            "2024-05-01T04:30:00+02:00",
            "2024-12-01T05:45:00+01:00",
            "invalid",
        ]
    )
    parsed = master.parse_local_wall_times(values)
    assert parsed.dt.strftime("%Y-%m-%d %H:%M:%S").tolist()[:2] == [
        "2024-05-01 04:30:00",
        "2024-12-01 05:45:00",
    ]
    assert pd.isna(parsed.iloc[2])


def test_formation_variant_status_is_summarised() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        variant_table = root / "formation_variants.parquet"
        index_path = root / "variant_index.json"
        pd.DataFrame(
            {
                "dawn_chorus_id": [1, 1, 2, 2],
                "lrt_variant": ["primary", "alternative", "primary", "alternative"],
                "grid_100m_has_majority_formation": [True, True, True, False],
                "grid_10m_has_majority_formation": [True, False, True, False],
                "variant_100m_product_exists": [True] * 4,
                "variant_10m_product_exists": [True] * 4,
            }
        ).to_parquet(variant_table, index=False)
        index_path.write_text(json.dumps({"variant_count": 2}), encoding="utf-8")
        result = master.add_formation_variant_status(
            pd.DataFrame({"dawn_chorus_id": ["1", "2", "3"]}),
            {
                "lrt_variants": {
                    "primary_suffix": "primary",
                    "master_parquet": str(variant_table),
                    "index_json": str(index_path),
                }
            },
        ).set_index("dawn_chorus_id")
        assert result.loc["1", "formation_variants_with_100m_majority"] == 2
        assert result.loc["2", "formation_variants_with_10m_majority"] == 1
        assert result.loc["3", "formation_variants_with_100m_majority"] == 0
        assert result.loc[['1','2'], "formation_variant_products_complete"].all()
        assert not result.loc['3', "formation_variant_products_complete"]


def test_grid_ids_without_formation_or_assignment_products() -> None:
    import geopandas as gpd
    from pyproj import Transformer
    from shapely.geometry import box

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        grid_path = root / "grid.gpkg"
        gpd.GeoDataFrame(
            {"grid_id": ["100mN30000E40000", "100mN30000E40001"]},
            geometry=[box(4000000, 3000000, 4000100, 3000100),
                      box(4000100, 3000000, 4000200, 3000100)],
            crs="EPSG:3035",
        ).to_file(grid_path, layer="grid", driver="GPKG", engine="pyogrio")
        inverse = Transformer.from_crs(3035, 4326, always_xy=True)
        coordinates = [inverse.transform(x, 3000025) for x in (4000025, 4000125, 4000250)]
        table = pd.DataFrame({
            "dawn_chorus_id": ["1", "2", "3", "4"],
            "lon": [p[0] for p in coordinates] + [None],
            "lat": [p[1] for p in coordinates] + [None],
        }, index=[8, 3, 10, 2])
        config = {"point_lrt_assignment": {"grid_gpkg": str(grid_path)}}
        result = master.add_10m_formation(master.add_100m_formation(table.copy(), config), config)
        assert result["grid_100m_id"].iloc[:2].tolist() == ["100mN30000E40000", "100mN30000E40001"]
        assert result["grid_10m_id"].iloc[:2].tolist() == ["10mN300002E400002", "10mN300002E400012"]
        assert result["grid_100m_id"].iloc[2:].isna().all()
        assert result["grid_10m_id"].iloc[2:].isna().all()
        assert not result["grid_100m_has_majority_formation"].any()
        assert not result["grid_10m_has_majority_formation"].any()
        assert result.index.tolist() == table.index.tolist()

        # A legacy formation-filtered assignment must not block other cells.
        assignment = root / "assignment.csv"
        write_csv(assignment, pd.DataFrame({"id": [1], "grid_id": ["100mN30000E40000"],
                                            "majority_formation": ["forest"],
                                            "majority_value": [10000], "majority_delta": [10000]}))
        config["point_lrt_assignment"]["output_csv"] = str(assignment)
        partial = master.add_10m_formation(master.add_100m_formation(table.copy(), config), config)
        assert partial["grid_100m_id"].tolist()[:2] == result["grid_100m_id"].tolist()[:2]
        assert partial["grid_10m_id"].tolist()[:2] == result["grid_10m_id"].tolist()[:2]
        assert partial["grid_100m_has_majority_formation"].tolist() == [True, False, False, False]
        again = master.complete_100m_grid_ids(partial.copy(), config)
        pd.testing.assert_series_equal(again["grid_100m_id"], partial["grid_100m_id"])


if __name__ == "__main__":
    test_grid_ids_without_formation_or_assignment_products()
    test_master_table_minimal_build()
    test_incremental_master_merge_preserves_unaffected_rows()
    test_default_output_paths_use_master_basename()
    test_susi_10m_grid_id_uses_the_parent_inspire_nomenclature()
    test_optional_majority_keeps_every_inspire_grid_cell()
    test_10m_grid_assignment_exists_without_a_majority_product()
    test_focused_refresh_preserves_nonformation_domains()
    test_mixed_timezone_local_wall_times()
    test_formation_variant_status_is_summarised()
    print("test_master_table.py: OK")


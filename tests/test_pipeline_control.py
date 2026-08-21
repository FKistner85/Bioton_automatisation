#!/usr/bin/env python3
"""Regression tests for workflow locking, source fingerprints and run planning."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "scripts"
TOOLS_ROOT = ROOT / "tools"
for path in [SCRIPT_ROOT, TOOLS_ROOT]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pipeline_lock
import plan_pipeline_run as planner
import run_with_manifest


def test_lock_ownership() -> None:
    with tempfile.TemporaryDirectory() as raw:
        lock = Path(raw) / "pipeline.lock"
        assert pipeline_lock.acquire(lock, "run-a") == 0
        assert pipeline_lock.acquire(lock, "run-b") == 3
        assert pipeline_lock.release(lock, "run-b", force=False) == 4
        assert pipeline_lock.release(lock, "run-a", force=False) == 0
        assert not lock.exists()


def test_domain_fingerprint_change_detection() -> None:
    source = pd.DataFrame(
        {
            "id": [1, 2],
            "lat": [49.0, 50.0],
            "lng": [8.0, 9.0],
            "datetime": ["2024-05-01", "2024-05-02"],
            "localtimes": ["", ""],
            "audio": ["a", "b"],
            "photo": ["p", "q"],
            "dawn_chorus_id": ["1", "2"],
        }
    )
    previous = planner.build_fingerprints(source)
    changed = source.copy()
    changed.loc[changed["id"] == 2, "audio"] = "new-audio-url"
    current = planner.build_fingerprints(changed)
    assert planner.changed_ids(current, previous, "audio_fingerprint") == (
        set(),
        {"2"},
        set(),
    )
    assert planner.changed_ids(current, previous, "photo_fingerprint") == (
        set(),
        set(),
        set(),
    )
    timezone_changed = planner.build_fingerprints(source, timezone="UTC")
    assert planner.changed_ids(
        timezone_changed,
        previous,
        "metadata_fingerprint",
    ) == (set(), {"1", "2"}, set())
    assert planner.changed_ids(
        timezone_changed,
        previous,
        "audio_fingerprint",
    ) == (set(), set(), set())


def test_add_reason_accumulates_per_id() -> None:
    reasons: dict[str, set[str]] = {}
    planner.add_reason(reasons, {1, "2"}, "new_id")
    planner.add_reason(reasons, ["2"], "changed:audio_fingerprint")
    assert reasons == {
        "1": {"new_id"},
        "2": {"new_id", "changed:audio_fingerprint"},
    }


def test_inventory_baseline_requires_state_and_outputs() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        state = root / "state.json"
        detailed = root / "detailed.csv"
        compact = root / "compact.csv"
        config = {
            "audio_inventory": {
                "state_file": str(state),
                "detailed_log": str(detailed),
                "compact_log": str(compact),
            }
        }
        assert not planner.inventory_baseline_ready(
            config,
            "audio_inventory",
            ["detailed_log", "compact_log"],
        )
        state.write_text('{"source_files": 1}', encoding="utf-8")
        detailed.write_text("id\n1\n", encoding="utf-8")
        compact.write_text("id\n1\n", encoding="utf-8")
        assert planner.inventory_baseline_ready(
            config,
            "audio_inventory",
            ["detailed_log", "compact_log"],
        )
        state.write_text("not-json", encoding="utf-8")
        assert not planner.inventory_baseline_ready(
            config,
            "audio_inventory",
            ["detailed_log", "compact_log"],
        )


def test_inventory_reconcile_decision() -> None:
    assert not planner.inventory_reconcile_needed("add_new_ids", set(), True)
    assert planner.inventory_reconcile_needed("add_new_ids", {"42"}, True)
    assert planner.inventory_reconcile_needed("add_new_ids", set(), False)
    assert planner.inventory_reconcile_needed("from_scratch", set(), True)


def test_add_new_ids_planner_main_path() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source_path = root / "dawn.csv"
        source_path.write_text("id\n1\n", encoding="utf-8")
        plan_root = root / "plans"
        config = {
            "dawn_chorus_csv": str(source_path),
            "status_dir": str(root / "status"),
            "metadata_extraction": {
                "fingerprint_csv": str(root / "previous.csv"),
            },
            "pipeline_control": {"run_plan_dir": str(plan_root)},
            "point_lrt_assignment": {"output_csv": str(root / "points.csv")},
            "weather_inventory": {},
            "bioacoustics": {"enabled": False},
            "master_table": {},
        }
        fingerprint_columns = [
            "source_fingerprint",
            *planner.FINGERPRINT_GROUPS,
        ]
        current = pd.DataFrame(
            {
                "dawn_chorus_id": ["1"],
                **{column: [f"{column}-value"] for column in fingerprint_columns},
            }
        )
        previous = pd.DataFrame(
            columns=["dawn_chorus_id", *fingerprint_columns]
        )

        with (
            patch.object(
                planner,
                "parse_args",
                return_value=SimpleNamespace(
                    config=root / "config.json",
                    run_id="test-run",
                    mode="add_new_ids",
                ),
            ),
            patch.object(planner, "load_config", return_value=config),
            patch.object(
                planner,
                "read_source",
                return_value=pd.DataFrame({"dawn_chorus_id": ["1"]}),
            ),
            patch.object(planner, "build_fingerprints", return_value=current),
            patch.object(
                planner,
                "read_previous_fingerprints",
                return_value=previous,
            ),
            patch.object(planner, "read_master", return_value=pd.DataFrame()),
            patch.object(planner, "step20_needed", return_value=(False, [])),
            patch.object(planner, "step21_needed", return_value=(False, [])),
            patch.object(planner, "step23_needed", return_value=(False, [])),
            patch.object(planner, "step24_needed", return_value=(False, [])),
        ):
            assert planner.main() == 0

        plan = json.loads(
            (plan_root / "test-run" / "run_plan.json").read_text(
                encoding="utf-8"
            )
        )
        assert plan["mode"] == "add_new_ids"
        assert plan["id_counts"]["metadata"] == 1
        assert plan["steps"]["step_1_metadata"]["run"] is True


def test_run_plan_schema_contract() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "run_plan.schema.json").read_text(encoding="utf-8")
    )
    assert schema["$schema"].endswith("2020-12/schema")
    assert "workflow_run_id" in schema["required"]
    assert schema["properties"]["mode"]["enum"] == [
        "add_new_ids",
        "from_scratch",
    ]


def test_result_config_invalidates_global_steps() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "source.gpkg"
        lrt = root / "lrt.gpkg"
        output = root / "clean.gpkg"
        for path, content in [
            (source, b"source"),
            (lrt, b"lrt"),
            (output, b"output"),
        ]:
            path.write_bytes(content)

        step20_state = root / "step20.json"
        step20_section = {
            "source_gpkgs": [str(source)],
            "output_gpkg": str(output),
            "output_layer": "lrt",
            "target_crs": 3035,
            "eps_area": 1.0,
            "state_file": str(step20_state),
        }
        step20_state.write_text(
            json.dumps(
                {
                    "inputs": {
                        str(source): planner.file_fingerprint(source),
                    },
                    "processing": {
                        "output_gpkg": str(output.resolve()),
                        "output_layer": "lrt",
                        "target_crs": 3035,
                        "eps_area": 1.0,
                        "formation_definition": "table_2026_08_03_coastal_v2",
                    },
                }
            ),
            encoding="utf-8",
        )
        config20 = {"lrt_cleaning": step20_section}
        assert planner.step20_needed(config20) == (False, [])
        step20_section["target_crs"] = 4326
        needed20, reasons20 = planner.step20_needed(config20)
        assert needed20
        assert "changed_processing_config" in reasons20

        source100 = root / "source100.parquet"
        final10 = root / "final10.parquet"
        source100.write_bytes(b"100m")
        final10.write_bytes(b"10m")
        state24 = root / "step24.json"
        section24 = {
            "source_100m_parquet": str(source100),
            "lrt_gpkg": str(lrt),
            "output_dir": str(root / "step24"),
            "final_parquet": str(final10),
            "state_file": str(state24),
            "chunk_size_100m": 1000,
        }
        state24.write_text(
            json.dumps(
                {
                    "inputs": {
                        "source_100m_parquet": planner.file_fingerprint(source100),
                        "lrt_gpkg": planner.file_fingerprint(lrt),
                    },
                    "processing": {
                        "chunk_size_100m": 1000,
                        "output_dir": str(Path(section24["output_dir"]).resolve()),
                        "final_parquet": str(final10.resolve()),
                        "susi_matrix_schema_version": "2026-08-03-centi-percent-abck-coastal-v3",
                    },
                    "status": "complete",
                }
            ),
            encoding="utf-8",
        )
        config24 = {"susi_10m_products": section24}
        assert planner.step24_needed(config24, False) == (False, [])
        section24["chunk_size_100m"] = 500
        needed24, reasons24 = planner.step24_needed(config24, False)
        assert needed24
        assert "changed_processing_config" in reasons24


def test_full_rebuild_generation_resume() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = {
            "processed_root": str(root / "processed"),
            "pipeline_control": {
                "full_rebuild_root": str(root / "processed" / "_control" / "full"),
            },
        }
        first = planner.full_rebuild_context(config, "run-1")
        assert first["resume"] is False
        assert first["generation_id"] == "run-1"

        marker_dir = Path(first["marker_dir"])
        for step in first["required_steps"][:-1]:
            (marker_dir / f"{step}.json").write_text("{}", encoding="utf-8")
        second = planner.full_rebuild_context(config, "run-2")
        assert second["resume"] is True
        assert second["generation_id"] == "run-1"

        last_step = first["required_steps"][-1]
        plan_path = root / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "workflow_run_id": "run-2",
                    "full_rebuild": second,
                }
            ),
            encoding="utf-8",
        )
        run_with_manifest.write_full_rebuild_marker(
            str(plan_path),
            last_step,
            "step-run",
        )
        assert (marker_dir / f"{last_step}.json").is_file()
        third = planner.full_rebuild_context(config, "run-3")
        assert third["resume"] is False
        assert third["generation_id"] == "run-3"


def test_full_rebuild_step_contract_and_legacy_migration() -> None:
    assert "step_6_2_bioacoustic_embeddings" in planner.FULL_REBUILD_STEPS
    assert planner.FULL_REBUILD_STEPS.index("step_4_1_sentinel2_mirror") < (
        planner.FULL_REBUILD_STEPS.index("step_4_0_sentinel2_inventory")
    )

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        rebuild_root = root / "full"
        marker_dir = rebuild_root / "legacy-run" / "completed_steps"
        marker_dir.mkdir(parents=True)
        legacy_steps = [
            step
            for step in planner.FULL_REBUILD_STEPS
            if step != "step_6_2_bioacoustic_embeddings"
        ]
        (marker_dir / f"{legacy_steps[0]}.json").write_text("{}", encoding="utf-8")
        (rebuild_root / "current.json").write_text(
            json.dumps(
                {
                    "generation_id": "legacy-run",
                    "status": "in_progress",
                    "marker_dir": str(marker_dir),
                    "required_steps": legacy_steps,
                    "workflow_runs": ["legacy-run"],
                }
            ),
            encoding="utf-8",
        )
        config = {
            "processed_root": str(root / "processed"),
            "pipeline_control": {"full_rebuild_root": str(rebuild_root)},
        }
        migrated = planner.full_rebuild_context(config, "resume-run")
        assert migrated["resume"] is True
        assert migrated["generation_id"] == "legacy-run"
        assert migrated["required_steps"] == planner.FULL_REBUILD_STEPS
        assert legacy_steps[0] in migrated["completed_steps"]

        state = json.loads((rebuild_root / "current.json").read_text(encoding="utf-8"))
        assert state["migrated_from_required_steps"] == legacy_steps
        assert state["workflow_runs"] == ["legacy-run", "resume-run"]


if __name__ == "__main__":
    test_lock_ownership()
    test_domain_fingerprint_change_detection()
    test_add_reason_accumulates_per_id()
    test_inventory_baseline_requires_state_and_outputs()
    test_inventory_reconcile_decision()
    test_add_new_ids_planner_main_path()
    test_run_plan_schema_contract()
    test_result_config_invalidates_global_steps()
    test_full_rebuild_generation_resume()
    test_full_rebuild_step_contract_and_legacy_migration()
    print("test_pipeline_control.py: OK")

"""Independent phases must retain IDs/checkpoints and isolate master domains."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools"), str(ROOT / "scripts_local_run")]
import plan_pipeline_run as planner
import final_validation_report as validation
import Step_6_1_prepare_bioacoustic_worklist as worklist
import Step_6_2_generate_bioacoustic_embeddings as inference
import Step_7_0_update_master_table as master
import local_orchestrator


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "status_dir": str(self.root),
            "audio_inventory": {"detailed_log": str(self.root / "audio.csv")},
            "master_table": {"output_csv": str(self.root / "master.csv")},
            "pipeline_control": {"run_plan_dir": str(self.root / "plans")},
            "bioacoustics": {"enabled": True, "models": ["birdnet"], "shard_count": 4},
        }
        pd.DataFrame({"id": [1, 2]}).to_csv(self.root / "dawnchorus_metadata_clean.csv", index=False)
        pd.DataFrame({"dawn_chorus_id": [1, 2]}).to_csv(self.root / "master.csv", index=False)
        (self.root / "audio.csv").write_text("dawn_chorus_id\n1\n2\n")

    def plan(self):
        return planner.plan_bioacoustics(self.config, SimpleNamespace(
            config=self.root / "config.json", run_id="separate", mode="bioacoustics"))

    def test_bio_plan_uses_prepared_ids_without_raw_source_or_step1_deltas(self):
        plan = json.loads(self.plan().read_text())
        self.assertEqual(plan["phase"], "bioacoustics")
        self.assertEqual(plan["id_counts"]["bioacoustic"], 2)
        for step, item in plan["steps"].items():
            self.assertEqual(item["run"], step.startswith("step_6_") or step in {"step_7_0_master_table", "final_validation"})
        pd.DataFrame({"dawn_chorus_id": [1]}).to_csv(self.root / "master.csv", index=False)
        with self.assertRaisesRegex(ValueError, "finish the core"):
            self.plan()

    def test_reconciliation_replaces_deleted_ids_and_preserves_unchanged_work_keys(self):
        section = self.config["bioacoustics"]
        for key, name in {"model_registry_json": "registry.json", "worklist_csv": "work.csv",
                          "worklist_parquet": "work.parquet", "rejected_audio_csv": "rejected.csv",
                          "worklist_state_json": "work.json"}.items():
            section[key] = str(self.root / name)
        (self.root / "registry.json").write_text(json.dumps({"status": "complete", "models": [{"name": "birdnet", "model_fingerprint": "stable"}]}))
        rows = []
        for dawn_id in (1, 2, 3):
            audio = self.root / f"{dawn_id}.wav"
            audio.write_bytes(b"audio")
            rows.append({"dawn_chorus_id": str(dawn_id), "source_path": str(audio),
                         "size_bytes": 5, "mtime_ns": 123, "has_issues": False})
        inventory = pd.DataFrame(rows)
        inventory.to_csv(self.root / "audio.csv", index=False)
        previous, _ = worklist.build_worklist(inventory, self.config, registry_fingerprints={"birdnet": "stable"})
        previous.to_parquet(self.root / "work.parquet", index=False)
        args = SimpleNamespace(config=self.root / "config.json", ids_file=None, reconcile_all=True, force=False)
        with patch.object(worklist, "parse_args", return_value=args), patch.object(worklist, "load_config", return_value=self.config):
            self.assertEqual(worklist.main(), 0)
            fresh = pd.read_parquet(self.root / "work.parquet")
            self.assertEqual(set(fresh.dawn_chorus_id), {"1", "2"})
            self.assertEqual(list(fresh.work_key), list(previous[previous.dawn_chorus_id.isin(["1", "2"])].work_key))
            inventory.loc[inventory.dawn_chorus_id.eq("2"), "mtime_ns"] = 456
            inventory.to_csv(self.root / "audio.csv", index=False)
            self.assertEqual(worklist.main(), 0)
            changed = pd.read_parquet(self.root / "work.parquet")
            self.assertEqual(changed.work_key.iloc[0], fresh.work_key.iloc[0])
            self.assertNotEqual(changed.work_key.iloc[1], fresh.work_key.iloc[1])

    def test_bio_master_write_preserves_all_other_columns(self):
        original = pd.DataFrame({
            "dawn_chorus_id": ["1", "2"], "datetime_local": ["2025-03-30 03:30:00", "2025-10-26 02:30:00"],
            "grid_100m_id": ["DE_1", "DE_2"], "inside_lrt_polygon": [True, False],
            "sound_exists": [True, True], "sound_has_issues": [False, True],
            "manual_note": ["keep", "unchanged"], "mastertable_schema_version": ["old", "old"],
        })
        original.to_csv(self.root / "master.csv", index=False)
        qc = self.root / "qc.csv"
        pd.DataFrame({"dawn_chorus_id": [1, 2], "bioacoustic_status": ["validated"] * 2,
                      "bioacoustic_required_models_complete": [True] * 2}).to_csv(qc, index=False)
        self.config["bioacoustics"]["qc_compact_csv"] = str(qc)
        with patch.object(master, "append_status_events", return_value=0):
            master.write_bioacoustic_master(self.config, self.root / "master.csv", self.root / "master.parquet", self.root / "summary.json", "now")
        result = pd.read_csv(self.root / "master.csv", dtype={"dawn_chorus_id": str})
        pd.testing.assert_frame_equal(original, result[original.columns])
        self.assertEqual(result.ready_for_bioacoustic_analysis.tolist(), [True, False])

    def test_completed_inference_is_reused_and_deleted_failures_do_not_block(self):
        section = self.config["bioacoustics"]
        section["shard_count"] = 1
        for key in ("inference_state_dir", "embedding_dir", "native_prediction_dir"):
            section[key] = str(self.root / key)
        section["worklist_parquet"] = str(self.root / "work.parquet")
        pd.DataFrame({"dawn_chorus_id": ["1"], "model": ["birdnet"], "shard_index": [0],
                      "model_fingerprint": ["stable"], "work_key": ["key-1"]}).to_parquet(section["worklist_parquet"])
        state = Path(section["inference_state_dir"]) / "model=birdnet" / "shard=0000.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"model_fingerprint": "stable", "shard_count": 1,
                                    "completed_work_keys": {"1": "key-1"}, "failed_by_id": {"deleted": "error"},
                                    "batch_count": 1}))
        args = SimpleNamespace(config=self.root / "config.json", verify_shards=False, task_index=0, force=False)
        cwd = Path.cwd()
        try:
            with patch.object(inference, "parse_args", return_value=args), patch.object(inference, "load_config", return_value=self.config), patch.dict(sys.modules, {"bacpipe": None}):
                self.assertEqual(inference.main(), 0)  # Would fail if a model were imported.
                self.assertEqual(inference.verify_shards(self.config), 0)
        finally:
            os.chdir(cwd)
        saved = json.loads(state.read_text())
        self.assertEqual(saved["completed_work_keys"], {"1": "key-1"})
        self.assertEqual(saved["failed_by_id"], {})

    def test_validation_and_full_rebuild_are_phase_scoped(self):
        self.config["bioacoustics"]["qc_compact_csv"] = str(self.root / "missing_qc.csv")
        self.config["lrt_cleaning"] = {"output_gpkg": str(self.root / "missing_lrt.gpkg")}
        self.config["final_validation"] = {"require_all_general_ready": True, "require_bioacoustic_analysis": True}
        path = self.plan()
        with patch.dict(os.environ, {"BIOOTON_RUN_PLAN": str(path)}):
            checks = validation.expected_outputs(self.config)
            self.assertFalse(any("Step 2" in c["label"] for c in checks))
            self.assertTrue(any("Step 6" in c["label"] and c["required"] for c in checks))
            self.assertEqual(set(validation.master_readiness(self.config)["requirements"]), {"require_bioacoustic_analysis"})
            plan = json.loads(path.read_text())
            plan["phase"] = "core"
            path.write_text(json.dumps(plan))
            checks = validation.expected_outputs(self.config)
            self.assertFalse(any("Step 6" in c["label"] for c in checks))
            self.assertEqual(set(validation.master_readiness(self.config)["requirements"]), {"require_all_general_ready"})
        self.config["pipeline_control"]["full_rebuild_root"] = str(self.root / "rebuild")
        rebuild = planner.full_rebuild_context(self.config, "core", phase="core")
        self.assertFalse(any(s.startswith("step_6_") for s in rebuild["required_steps"]))

    def test_shell_dags_separate_core_and_bio_in_both_launch_modes(self):
        bash = str(Path("C:/Program Files/Git/bin/bash.exe")) if os.name == "nt" else shutil.which("bash")
        if not bash:
            self.skipTest("Bash unavailable")
        config = json.loads((ROOT / "config.horeka.json").read_text())
        config["slurm_log_dir"] = self.root.as_posix()
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(config))
        plan_path = self.plan()
        bio_plan = json.loads(plan_path.read_text())
        shim = self.root / "python-shim"
        shim.write_text('''#!/usr/bin/env bash
case "$1" in
  -c) [[ "$2" == 'import pandas, geopandas'* ]] && exit 0 ;;
  */plan_pipeline_run.py) printf '%s\\n' "$FIXTURE_PLAN"; exit 0 ;;
  */pipeline_lock.py|*/sentinel_credentials_preflight.py|*/run_with_manifest.py) exit 0 ;;
  */run_hostrada_raster_all.py) echo 73; exit 0 ;;
esac
exec "$REAL_PYTHON" "$@"
''', encoding="utf-8", newline="\n")
        shim.chmod(0o755)
        env = dict(os.environ, PYTHON=shim.as_posix(), REAL_PYTHON=Path(sys.executable).as_posix(),
                   CONFIG=config_path.as_posix(), FIXTURE_PLAN=plan_path.as_posix(),
                   BIOOTON_SLURM_DRY_RUN="1", BIOOTON_SUBMISSION_FILE=(self.root / "submission.json").as_posix())
        env.pop("BIOOTON_CLUSTER_PROFILE", None)
        for mode in ("add_new_ids", "bioacoustics"):
            plan = json.loads(json.dumps(bio_plan))
            if mode == "add_new_ids":
                plan["phase"] = "core"
                for step, item in plan["steps"].items():
                    item["run"] = not step.startswith("step_6_")
            plan_path.write_text(json.dumps(plan))
            for hybrid in ("0", "1"):
                with self.subTest(mode=mode, hybrid=hybrid):
                    result = subprocess.run([bash, str(ROOT / "submit_bio_o_ton_horeka.sh"), mode],
                                            env=dict(env, BIOOTON_HYBRID_CONTROLLER=hybrid), capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    jobs = result.stderr
                    if mode == "add_new_ids":
                        self.assertIn("job=bio_step1 ", jobs)
                        self.assertIn("job=bio_step54[", jobs)
                        self.assertNotIn("job=bio_step6", jobs)
                    else:
                        self.assertIn("job=bio_step60 ", jobs)
                        self.assertIn("job=bio_step62[", jobs)
                        self.assertIn("--reconcile-all", jobs)
                        for step in ("1", "2", "3", "4", "5"):
                            self.assertNotIn("job=bio_step" + step, jobs)
                    self.assertIn("job=bio_master_", jobs)
                    if hybrid == "0":
                        self.assertIn("job=bio_unlock ", jobs)

    def test_local_bio_graph_contains_only_step6(self):
        config = json.loads((ROOT / "config.horeka.json").read_text())
        config["slurm_log_dir"] = str(self.root / "logs")
        args = SimpleNamespace(repo_root=ROOT, config=self.root / "config.json",
                               core_python=Path(sys.executable), bacpipe_python=Path(sys.executable), mode="bioacoustics")
        pipeline = local_orchestrator.Pipeline(args, config, {})
        pipeline.plan = json.loads(self.plan().read_text())
        pipeline.build_steps()
        self.assertTrue(pipeline.steps)
        self.assertTrue(all(key.startswith("j6") for key in pipeline.steps), list(pipeline.steps))


if __name__ == "__main__":
    unittest.main()

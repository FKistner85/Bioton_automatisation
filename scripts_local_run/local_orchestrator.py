#!/usr/bin/env python3
"""Run the current Bio-O-Ton pipeline locally with the Slurm dependency graph."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


Runner = Callable[[], int]


@dataclass
class LocalStep:
    key: str
    label: str
    runner: Runner
    dependencies: list[str] = field(default_factory=list)
    require_success: list[str] = field(default_factory=list)
    master_ids: Path | None = None
    master_global: bool = False


class Pipeline:
    def __init__(self, args: argparse.Namespace, config: dict, settings: dict) -> None:
        self.args = args
        self.config = config
        self.settings = settings
        self.repo = args.repo_root.resolve()
        self.core = args.core_python.resolve()
        self.bacpipe = args.bacpipe_python.resolve()
        self.config_path = args.config.resolve()
        self.logical_cpus = max(1, int(settings.get("logical_cpus", 20)))
        self.max_parallel = max(1, int(settings.get("max_parallel_steps", 2)))
        self.array_workers = max(1, int(settings.get("array_workers", 2)))
        self.step_cpus = max(1, self.logical_cpus // self.max_parallel)
        self.logs = Path(config["slurm_log_dir"])
        self.logs.mkdir(parents=True, exist_ok=True)
        self.run_id = os.environ.get("BIOOTON_RUN_ID") or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + f"_local_{os.getpid()}"
        )
        self.log_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "BIOOTON_RUN_ID": self.run_id,
                "PYTHONUNBUFFERED": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        self.run_plan = Path()
        self.plan: dict = {}
        self.steps: dict[str, LocalStep] = {}
        self.outcomes: dict[str, int] = {}
        self.master_lock = threading.Lock()
        self.master_failures: list[str] = []

    def safe_label(self, label: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")

    def run_logged(
        self,
        label: str,
        command: list[str],
        *,
        cpus: int | None = None,
        suffix: str = "",
        target_python: Path | None = None,
    ) -> int:
        safe = self.safe_label(label + (f"_{suffix}" if suffix else ""))
        stdout_path = self.logs / f"{self.log_stamp}_{safe}.out"
        stderr_path = self.logs / f"{self.log_stamp}_{safe}.err"
        environment = self.environment.copy()
        environment["SLURM_CPUS_PER_TASK"] = str(max(1, cpus or self.step_cpus))
        environment["BIOOTON_STDOUT_LOG"] = str(stdout_path)
        environment["BIOOTON_STDERR_LOG"] = str(stderr_path)
        environment["BIOOTON_RUN_PLAN"] = str(self.run_plan) if self.run_plan else ""
        if target_python == self.bacpipe:
            environment["OMP_NUM_THREADS"] = str(max(1, cpus or self.step_cpus))

        print(f"START {label}{' [' + suffix + ']' if suffix else ''}")
        print(f"  stdout: {stdout_path}")
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as stderr_handle:
            result = subprocess.run(
                command,
                cwd=self.repo,
                env=environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
            )
        state = "OK" if result.returncode == 0 else f"FAILED exit={result.returncode}"
        print(f"END   {label}{' [' + suffix + ']' if suffix else ''}: {state}")
        return int(result.returncode)

    def manifest_command(
        self,
        step_name: str,
        target: str,
        extra: list[str] | None = None,
        *,
        target_python: Path | None = None,
    ) -> list[str]:
        interpreter = target_python or self.core
        return [
            str(self.core),
            str(self.repo / "tools" / "run_with_manifest.py"),
            "--config",
            str(self.config_path),
            "--step-name",
            step_name,
            "--",
            str(interpreter),
            str(self.repo / target),
            "--config",
            str(self.config_path),
            *(extra or []),
        ]

    def command_runner(
        self,
        label: str,
        step_name: str,
        target: str,
        extra: list[str] | None = None,
        *,
        target_python: Path | None = None,
        cpus: int | None = None,
    ) -> Runner:
        command = self.manifest_command(
            step_name,
            target,
            extra,
            target_python=target_python,
        )
        return lambda: self.run_logged(
            label,
            command,
            cpus=cpus,
            target_python=target_python,
        )

    def array_runner(
        self,
        label: str,
        step_name: str,
        target: str,
        task_count: int,
        argument_factory: Callable[[int], list[str]],
        *,
        target_python: Path | None = None,
        max_workers: int | None = None,
    ) -> Runner:
        workers = max(1, min(max_workers or self.array_workers, task_count))
        cpus_per_task = max(1, self.logical_cpus // workers)

        def run() -> int:
            print(f"ARRAY {label}: tasks={task_count}, parallel={workers}, CPUs/task={cpus_per_task}")

            def one(index: int) -> int:
                command = self.manifest_command(
                    step_name,
                    target,
                    argument_factory(index),
                    target_python=target_python,
                )
                return self.run_logged(
                    label,
                    command,
                    cpus=cpus_per_task,
                    suffix=f"task_{index:03d}",
                    target_python=target_python,
                )

            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(one, range(task_count)))
            failures = [index for index, code in enumerate(results) if code != 0]
            if failures:
                print(f"ARRAY FAILED {label}: {failures}", file=sys.stderr)
                return 1
            return 0

        return run

    def create_plan(self) -> None:
        command = [
            str(self.core),
            str(self.repo / "tools" / "plan_pipeline_run.py"),
            "--config",
            str(self.config_path),
            "--run-id",
            self.run_id,
            "--mode",
            self.args.mode,
        ]
        result = subprocess.run(command, cwd=self.repo, env=self.environment, text=True, capture_output=True, check=False)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            raise RuntimeError("Lokaler Run-Plan konnte nicht erzeugt werden.")
        final_line = result.stdout.strip().splitlines()[-1]
        self.run_plan = Path(final_line)
        self.plan = json.loads(self.run_plan.read_text(encoding="utf-8"))
        self.environment["BIOOTON_RUN_PLAN"] = str(self.run_plan)
        print(f"Run plan: {self.run_plan}")

    def plan_run(self, key: str) -> bool:
        return bool(self.plan.get("steps", {}).get(key, {}).get("run", False))

    def ids_file(self, key: str) -> Path:
        return Path(self.plan["id_files"][key])

    def id_count(self, path: Path) -> int:
        if not path.is_file() or path.stat().st_size == 0:
            return 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))

    def add(
        self,
        key: str,
        label: str,
        runner: Runner,
        dependencies: list[str] | None = None,
        require_success: list[str] | None = None,
        master_ids: Path | None = None,
        master_global: bool = False,
    ) -> None:
        self.steps[key] = LocalStep(
            key=key,
            label=label,
            runner=runner,
            dependencies=[item for item in dependencies or [] if item in self.steps],
            require_success=[item for item in require_success or [] if item in self.steps],
            master_ids=master_ids,
            master_global=master_global,
        )

    def build_steps(self) -> None:
        force = ["--force"] if self.args.mode == "from_scratch" else []
        metadata_ids = self.ids_file("metadata")
        point_ids = self.ids_file("point_assignment")
        audio_ids = self.ids_file("audio")
        photo_ids = self.ids_file("photo")
        weather_ids = self.ids_file("weather")
        bio_ids = self.ids_file("bioacoustic")
        sentinel_ids = self.ids_file("sentinel")

        if self.plan_run("step_1_metadata"):
            self.add("j1", "step_1_metadata", self.command_runner(
                "step_1_metadata", "step_1_metadata", "scripts/Step_1_metadata_extraction.py",
                [*force, "--ids-file", str(metadata_ids)], cpus=2,
            ), master_ids=metadata_ids)
        if self.plan_run("step_2_0_lrt_cleaning"):
            self.add("j20", "step_2_0", self.command_runner(
                "step_2_0", "step_2_0_lrt_cleaning", "scripts/Step_2_0_clean_lrts.py", force,
            ))
        if self.plan_run("step_2_1_100m_formation"):
            self.add("j21", "step_2_1", self.command_runner(
                "step_2_1", "step_2_1_100m_formation", "scripts/Step_2_1_merge_lrts_and_grid.py", force,
            ), ["j20"])
        if self.plan_run("step_2_2_point_assignment"):
            self.add("j22", "step_2_2", self.command_runner(
                "step_2_2", "step_2_2_point_assignment", "scripts/Step_2_2_assign_points_to_lrt_grid.py",
                [*force, "--ids-file", str(point_ids)], cpus=2,
            ), ["j1", "j21"], master_ids=point_ids)
        if self.plan_run("step_2_3_grid_aggregation"):
            self.add("j23", "step_2_3", self.command_runner(
                "step_2_3", "step_2_3_grid_aggregation", "scripts/Step_2_3_generate_remaining_grid_products.py", force,
            ), ["j21"])
        if self.plan_run("step_2_4_10m_formation"):
            self.add("j24", "step_2_4", self.command_runner(
                "step_2_4", "step_2_4_10m_formation", "scripts/Step_2_4_generate_10m_formation_status_products.py", force,
            ), ["j21"], master_global=True)

        self.add("j3pre", "step_3_preflight", self.command_runner(
            "step_3_preflight", "step_3_path_preflight", "tools/step3_path_preflight.py", cpus=1,
        ))
        if self.plan_run("step_3_0_audio_inventory"):
            self.add("j30a", "step_3_0a", self.command_runner(
                "step_3_0a", "step_3_0_audio_inventory", "scripts/Step_3_0_a_audio_inventory.py", force,
            ), ["j3pre"])
        if self.plan_run("step_3_0_photo_inventory"):
            self.add("j30b", "step_3_0b", self.command_runner(
                "step_3_0b", "step_3_0_photo_inventory", "scripts/Step_3_0_b_photo_inventory.py", force,
            ), ["j3pre"])
        if self.plan_run("step_3_1_audio_download"):
            self.add("j31a", "step_3_1a", self.command_runner(
                "step_3_1a", "step_3_1_audio_download", "scripts/Step_3_1_a_audio_download.py",
                [*force, "--ids-file", str(audio_ids)],
            ), ["j30a"])
        if self.plan_run("step_3_0_audio_inventory_post"):
            self.add("j30apost", "step_3_0a_post", self.command_runner(
                "step_3_0a_post", "step_3_0_audio_inventory_post", "scripts/Step_3_0_a_audio_inventory.py",
            ), ["j31a"], master_ids=audio_ids)
        if self.plan_run("step_3_1_photo_download"):
            self.add("j31b", "step_3_1b", self.command_runner(
                "step_3_1b", "step_3_1_photo_download", "scripts/Step_3_1_b_photo_download.py",
                [*force, "--ids-file", str(photo_ids)],
            ), ["j30b"], master_ids=photo_ids)

        if self.plan_run("step_4_1_sentinel2_mirror"):
            self.add("j41", "step_4_1", self.command_runner(
                "step_4_1", "step_4_1_sentinel2_mirror", "scripts/Step_4_1_Sentinel2_download.py", force, cpus=2,
            ), ["j1"])
        if self.plan_run("step_4_0_sentinel2_inventory"):
            self.add("j40", "step_4_0", self.command_runner(
                "step_4_0", "step_4_0_sentinel2_inventory", "scripts/Step_4_0_Sentinel2_inventory.py", force,
            ), ["j41"], master_ids=sentinel_ids)

        if self.plan_run("step_5_1_weather_inventory"):
            self.add("j51pre", "step_5_1_pre", self.command_runner(
                "step_5_1_pre", "step_5_1_weather_inventory", "scripts/Step_5_1_Weather_inventory.py", force,
            ), ["j1"])
        if self.plan_run("step_5_2_weather_download"):
            count = self.id_count(weather_ids)
            shards = max(1, min(int(self.config["weather_download"].get("slurm_shard_count", 8)), (count + 4999) // 5000 or 1))
            self.add("j52", "step_5_2", self.array_runner(
                "step_5_2", "step_5_2_weather_download_array_task", "scripts/Step_5_2_download_weather_data.py",
                shards,
                lambda index: [*force, "--ids-file", str(weather_ids), "--task-index", str(index), "--task-count", str(shards)],
            ), ["j51pre"])
            self.add("j52verify", "step_5_2_verify", self.command_runner(
                "step_5_2_verify", "step_5_2_weather_download", "scripts/Step_5_2_download_weather_data.py",
                ["--verify-shards", "--ids-file", str(weather_ids)], cpus=1,
            ), ["j52"])
            self.add("j51post", "step_5_1_post", self.command_runner(
                "step_5_1_post", "step_5_1_weather_inventory_post", "scripts/Step_5_1_Weather_inventory.py",
            ), ["j52verify"], master_ids=weather_ids)

        if self.plan_run("step_5_3_hostrada_monthly"):
            self.add("j53", "step_5_3", self.command_runner(
                "step_5_3", "step_5_3_hostrada_monthly", "scripts/Step_5_3_download_hostrada_monthly.py",
            ))
        if self.plan_run("step_5_4_hostrada_rasters"):
            count_command = [str(self.core), str(self.repo / "tools/run_hostrada_raster_all.py"), "--config", str(self.config_path), "--task-count"]
            count_result = subprocess.run(count_command, cwd=self.repo, text=True, capture_output=True, check=False)
            if count_result.returncode != 0 or not count_result.stdout.strip().splitlines()[-1].isdigit():
                raise RuntimeError(f"Ungueltige Step-5.4-Taskzahl: {count_result.stderr}")
            task_count = int(count_result.stdout.strip().splitlines()[-1])
            self.add("j54", "step_5_4", self.array_runner(
                "step_5_4", "step_5_4_hostrada_raster_array_task", "tools/run_hostrada_raster_all.py",
                task_count, lambda index: ["--task-index", str(index), *force],
            ), ["j53"])
            self.add("j54verify", "step_5_4_verify", self.command_runner(
                "step_5_4_verify", "step_5_4_hostrada_rasters", "tools/run_hostrada_raster_all.py", ["--verify-array"], cpus=1,
            ), ["j54"])
        if self.plan_run("step_5_5_hostrada_raster_qc"):
            self.add("j55", "step_5_5", self.command_runner(
                "step_5_5", "step_5_5_hostrada_raster_qc", "scripts/Step_5_5_check_hostrada_raster_products.py",
            ), ["j54verify"], master_global=True)

        if self.plan_run("step_6_0_bioacoustic_model_preflight"):
            instantiate = self.config["bioacoustics"].get("instantiate_models_in_preflight", True)
            self.add("j60", "step_6_0", self.command_runner(
                "step_6_0", "step_6_0_bioacoustic_model_preflight", "scripts/Step_6_0_bioacoustic_model_preflight.py",
                ["--instantiate-models"] if instantiate else [], target_python=self.bacpipe,
            ))
        if self.plan_run("step_6_1_bioacoustic_worklist"):
            required = [item for item in ["j30apost", "j1", "j60"] if item in self.steps]
            self.add("j61", "step_6_1", self.command_runner(
                "step_6_1", "step_6_1_bioacoustic_worklist", "scripts/Step_6_1_prepare_bioacoustic_worklist.py",
                [*force, "--ids-file", str(bio_ids)], cpus=2,
            ), required, required)
        if self.plan_run("step_6_2_bioacoustic_embeddings"):
            section = self.config["bioacoustics"]
            task_count = len(section["models"]) * int(section.get("shard_count", 16))
            workers = max(1, int(section.get("max_concurrent_tasks", 1)))
            self.add("j62", "step_6_2", self.array_runner(
                "step_6_2", "step_6_2_bioacoustic_embeddings_array_task", "scripts/Step_6_2_generate_bioacoustic_embeddings.py",
                task_count, lambda index: [*force, "--task-index", str(index)],
                target_python=self.bacpipe, max_workers=workers,
            ), ["j61"], ["j61"])
            self.add("j62verify", "step_6_2_verify", self.command_runner(
                "step_6_2_verify", "step_6_2_bioacoustic_embeddings",
                "scripts/Step_6_2_generate_bioacoustic_embeddings.py",
                ["--verify-shards"], cpus=2,
            ), ["j62"])
        if self.plan_run("step_6_3_species_predictions"):
            self.add("j63", "step_6_3", self.command_runner(
                "step_6_3", "step_6_3_species_predictions", "scripts/Step_6_3_normalise_species_predictions.py",
            ), ["j62verify"])
        if self.plan_run("step_6_4_germany_taxonomy_filter"):
            self.add("j64", "step_6_4", self.command_runner(
                "step_6_4", "step_6_4_germany_taxonomy_filter", "scripts/Step_6_4_filter_germany_taxonomy.py",
            ), ["j63"], ["j63"])
        if self.plan_run("step_6_5_bioacoustic_aggregation"):
            self.add("j65", "step_6_5", self.command_runner(
                "step_6_5", "step_6_5_bioacoustic_aggregation", "scripts/Step_6_5_aggregate_bioacoustic_results.py",
            ), ["j64"], ["j64"])
        if self.plan_run("step_6_6_bioacoustic_qc"):
            self.add("j66", "step_6_6", self.command_runner(
                "step_6_6", "step_6_6_bioacoustic_qc", "scripts/Step_6_6_bioacoustic_quality_control.py",
            ), ["j65"], master_ids=bio_ids)

    def update_master(self, stage: str, ids_file: Path | None = None) -> int:
        extra = ["--ids-file", str(ids_file)] if ids_file else []
        with self.master_lock:
            code = self.run_logged(
                f"master_{stage}",
                self.manifest_command(
                    f"step_7_0_master_{stage}",
                    "scripts/Step_7_0_update_master_table.py",
                    extra,
                ),
                cpus=2,
            )
        if code != 0:
            self.master_failures.append(stage)
        return code

    def run_graph(self) -> int:
        pending = dict(self.steps)
        running: dict[Future[int], LocalStep] = {}
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            while pending or running:
                made_progress = False
                for key, step in list(pending.items()):
                    if len(running) >= self.max_parallel:
                        break
                    if not all(dep in self.outcomes for dep in step.dependencies):
                        continue
                    failed_required = [dep for dep in step.require_success if self.outcomes.get(dep, 1) != 0]
                    if failed_required:
                        print(f"SKIP  {step.label}: erforderliche Abhaengigkeit fehlgeschlagen: {failed_required}")
                        self.outcomes[key] = 99
                        del pending[key]
                        made_progress = True
                        continue
                    running[executor.submit(step.runner)] = step
                    del pending[key]
                    made_progress = True

                if running:
                    done, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in done:
                        step = running.pop(future)
                        try:
                            code = int(future.result())
                        except Exception as exc:
                            print(f"FAILED {step.label}: {exc}", file=sys.stderr)
                            code = 1
                        self.outcomes[step.key] = code
                        if step.master_ids is not None:
                            self.update_master(step.label, step.master_ids)
                        elif step.master_global:
                            self.update_master(step.label)
                    made_progress = True

                if not made_progress and pending:
                    unresolved = {key: step.dependencies for key, step in pending.items()}
                    raise RuntimeError(f"Nicht aufloesbare lokale Abhaengigkeiten: {unresolved}")

        final_master = self.update_master("final")
        validation = self.run_logged(
            "final_validation",
            self.manifest_command("final_validation", "tools/final_validation_report.py"),
            cpus=1,
        )
        visual = self.run_logged(
            "visual_reports",
            self.manifest_command("step_9_visual_reports", "tools/generate_pipeline_visual_reports.py"),
            cpus=1,
        )
        failed_steps = [key for key, code in self.outcomes.items() if code not in (0, 99)]
        if failed_steps or self.master_failures or final_master != 0 or validation != 0 or visual != 0:
            print(f"Fehlgeschlagene Steps: {failed_steps}", file=sys.stderr)
            print(f"Fehlgeschlagene Master-Updates: {self.master_failures}", file=sys.stderr)
            return 1
        return 0


def run_lock(core: Path, repo: Path, config: Path, command: str, run_id: str, force: bool = False) -> int:
    args = [
        str(core),
        str(repo / "tools" / "pipeline_lock.py"),
        "--config",
        str(config),
        command,
    ]
    if force:
        args.append("--force")
    else:
        args.extend(["--run-id", run_id])
    return subprocess.run(args, cwd=repo, check=False).returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["add_new_ids", "from_scratch", "functionality_test"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--core-python", type=Path, required=True)
    parser.add_argument("--bacpipe-python", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    settings = json.loads(args.settings.read_text(encoding="utf-8-sig"))
    pipeline = Pipeline(args, config, settings)

    if args.mode == "functionality_test":
        return pipeline.run_logged(
            "functionality_test",
            [str(args.core_python), str(args.repo_root / "tools/functionality_test.py"), "--config", str(args.config)],
            cpus=2,
        )

    os.environ["BIOOTON_RUN_ID"] = pipeline.run_id
    if run_lock(args.core_python, args.repo_root, args.config, "acquire", pipeline.run_id) != 0:
        return 3
    try:
        pipeline.create_plan()
        pipeline.build_steps()
        print(f"Lokaler Workflow: {pipeline.run_id}")
        print(f"Geplante Steps : {len(pipeline.steps)}")
        print(f"Parallel Steps : {pipeline.max_parallel}")
        print(f"Log-Verzeichnis: {pipeline.logs}")
        return pipeline.run_graph()
    except KeyboardInterrupt:
        print("Lokaler Lauf wurde unterbrochen. Checkpoints bleiben erhalten.", file=sys.stderr)
        return 130
    finally:
        run_lock(args.core_python, args.repo_root, args.config, "release", pipeline.run_id)


if __name__ == "__main__":
    raise SystemExit(main())

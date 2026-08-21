#!/usr/bin/env python3
"""Persistent tmux-side controller for the hybrid HoreKa workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_json, load_config, processed_root_from_config


ACTIVE_STATES = {
    "CONFIGURING",
    "COMPLETING",
    "PENDING",
    "RUNNING",
    "RESIZING",
    "SUSPENDED",
}
SUCCESS_STATES = {"COMPLETED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "functionality_test",
            "add_new_ids",
            "from_scratch",
            "formation_compare",
        ],
        required=True,
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="Run controller-side checks but replace every sbatch call with a print.",
    )
    return parser.parse_args()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def running_python() -> Path:
    """Return the invoked interpreter without resolving a venv symlink.

    On HoreKa, ``.venv/bin/python`` may be a symlink to the system Python.
    Resolving it would discard the virtual environment's site-packages before
    forwarding the interpreter to submitted jobs.
    """
    return Path(sys.executable)


def normalise_state(value: str) -> str:
    return value.strip().split("+", 1)[0].split(" ", 1)[0].upper()


def command_output(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout.strip()


def slurm_job_state(job_id: str) -> str:
    queued = command_output(["squeue", "-h", "-j", job_id, "-o", "%T"])
    if queued:
        return normalise_state(queued.splitlines()[0])
    accounting = command_output(
        ["sacct", "-n", "-X", "-j", job_id, "--format=State", "--parsable2"]
    )
    states = [normalise_state(line) for line in accounting.splitlines() if line.strip()]
    return states[0] if states else "UNKNOWN"


def wait_for_jobs(
    job_ids: list[str],
    poll_seconds: int,
    update_state: Any,
) -> dict[str, str]:
    remaining = set(job_ids)
    final: dict[str, str] = {}
    unknown_counts = {job_id: 0 for job_id in job_ids}
    while remaining:
        snapshot: dict[str, str] = {}
        for job_id in sorted(remaining, key=int):
            state = slurm_job_state(job_id)
            snapshot[job_id] = state
            if state == "UNKNOWN":
                unknown_counts[job_id] += 1
                if unknown_counts[job_id] < 5:
                    continue
            if state not in ACTIVE_STATES:
                final[job_id] = state
        for job_id in final:
            remaining.discard(job_id)
        update_state("waiting_for_slurm", slurm=snapshot, completed=final)
        if remaining:
            print(
                f"Waiting for {len(remaining)} Slurm job(s): "
                + ", ".join(f"{job}={snapshot.get(job, 'UNKNOWN')}" for job in sorted(remaining, key=int)),
                flush=True,
            )
            time.sleep(max(5, poll_seconds))
    return final


def run_local_step(
    python: Path,
    root: Path,
    config: Path,
    run_id: str,
    run_plan: str,
    step_name: str,
    target: str,
) -> int:
    environment = os.environ.copy()
    environment.update(
        {
            "BIOOTON_RUN_ID": run_id,
            "BIOOTON_RUN_PLAN": run_plan,
            "SLURM_CPUS_PER_TASK": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    command = [
        str(python),
        str(root / "tools" / "run_with_manifest.py"),
        "--config",
        str(config),
        "--step-name",
        step_name,
        "--",
        str(python),
        str(root / target),
        "--config",
        str(config),
    ]
    print(f"LOCAL {step_name}: {' '.join(command[7:])}", flush=True)
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path = args.config.resolve()
    config = load_config(config_path)
    python = running_python()
    control_root = processed_root_from_config(config) / "step_0_control" / "controllers"
    controller_id = f"{utc_stamp()}_{os.environ.get('USER', 'user')}_{os.getpid()}"
    state_path = control_root / f"{controller_id}.json"
    submission_path = control_root / f"{controller_id}_submission.json"
    state: dict[str, Any] = {
        "schema_version": "2026-08-21-horeka-controller-v1",
        "controller_id": controller_id,
        "tmux_session": os.environ.get("BIOOTON_TMUX_SESSION", ""),
        "host": os.environ.get("HOSTNAME", ""),
        "pid": os.getpid(),
        "mode": args.mode,
        "local_test": args.local_test,
        "config": str(config_path),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "starting",
    }

    def update(status: str, **extra: Any) -> None:
        state.update(extra)
        state["status"] = status
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(state_path, state)

    update("starting")
    if args.mode == "functionality_test":
        result = run_local_step(
            python,
            root,
            config_path,
            controller_id,
            "",
            "functionality_test",
            "tools/functionality_test.py",
        )
        update("complete" if result == 0 else "failed", returncode=result)
        return result

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHON": str(python),
            "CONFIG": str(config_path),
            "BIOOTON_HYBRID_CONTROLLER": "1",
            "BIOOTON_DISABLE_BATCH_MASTER_UPDATES": "1",
            "BIOOTON_SUBMISSION_FILE": str(submission_path),
            "BIOOTON_SLURM_DRY_RUN": "1" if args.local_test else "0",
        }
    )
    update("submitting")
    submitted = subprocess.run(
        ["bash", str(root / "submit_bio_o_ton_horeka.sh"), args.mode],
        cwd=root,
        env=environment,
        check=False,
    )
    if submitted.returncode != 0 or not submission_path.is_file():
        update("submission_failed", returncode=submitted.returncode)
        return submitted.returncode or 1

    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    update("submitted", submission=submission)
    job_ids = [str(value) for value in submission.get("job_ids", []) if str(value).isdigit()]
    interrupted = False
    safe_to_release = not job_ids
    try:
        if args.local_test:
            print(
                "LOCAL-TEST complete: no Slurm job was submitted. "
                "Final validation and visual reports were not executed because "
                "their planned Slurm inputs were intentionally not produced.",
                flush=True,
            )
            update(
                "local_test_complete",
                planned_submission=submission,
                skipped_local_post_steps=[
                    "final_validation",
                    "step_9_visual_reports",
                ],
            )
            return 0
        final_states = wait_for_jobs(job_ids, args.poll_seconds, update) if job_ids else {}
        safe_to_release = True
        failed_jobs = {
            job_id: value
            for job_id, value in final_states.items()
            if value not in SUCCESS_STATES
        }
        if args.mode == "formation_compare":
            result = 1 if failed_jobs else 0
            update(
                "complete" if result == 0 else "completed_with_failures",
                slurm_final=final_states,
                failed_jobs=failed_jobs,
            )
            return result
        run_id = str(submission.get("run_id", controller_id))
        run_plan = str(submission.get("run_plan", ""))
        validation_result = run_local_step(
            python,
            root,
            config_path,
            run_id,
            run_plan,
            "final_validation",
            "tools/final_validation_report.py",
        )
        visual_result = run_local_step(
            python,
            root,
            config_path,
            run_id,
            run_plan,
            "step_9_visual_reports",
            "tools/generate_pipeline_visual_reports.py",
        )
        result = 1 if failed_jobs or validation_result or visual_result else 0
        update(
            "complete" if result == 0 else "completed_with_failures",
            slurm_final=final_states,
            failed_jobs=failed_jobs,
            validation_returncode=validation_result,
            visual_returncode=visual_result,
        )
        return result
    except KeyboardInterrupt:
        interrupted = True
        update("interrupted_lock_retained")
        print("Controller interrupted; Slurm jobs and pipeline lock were left untouched.", file=sys.stderr)
        return 130
    finally:
        if submission.get("lock_active") and not interrupted and safe_to_release:
            run_id = str(submission.get("run_id", ""))
            released = subprocess.run(
                [
                    str(python),
                    str(root / "tools" / "pipeline_lock.py"),
                    "--config",
                    str(config_path),
                    "release",
                    "--run-id",
                    run_id,
                ],
                cwd=root,
                check=False,
            )
            state["lock_release_returncode"] = released.returncode
            atomic_write_json(state_path, state)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run any pipeline command and write a central step manifest.

This is the orchestration-level manifest layer. Individual steps can still write
their own richer manifests and batch status files; this wrapper guarantees that
every Slurm-submitted command has at least one consistent run record.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_json, finish_step_manifest, load_config, start_step_manifest, utc_now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command with a pipeline manifest.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--step-name", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def clean_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def write_full_rebuild_marker(
    run_plan_path: str,
    step_name: str,
    step_run_id: str,
) -> None:
    if not run_plan_path or not Path(run_plan_path).is_file():
        return
    try:
        plan = json.loads(Path(run_plan_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    context = plan.get("full_rebuild", {})
    marker_dir = context.get("marker_dir")
    if not marker_dir or step_name not in context.get("required_steps", []):
        return
    atomic_write_json(
        Path(marker_dir) / f"{step_name}.json",
        {
            "schema_version": "2026-07-23-full-rebuild-step-v1",
            "generation_id": context.get("generation_id", ""),
            "workflow_run_id": plan.get("workflow_run_id", ""),
            "step_name": step_name,
            "step_run_id": step_run_id,
            "completed_utc": utc_now_iso(),
        },
    )


def main() -> int:
    args = parse_args()
    command = clean_command(args.command)
    if not command:
        print("ERROR: no command supplied to run_with_manifest.py", file=sys.stderr)
        return 2

    config = load_config(args.config)
    manifest_inputs: list[Path] = [args.config]
    for item in command:
        candidate = Path(item)
        if candidate.is_file() and candidate not in manifest_inputs:
            manifest_inputs.append(candidate)
    run_plan = os.environ.get("BIOOTON_RUN_PLAN", "").strip()
    if run_plan and Path(run_plan).is_file():
        manifest_inputs.append(Path(run_plan))
    force = bool(args.force or "--force" in command)
    manifest_path, manifest = start_step_manifest(
        config,
        args.step_name,
        config_path=args.config,
        inputs=manifest_inputs,
        outputs=[],
        parameters={
            "wrapped_command": command,
            "wrapper": "tools/run_with_manifest.py",
            "workflow_run_plan": run_plan,
        },
        force=force,
    )
    started = time.monotonic()
    completed = subprocess.run(command, text=True)
    elapsed_seconds = time.monotonic() - started
    status = "complete" if completed.returncode == 0 else "failed"
    finish_step_manifest(
        manifest_path,
        manifest,
        status,
        result={
            "returncode": completed.returncode,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "wrapped_command": command,
        },
        error="" if completed.returncode == 0 else f"returncode={completed.returncode}",
    )
    if completed.returncode == 0:
        write_full_rebuild_marker(
            run_plan,
            args.step_name,
            str(manifest.get("step_run_id", manifest.get("run_id", ""))),
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

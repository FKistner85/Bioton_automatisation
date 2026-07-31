#!/usr/bin/env python3
"""Acquire, inspect or release the shared Bio-O-Ton pipeline run lock."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_json, load_config, processed_root_from_config


def lock_dir(config: dict) -> Path:
    configured = config.get("pipeline_control", {}).get("lock_dir")
    return Path(configured) if configured else processed_root_from_config(config) / "step_0_control" / "pipeline.lock"


def read_owner(path: Path) -> dict:
    owner_path = path / "owner.json"
    if not owner_path.is_file():
        return {}
    try:
        return json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def acquire(path: Path, run_id: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError:
        owner = read_owner(path)
        print(
            "ERROR: Another Bio-O-Ton pipeline run owns the lock.\n"
            f"Lock: {path}\n"
            f"Owner: {json.dumps(owner, indent=2)}\n"
            "Inspect active jobs before using the explicit force-release command.",
            file=sys.stderr,
        )
        return 3
    atomic_write_json(
        path / "owner.json",
        {
            "workflow_run_id": run_id,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME", ""),
        },
    )
    print(f"Pipeline lock acquired: {path}")
    return 0


def release(path: Path, run_id: str, force: bool) -> int:
    if not path.exists():
        print(f"Pipeline lock already absent: {path}")
        return 0
    owner = read_owner(path)
    owner_run = str(owner.get("workflow_run_id", ""))
    if not force and owner_run and owner_run != run_id:
        print(
            f"ERROR: Lock belongs to workflow_run_id={owner_run}, not {run_id}.",
            file=sys.stderr,
        )
        return 4
    shutil.rmtree(path)
    print(f"Pipeline lock released: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", choices=["acquire", "status", "release"])
    parser.add_argument("--run-id", default=os.environ.get("BIOOTON_RUN_ID", ""))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    path = lock_dir(config)
    if args.command == "status":
        print(json.dumps({"path": str(path), "exists": path.exists(), "owner": read_owner(path)}, indent=2))
        return 0
    if not args.run_id and not args.force:
        print("ERROR: --run-id is required.", file=sys.stderr)
        return 2
    if args.command == "acquire":
        return acquire(path, args.run_id)
    return release(path, args.run_id, args.force)


if __name__ == "__main__":
    raise SystemExit(main())

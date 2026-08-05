#!/usr/bin/env python3
"""Move large Step-2 intermediates from the local workspace to mounted LSDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


INTERMEDIATE_DIRS = ("grid10m_chunks", "ix_chunks")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


def sha256(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def verified_equal(source: Path, target: Path, verification: str) -> bool:
    if not target.is_file() or source.stat().st_size != target.stat().st_size:
        return False
    return verification == "size" or sha256(source) == sha256(target)


def copy_verified(source: Path, target: Path, verification: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if verification == "sha256" and verified_equal(source, target, verification):
        return "remote_existing"
    temporary = target.with_name(f".{target.name}.offload-{os.getpid()}.part")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temporary)
        if not verified_equal(source, temporary, verification):
            raise OSError(f"Verification failed after LSDF copy: {source} -> {target}")
        os.replace(temporary, target)
        if not verified_equal(source, target, verification):
            raise OSError(f"Verification failed after LSDF publish: {source} -> {target}")
    finally:
        temporary.unlink(missing_ok=True)
    return "uploaded"


def variant_complete(step24: Path) -> bool:
    state_path = step24 / "state.json"
    if not state_path.is_file():
        return False
    try:
        state = load_json(state_path)
    except (OSError, ValueError):
        return False
    if state.get("status") != "complete":
        return False
    configured_output = state.get("processing", {}).get("final_parquet")
    if configured_output and Path(configured_output).is_file():
        return True
    return any(step24.glob("Formation_Status_10m_Grid_withLRTCode*.parquet"))


def candidate_directories(local_root: Path, include_completed_parquet: bool) -> list[Path]:
    candidates: list[Path] = []
    for step24 in sorted(local_root.glob("*/step_2_4_susi_10m")):
        candidates.extend(step24 / name for name in INTERMEDIATE_DIRS)
        if include_completed_parquet and variant_complete(step24):
            candidates.append(step24 / "parquet_10")
    return [path for path in candidates if path.is_dir()]


def append_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def offload(
    settings: dict,
    *,
    verification: str = "size",
    include_completed_parquet: bool = True,
    dry_run: bool = False,
    allow_active_lock: bool = False,
) -> dict:
    workspace = Path(settings["workspace_dir"]).expanduser().resolve()
    local_outputs = workspace / "outputs"
    local_root = local_outputs / "step_2_variants"
    remote_outputs = (
        mount_root(settings)
        / Path(settings.get("horeka_outputs_relative", "Data_automatisation_skripts/outputs"))
    )
    remote_root = remote_outputs / "step_2_variants"
    lock = local_outputs / "step_0_control" / "pipeline.lock"
    if lock.exists() and not allow_active_lock:
        raise RuntimeError(
            f"Pipeline lock exists: {lock}. Stop the run or pass --allow-active-lock only "
            "from the owning orchestrator."
        )
    if not local_root.is_dir():
        return {"status": "nothing_to_do", "files": 0, "bytes": 0}
    mounted = mount_root(settings)
    if not (mounted / "PointData").is_dir():
        raise FileNotFoundError(f"LSDF mount is not readable: {mounted}")

    log_path = local_outputs / "step_0_local_logs" / "step2_storage_offload.jsonl"
    files = 0
    bytes_freed = 0
    uploaded = 0
    reused = 0
    stale_parts = 0
    for directory in candidate_directories(local_root, include_completed_parquet):
        relative_dir = directory.relative_to(local_outputs)
        for source in sorted(directory.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(local_outputs)
            if source.name.endswith(".part") or ".offload-" in source.name:
                if not dry_run:
                    source.unlink(missing_ok=True)
                stale_parts += 1
                continue
            size = source.stat().st_size
            target = remote_outputs / relative
            action = "dry_run"
            if not dry_run:
                action = copy_verified(source, target, verification)
                source.unlink()
                if source.exists():
                    raise OSError(f"Local file could not be removed: {source}")
            files += 1
            bytes_freed += size
            uploaded += int(action == "uploaded")
            reused += int(action == "remote_existing")
            append_log(
                log_path,
                {
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "source": str(source),
                    "target": str(target),
                    "bytes": size,
                    "verification": verification,
                    "action": action,
                },
            )
        if not dry_run:
            try:
                directory.rmdir()
            except OSError:
                pass

    result = {
        "status": "dry_run" if dry_run else "complete",
        "files": files,
        "uploaded": uploaded,
        "remote_existing": reused,
        "stale_parts_removed": stale_parts,
        "bytes": bytes_freed,
        "gib": round(bytes_freed / (1024 ** 3), 2),
        "remote_root": str(remote_root),
        "log": str(log_path),
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--verification", choices=("size", "sha256"), default="size")
    parser.add_argument("--no-completed-parquet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-active-lock", action="store_true")
    args = parser.parse_args()
    offload(
        load_json(args.settings),
        verification=args.verification,
        include_completed_parquet=not args.no_completed_parquet,
        dry_run=args.dry_run,
        allow_active_lock=args.allow_active_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

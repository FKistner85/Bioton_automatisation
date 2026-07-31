#!/usr/bin/env python3
"""Step 6_0: Validate Bacpipe, model configuration and runtime capabilities."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from common import atomic_write_json, load_config, utc_now_iso
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    bio_config,
    configured_models,
    configure_bacpipe_runtime,
    model_fingerprint,
    output_path,
)

CHECKPOINT_TREES: dict[str, tuple[str, ...]] = {
    "birdnet": ("birdnet",),
    "insect66": ("insect66",),
    "naturebeats": ("naturebeats", "beats"),
}
REPAIRABLE_CHECKPOINT_ERRORS = (
    "file not found",
    "pytorchstreamreader",
    "failed finding central directory",
    "pickle data was truncated",
    "invalid load key",
    "unexpected eof",
    "failed reading zip archive",
)


def checkpoint_error_is_repairable(exc: Exception | str) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in REPAIRABLE_CHECKPOINT_ERRORS)


def quarantine_checkpoint_trees(
    checkpoint_dir: Path,
    model_name: str,
) -> list[str]:
    """Move suspect model trees aside so Bacpipe must download them again."""
    tree_names = CHECKPOINT_TREES.get(model_name, (model_name,))
    stamp = utc_now_iso().replace(":", "").replace("+", "_")
    quarantine_root = (
        checkpoint_dir
        / "_quarantine"
        / f"{stamp}_{model_name}"
    )
    moved: list[str] = []
    for tree_name in tree_names:
        source = checkpoint_dir / tree_name
        if not source.exists():
            continue
        destination = quarantine_root / tree_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append(str(destination))
    return moved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument(
        "--instantiate-models",
        action="store_true",
        help="Instantiate every configured Bacpipe model to stage/check checkpoints.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Bacpipe 1.3.1 resolves several checkpoints relative to the working
    # directory. Make direct execution behave like the Slurm wrapper.
    os.chdir(args.config.resolve().parent)
    config = load_config(args.config)
    section = bio_config(config)
    models = configured_models(config)
    registry_path = output_path(config, "model_registry_json")
    issues: list[str] = []
    warnings: list[str] = []
    bacpipe_version = ""
    torch_info: dict[str, Any] = {}
    checkpoint_staging: dict[str, Any] = {
        "requested": [],
        "completed": [],
        "failed": {},
        "repairs": {},
    }

    try:
        import bacpipe

        bacpipe_version = importlib.metadata.version("bacpipe")
    except Exception as exc:
        bacpipe = None
        issues.append(f"bacpipe_import_failed:{type(exc).__name__}:{exc}")

    expected_version = str(section.get("bacpipe_version", "")).strip()
    if expected_version and bacpipe_version and bacpipe_version != expected_version:
        issues.append(
            f"bacpipe_version_mismatch:expected={expected_version}:actual={bacpipe_version}"
        )

    try:
        import torch

        torch_info = {
            "version": str(torch.__version__),
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()),
            "cuda_version": str(torch.version.cuda or ""),
        }
        if str(section.get("device", "cuda")).lower() == "cuda" and not torch.cuda.is_available():
            warnings.append("cuda_not_available_in_preflight_process")
    except Exception as exc:
        issues.append(f"torch_import_failed:{type(exc).__name__}:{exc}")

    instantiated: dict[str, str] = {}
    if args.instantiate_models and bacpipe is not None:
        configure_bacpipe_runtime(bacpipe, section)
        checkpoint_dir = Path(
            str(
                section.get(
                    "model_checkpoint_dir",
                    Path.cwd() / "bacpipe" / "model_checkpoints",
                )
            )
        ).expanduser()
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_staging.update(
            {
                "repository": str(
                    section.get("model_checkpoint_repository", "vskode/bacpipe_models")
                ),
                "checkpoint_dir": str(checkpoint_dir.resolve()),
            }
        )
        stage_optional = bool(section.get("stage_optional_models", True))
        repository = str(
            section.get("model_checkpoint_repository", "vskode/bacpipe_models")
        )
        ensure_models = getattr(bacpipe, "ensure_models_exist", None)
        if not callable(ensure_models):
            issues.append("bacpipe_ensure_models_exist_unavailable")

        # Calling Embedder directly does not download every Bacpipe checkpoint.
        # Provision each configured model explicitly before validation so a fresh
        # environment is reproducible and does not leave dependent Slurm jobs stuck.
        for model in models:
            name = model["name"]
            if not model["required"] and not stage_optional:
                continue
            checkpoint_staging["requested"].append(name)
            try:
                if not callable(ensure_models):
                    raise AttributeError("bacpipe.ensure_models_exist is unavailable")
                ensure_models(checkpoint_dir, [name], repo_id=repository)
                checkpoint_staging["completed"].append(name)
            except Exception as exc:
                message = f"{type(exc).__name__}:{exc}"
                checkpoint_staging["failed"][name] = message
                warnings.append(f"model_checkpoint_staging_failed:{name}")
                print(f"MODEL STAGING {name}: {message}", file=sys.stderr)

        for model in models:
            name = model["name"]
            try:
                bacpipe.Embedder(name)
                instantiated[name] = "ok"
            except Exception as exc:
                initial_message = f"{type(exc).__name__}:{exc}"
                repaired = False
                if checkpoint_error_is_repairable(exc):
                    repair: dict[str, Any] = {
                        "trigger": initial_message,
                        "quarantined": [],
                        "status": "started",
                    }
                    checkpoint_staging["repairs"][name] = repair
                    try:
                        if not callable(ensure_models):
                            raise AttributeError(
                                "bacpipe.ensure_models_exist is unavailable"
                            )
                        repair["quarantined"] = quarantine_checkpoint_trees(
                            checkpoint_dir,
                            name,
                        )
                        ensure_models(checkpoint_dir, [name], repo_id=repository)
                        bacpipe.Embedder(name)
                        instantiated[name] = "ok"
                        repair["status"] = "repaired"
                        checkpoint_staging["completed"].append(name)
                        checkpoint_staging["failed"].pop(name, None)
                        repaired = True
                        print(
                            f"MODEL REPAIR {name}: redownloaded and validated",
                            file=sys.stderr,
                        )
                    except Exception as repair_exc:
                        repair["status"] = "failed"
                        repair["error"] = (
                            f"{type(repair_exc).__name__}:{repair_exc}"
                        )
                        exc = repair_exc
                if repaired:
                    continue
                message = f"failed:{type(exc).__name__}:{exc}"
                instantiated[name] = message
                if model["required"]:
                    issues.append(f"required_model_initialisation_failed:{name}")
                else:
                    warnings.append(f"optional_model_initialisation_failed:{name}")
                print(f"MODEL INITIALISATION {name}: {message}", file=sys.stderr)

    allowlist_path = Path(str(section.get("taxonomy_allowlist_csv", "")))
    require_allowlist = bool(section.get("require_taxonomy_allowlist", False))
    if not allowlist_path.is_file():
        message = f"taxonomy_allowlist_missing:{allowlist_path}"
        (issues if require_allowlist else warnings).append(message)

    registry = {
        "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
        "created_utc": utc_now_iso(),
        "status": "failed" if issues else ("has_warnings" if warnings else "validated"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "bacpipe_version": bacpipe_version,
        "expected_bacpipe_version": expected_version,
        "torch": torch_info,
        "device": section.get("device", "cuda"),
        "checkpoint_staging": checkpoint_staging,
        "models": [
            {
                **model,
                "model_fingerprint": model_fingerprint(config, model),
                "initialisation": instantiated.get(model["name"], "not_requested"),
            }
            for model in models
        ],
        "taxonomy_allowlist_csv": str(allowlist_path),
        "issues": issues,
        "warnings": warnings,
    }
    atomic_write_json(registry_path, registry)
    print(f"Bacpipe version : {bacpipe_version or 'unavailable'}")
    print(f"Configured models: {', '.join(model['name'] for model in models)}")
    print(f"Registry        : {registry_path}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for issue in issues:
        print(f"ERROR: {issue}", file=sys.stderr)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

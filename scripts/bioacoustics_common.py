#!/usr/bin/env python3
"""Shared helpers for the Step 6 bioacoustic inference workflow."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from common import atomic_write_json, resolve_output_path, utc_now_iso


BIOACOUSTIC_SCHEMA_VERSION = "2026-07-24-bioacoustics-v1"
MODEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "birdnet": {
        "required": True,
        "classifier": True,
        "taxon_scope": "birds",
        "segment_seconds": 3.0,
    },
    "perch_v2": {
        "required": True,
        "classifier": True,
        "taxon_scope": "multitaxon",
        "segment_seconds": 5.0,
    },
    "audioprotopnet": {
        "required": True,
        "classifier": True,
        "taxon_scope": "birds",
        "segment_seconds": 5.0,
    },
    "convnext_birdset": {
        "required": True,
        "classifier": True,
        "taxon_scope": "birds",
        "segment_seconds": 5.0,
    },
    "insect66": {
        "required": False,
        "classifier": False,
        "taxon_scope": "insects",
        "segment_seconds": 5.5,
    },
    "naturebeats": {
        "required": False,
        "classifier": False,
        "taxon_scope": "multitaxon_embedding",
        "segment_seconds": 5.0,
    },
}


def bio_config(config: dict[str, Any]) -> dict[str, Any]:
    section = config.get("bioacoustics")
    if not isinstance(section, dict):
        raise KeyError("Missing required 'bioacoustics' configuration section.")
    return section


def configured_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    section = bio_config(config)
    raw_models = section.get("models", list(MODEL_DEFAULTS))
    models: list[dict[str, Any]] = []
    for raw in raw_models:
        item = {"name": raw} if isinstance(raw, str) else dict(raw)
        name = str(item.get("name", "")).strip().lower()
        if not name:
            raise ValueError("Each bioacoustic model needs a non-empty name.")
        merged = dict(MODEL_DEFAULTS.get(name, {}))
        merged.update(item)
        merged["name"] = name
        merged["required"] = bool(merged.get("required", False))
        merged["classifier"] = bool(merged.get("classifier", False))
        merged["segment_seconds"] = float(merged.get("segment_seconds", 5.0))
        models.append(merged)
    names = [item["name"] for item in models]
    if len(names) != len(set(names)):
        raise ValueError("Bioacoustic model names must be unique.")
    return models


def output_path(config: dict[str, Any], key: str) -> Path:
    section = bio_config(config)
    value = section.get(key)
    if not value:
        raise KeyError(f"Missing bioacoustics.{key} in configuration.")
    return resolve_output_path(value)


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_fingerprint(config: dict[str, Any], model: dict[str, Any]) -> str:
    section = bio_config(config)
    return stable_json_hash(
        {
            "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
            "bacpipe_version": section.get("bacpipe_version", ""),
            "device": section.get("device", "cpu"),
            "model": model,
            "classifier_threshold": section.get("classifier_threshold", 0.1),
            "classifier_top_k": section.get("classifier_top_k", 5),
            "run_pretrained_classifier": section.get(
                "run_pretrained_classifier",
                True,
            ),
            "preprocessing_version": section.get("preprocessing_version", "v1"),
        }
    )


def configure_bacpipe_runtime(bacpipe_module: Any, section: dict[str, Any]) -> None:
    """Set result-relevant Bacpipe options explicitly instead of using defaults."""
    assignments = [
        (
            getattr(bacpipe_module, "settings", None),
            "device",
            str(section.get("device", "cuda")),
        ),
        (
            getattr(bacpipe_module, "config", None),
            "run_pretrained_classifier",
            bool(section.get("run_pretrained_classifier", True)),
        ),
        (
            getattr(bacpipe_module, "config", None),
            "classifier_threshold",
            float(section.get("classifier_threshold", 0.1)),
        ),
    ]
    for target, attribute, value in assignments:
        if target is None:
            continue
        try:
            setattr(target, attribute, value)
        except Exception as exc:
            raise RuntimeError(
                f"Could not set bacpipe {attribute}={value!r}: {exc}"
            ) from exc


def normalise_id(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    return "" if pd.isna(numeric) else str(int(numeric))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def audio_fingerprint(row: pd.Series) -> str:
    payload = {
        "dawn_chorus_id": normalise_id(row.get("dawn_chorus_id", "")),
        "source_path": str(row.get("source_path", "")),
        "size_bytes": str(row.get("size_bytes", "")),
        "mtime_ns": str(row.get("mtime_ns", "")),
        "sample_rate_hz": str(row.get("sample_rate_hz", "")),
        "duration_seconds": str(row.get("duration_seconds", "")),
    }
    return stable_json_hash(payload)


def work_key(dawn_chorus_id: str, audio_fp: str, model_fp: str) -> str:
    return hashlib.sha256(
        f"{dawn_chorus_id}\x1f{audio_fp}\x1f{model_fp}".encode("utf-8")
    ).hexdigest()


def shard_for_id(dawn_chorus_id: str, shard_count: int) -> int:
    digest = hashlib.sha256(str(dawn_chorus_id).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % max(1, shard_count)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def read_parquet_files(paths: Iterable[Path], columns: list[str] | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            continue
        try:
            frames.append(pd.read_parquet(path, columns=columns))
        except Exception:
            if columns is None:
                raise
            frame = pd.read_parquet(path)
            frames.append(frame[[column for column in columns if column in frame.columns]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns or [])


def load_task_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_task_state(
    path: Path,
    *,
    model: str,
    shard_index: int,
    shard_count: int,
    model_fp: str,
    completed_ids: Iterable[str],
    completed_work_keys: dict[str, str],
    failed_by_id: dict[str, str],
    status: str,
    batch_count: int,
) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
            "updated_utc": utc_now_iso(),
            "model": model,
            "shard_index": int(shard_index),
            "shard_count": int(shard_count),
            "model_fingerprint": model_fp,
            "status": status,
            "completed_ids": sorted(
                {str(value) for value in completed_ids},
                key=lambda value: int(value) if value.isdigit() else value,
            ),
            "completed_work_keys": dict(sorted(completed_work_keys.items())),
            "failed_by_id": dict(sorted(failed_by_id.items())),
            "batch_count": int(batch_count),
        },
    )


def sanitise_species_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return "" if text.lower() in {"", "nan", "none"} else text


def finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def slurm_task_index() -> int:
    return int(os.environ.get("SLURM_ARRAY_TASK_ID", "0"))

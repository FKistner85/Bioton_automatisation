#!/usr/bin/env python3
"""Step 6_2: Generate checkpointed Bacpipe embeddings and native predictions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common import load_config, write_progress_snapshot
from bioacoustics_common import (
    BIOACOUSTIC_SCHEMA_VERSION,
    atomic_write_parquet,
    bio_config,
    configured_models,
    configure_bacpipe_runtime,
    finite_float,
    load_task_state,
    output_path,
    sanitise_species_name,
    slurm_task_index,
    write_task_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument("--task-index", type=int)
    parser.add_argument("--verify-shards", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def verify_shards(config: dict[str, Any]) -> int:
    section = bio_config(config)
    models = configured_models(config)
    shard_count = int(section.get("shard_count", 16))
    worklist_path = output_path(config, "worklist_parquet")
    state_root = output_path(config, "inference_state_dir")
    if not worklist_path.is_file():
        print(f"ERROR: Worklist fehlt: {worklist_path}", file=sys.stderr)
        return 2

    worklist = pd.read_parquet(worklist_path)
    issues: list[str] = []
    warnings: list[str] = []
    verified_rows = 0
    for model_cfg in models:
        model_name = str(model_cfg["name"])
        model_required = bool(model_cfg.get("required", False))

        def record(problem: str) -> None:
            (issues if model_required else warnings).append(problem)

        model_rows = worklist[worklist["model"].astype(str) == model_name]
        for shard_index in range(shard_count):
            expected = model_rows[
                pd.to_numeric(model_rows["shard_index"], errors="coerce")
                == shard_index
            ]
            state_path = (
                state_root
                / f"model={model_name}"
                / f"shard={shard_index:04d}.json"
            )
            state = load_task_state(state_path)
            if not state:
                record(f"missing_state:{model_name}:{shard_index}")
                continue
            if state.get("status") != "complete":
                record(
                    f"non_complete_state:{model_name}:{shard_index}:"
                    f"{state.get('status', '')}"
                )
            if state.get("failed_by_id"):
                record(f"failed_ids:{model_name}:{shard_index}")
            if int(state.get("shard_count", -1)) != shard_count:
                record(f"shard_count_mismatch:{model_name}:{shard_index}")
            completed = {
                str(key): str(value)
                for key, value in state.get("completed_work_keys", {}).items()
            }
            for row in expected.to_dict("records"):
                dawn_id = str(row["dawn_chorus_id"])
                if completed.get(dawn_id) != str(row["work_key"]):
                    record(
                        f"missing_work_key:{model_name}:{shard_index}:{dawn_id}"
                    )
            verified_rows += len(expected)

    print(f"Verified models : {len(models)}")
    print(f"Verified shards : {len(models) * shard_count}")
    print(f"Verified rows   : {verified_rows:,}")
    if warnings:
        print(
            f"WARNING: {len(warnings)} optional-model shard issue(s) do not "
            "block completion.",
            file=sys.stderr,
        )
        for warning in warnings[:50]:
            print(f"- {warning}", file=sys.stderr)
    if issues:
        print(
            f"ERROR: Step 6_2 shard verification found {len(issues)} issue(s).",
            file=sys.stderr,
        )
        for issue in issues[:50]:
            print(f"- {issue}", file=sys.stderr)
        return 2
    print("Step 6_2 shard verification: OK")
    return 0


def as_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if isinstance(value, dict):
        for key in ("embeddings", "embedding", "features", "output"):
            if key in value:
                return as_numpy(value[key])
        if len(value) == 1:
            return as_numpy(next(iter(value.values())))
    if isinstance(value, (tuple, list)) and value:
        try:
            array = np.asarray(value)
            if array.dtype != object:
                return array
        except Exception:
            pass
        return as_numpy(value[0])
    return np.asarray(value)


def embedding_rows(
    raw: Any,
    work: dict[str, Any],
    segment_seconds: float,
) -> list[dict[str, Any]]:
    array = as_numpy(raw)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    elif array.ndim > 2:
        array = array.reshape(array.shape[0], -1)
    if array.ndim != 2 or not array.size:
        raise ValueError(f"Unexpected empty embedding shape: {array.shape}")
    rows = []
    for index, vector in enumerate(array):
        rows.append(
            {
                "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
                "dawn_chorus_id": str(work["dawn_chorus_id"]),
                "audio_fingerprint": str(work["audio_fingerprint"]),
                "model": str(work["model"]),
                "model_fingerprint": str(work["model_fingerprint"]),
                "work_key": str(work["work_key"]),
                "segment_index": int(index),
                "segment_start_seconds": float(index * segment_seconds),
                "segment_end_seconds": float((index + 1) * segment_seconds),
                "embedding_dimension": int(array.shape[1]),
                "embedding": np.asarray(vector, dtype=np.float32).tolist(),
            }
        )
    return rows


def labels_from_model(model: Any, width: int) -> list[str]:
    candidates = [
        getattr(model, "label2index", None),
        getattr(model, "labels", None),
        getattr(model, "class_names", None),
        getattr(model, "classes", None),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            if all(isinstance(value, (int, np.integer)) for value in candidate.values()):
                labels = [""] * width
                for label, index in candidate.items():
                    if 0 <= int(index) < width:
                        labels[int(index)] = str(label)
                if any(labels):
                    return labels
            if all(isinstance(key, (int, np.integer)) for key in candidate):
                return [str(candidate.get(index, "")) for index in range(width)]
        if isinstance(candidate, (list, tuple, np.ndarray)) and len(candidate) == width:
            return [str(value) for value in candidate]
    return []


def prediction_rows(
    raw: Any,
    embedder: Any,
    work: dict[str, Any],
    segment_seconds: float,
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    rows: list[dict[str, Any]] = []
    base = {
        "schema_version": BIOACOUSTIC_SCHEMA_VERSION,
        "dawn_chorus_id": str(work["dawn_chorus_id"]),
        "audio_fingerprint": str(work["audio_fingerprint"]),
        "model": str(work["model"]),
        "model_fingerprint": str(work["model_fingerprint"]),
        "work_key": str(work["work_key"]),
        "taxon_scope": str(work.get("taxon_scope", "")),
    }
    if isinstance(raw, dict):
        for outer_key, value in raw.items():
            if isinstance(value, dict):
                segment = int(outer_key) if str(outer_key).isdigit() else 0
                for species, score in value.items():
                    numeric = finite_float(score)
                    if numeric is not None:
                        rows.append(
                            {
                                **base,
                                "segment_index": segment,
                                "segment_start_seconds": segment * segment_seconds,
                                "segment_end_seconds": (segment + 1) * segment_seconds,
                                "species_raw": sanitise_species_name(species),
                                "score_raw": numeric,
                            }
                        )
            elif isinstance(value, (list, tuple, np.ndarray)) or hasattr(value, "shape"):
                array = as_numpy(value)
                if array.ndim == 1:
                    array = array.reshape(1, -1)
                if array.ndim != 2:
                    continue
                labels = labels_from_model(
                    getattr(embedder, "model", embedder),
                    array.shape[1],
                )
                if not labels:
                    continue
                for segment, scores in enumerate(array):
                    for label_index, score in enumerate(scores):
                        numeric = finite_float(score)
                        if numeric is None:
                            continue
                        rows.append(
                            {
                                **base,
                                "segment_index": int(segment),
                                "segment_start_seconds": segment * segment_seconds,
                                "segment_end_seconds": (segment + 1) * segment_seconds,
                                "species_raw": sanitise_species_name(labels[label_index]),
                                "score_raw": numeric,
                            }
                        )
            else:
                numeric = finite_float(value)
                if numeric is not None:
                    rows.append(
                        {
                            **base,
                            "segment_index": 0,
                            "segment_start_seconds": 0.0,
                            "segment_end_seconds": segment_seconds,
                            "species_raw": sanitise_species_name(outer_key),
                            "score_raw": numeric,
                        }
                    )
        return rows

    array = as_numpy(raw)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2:
        return []
    labels = labels_from_model(getattr(embedder, "model", embedder), array.shape[1])
    if not labels:
        return []
    for segment, scores in enumerate(array):
        for index, score in enumerate(scores):
            numeric = finite_float(score)
            if numeric is None:
                continue
            rows.append(
                {
                    **base,
                    "segment_index": int(segment),
                    "segment_start_seconds": segment * segment_seconds,
                    "segment_end_seconds": (segment + 1) * segment_seconds,
                    "species_raw": sanitise_species_name(labels[index]),
                    "score_raw": numeric,
                }
            )
    return rows


def select_predictions(
    rows: list[dict[str, Any]],
    *,
    threshold: float,
    top_k: int,
) -> list[dict[str, Any]]:
    """Keep only thresholded top-k scores per recording segment."""
    selected: list[dict[str, Any]] = []
    by_segment: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        score = finite_float(row.get("score_raw"))
        species = sanitise_species_name(row.get("species_raw"))
        if score is None or score < threshold or not species:
            continue
        cleaned = dict(row)
        cleaned["species_raw"] = species
        cleaned["score_raw"] = score
        by_segment.setdefault(int(row.get("segment_index", 0)), []).append(cleaned)
    for segment_rows in by_segment.values():
        segment_rows.sort(key=lambda row: float(row["score_raw"]), reverse=True)
        selected.extend(segment_rows[:top_k] if top_k > 0 else segment_rows)
    return selected


def main() -> int:
    args = parse_args()
    # Keep Bacpipe's relative checkpoint lookup stable for direct and Slurm runs.
    os.chdir(args.config.resolve().parent)
    config = load_config(args.config)
    if args.verify_shards:
        return verify_shards(config)
    section = bio_config(config)
    models = configured_models(config)
    shard_count = int(section.get("shard_count", 16))
    task_index = slurm_task_index() if args.task_index is None else args.task_index
    model_index, shard_index = divmod(task_index, shard_count)
    if model_index >= len(models):
        print(f"Task {task_index} has no configured model; nothing to do.")
        return 0
    model_cfg = models[model_index]
    model_name = model_cfg["name"]
    worklist_path = output_path(config, "worklist_parquet")
    worklist = pd.read_parquet(worklist_path)
    task_rows = worklist[
        (worklist["model"].astype(str) == model_name)
        & (pd.to_numeric(worklist["shard_index"], errors="coerce") == shard_index)
    ].copy()

    state_root = output_path(config, "inference_state_dir")
    embedding_root = output_path(config, "embedding_dir")
    native_root = output_path(config, "native_prediction_dir")
    for root in [state_root, embedding_root, native_root]:
        root.mkdir(parents=True, exist_ok=True)
    state_path = state_root / f"model={model_name}" / f"shard={shard_index:04d}.json"
    if args.force:
        pattern = f"part-shard{shard_index:04d}-batch*.parquet"
        for root in [embedding_root, native_root]:
            task_dir = root / f"model={model_name}"
            for old_part in task_dir.glob(pattern):
                old_part.unlink()
        if state_path.is_file():
            state_path.unlink()
    state = {} if args.force else load_task_state(state_path)
    expected_fp = str(task_rows["model_fingerprint"].iloc[0]) if not task_rows.empty else ""
    if state.get("model_fingerprint") != expected_fp:
        state = {}
    completed_work_keys = {
        str(key): str(value)
        for key, value in state.get("completed_work_keys", {}).items()
    }
    completed_ids = set(completed_work_keys)
    failed_by_id = {
        str(key): str(value) for key, value in state.get("failed_by_id", {}).items()
    }
    batch_index = int(state.get("batch_count", 0))
    completed_mask = task_rows.apply(
        lambda row: completed_work_keys.get(str(row["dawn_chorus_id"]))
        == str(row["work_key"]),
        axis=1,
    )
    pending = task_rows[~completed_mask]
    print(
        f"Model={model_name} shard={shard_index}/{shard_count} "
        f"rows={len(task_rows):,} pending={len(pending):,}"
    )
    if pending.empty:
        write_task_state(
            state_path,
            model=model_name,
            shard_index=shard_index,
            shard_count=shard_count,
            model_fp=expected_fp,
            completed_ids=completed_ids,
            completed_work_keys=completed_work_keys,
            failed_by_id=failed_by_id,
            status="complete",
            batch_count=batch_index,
        )
        return 0

    try:
        import bacpipe
    except Exception as exc:
        print(f"ERROR: Bacpipe import failed: {exc}", file=sys.stderr)
        return 1

    configure_bacpipe_runtime(bacpipe, section)
    embedder = bacpipe.Embedder(model_name)
    batch_size = max(1, int(section.get("checkpoint_batch_size", 16)))
    threshold = float(section.get("classifier_threshold", 0.1))
    top_k = int(section.get("classifier_top_k", 5))
    embedding_buffer: list[dict[str, Any]] = []
    prediction_buffer: list[dict[str, Any]] = []
    inference_started = time.monotonic()
    progress_path = (
        Path(section["inference_state_dir"])
        / "progress"
        / f"{model_name}_shard{shard_index:04d}.json"
    )

    def flush() -> None:
        nonlocal batch_index, embedding_buffer, prediction_buffer
        if not embedding_buffer and not prediction_buffer:
            return
        batch_name = f"part-shard{shard_index:04d}-batch{batch_index:06d}.parquet"
        if embedding_buffer:
            atomic_write_parquet(
                pd.DataFrame(embedding_buffer),
                embedding_root / f"model={model_name}" / batch_name,
            )
        if prediction_buffer:
            atomic_write_parquet(
                pd.DataFrame(prediction_buffer),
                native_root / f"model={model_name}" / batch_name,
            )
        batch_index += 1
        embedding_buffer = []
        prediction_buffer = []
        write_task_state(
            state_path,
            model=model_name,
            shard_index=shard_index,
            shard_count=shard_count,
            model_fp=expected_fp,
            completed_ids=completed_ids,
            completed_work_keys=completed_work_keys,
            failed_by_id=failed_by_id,
            status="running",
            batch_count=batch_index,
        )
        write_progress_snapshot(
            progress_path,
            step_name="step_6_2_bioacoustic_embeddings",
            total_batches=len(pending),
            completed_batches=min(len(pending), len(completed_work_keys) + len(failed_by_id)),
            succeeded=len(completed_work_keys),
            failed=len(failed_by_id),
            started_monotonic=inference_started,
            extra={
                "model": model_name,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "mastertable_update": "deferred_until_step_6_6_qc",
            },
        )

    for index, work in enumerate(pending.to_dict("records"), start=1):
        dawn_id = str(work["dawn_chorus_id"])
        try:
            raw_embeddings = embedder.get_embeddings_from_model(str(work["source_path"]))
            embedding_buffer.extend(
                embedding_rows(raw_embeddings, work, float(work["segment_seconds"]))
            )
            classifier_raw = getattr(getattr(embedder, "model", None), "classifier_outputs", None)
            native_rows = prediction_rows(
                classifier_raw,
                embedder,
                work,
                float(work["segment_seconds"]),
            )
            if bool(work.get("classifier_available")) and not native_rows:
                raise ValueError(
                    "Classifier model returned no interpretable class-score output."
                )
            prediction_buffer.extend(
                select_predictions(native_rows, threshold=threshold, top_k=top_k)
            )
            completed_work_keys[dawn_id] = str(work["work_key"])
            completed_ids.add(dawn_id)
            failed_by_id.pop(dawn_id, None)
        except Exception as exc:
            failed_by_id[dawn_id] = (
                f"{type(exc).__name__}:{exc}\n"
                + "".join(traceback.format_exception_only(type(exc), exc)).strip()
            )[:2000]
        if index % batch_size == 0:
            flush()
            print(f"Checkpointed {index:,}/{len(pending):,}")
    flush()
    final_status = "complete" if not failed_by_id else "partial"
    write_task_state(
        state_path,
        model=model_name,
        shard_index=shard_index,
        shard_count=shard_count,
        model_fp=expected_fp,
        completed_ids=completed_ids,
        completed_work_keys=completed_work_keys,
        failed_by_id=failed_by_id,
        status=final_status,
        batch_count=batch_index,
    )
    print(f"Completed IDs: {len(completed_ids):,}; failed IDs: {len(failed_by_id):,}")
    return 0 if not failed_by_id else 2


if __name__ == "__main__":
    raise SystemExit(main())

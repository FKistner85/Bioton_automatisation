#!/usr/bin/env python3
"""Publish successful local outputs back to the canonical LSDF output tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


EXCLUDED_TOP_LEVEL = {
    "_local_bootstrap",
    "_local_publish",
    "step_0_local_logs",
    "step_0_slurm_logs",
    "step_0_manifests",
    "step_9_visual_reports",
    "step_9_validation",
}
EXCLUDED_CONTROL_DIRS = {"run_plans", "full_rebuild"}
EXCLUDED_RELATIVE_FILES = {
    Path("step_6_0_bioacoustic_model_preflight/model_registry.json"),
}
TEXT_SUFFIXES = {".csv", ".json", ".txt", ".md", ".html", ".tsv"}
PATH_COLUMN_MARKERS = ("path", "file", "directory", "source", "output")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


def excluded(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return False
    if parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    if relative in EXCLUDED_RELATIVE_FILES:
        return True
    if len(parts) >= 2 and parts[0] == "step_0_control" and parts[1] in EXCLUDED_CONTROL_DIRS:
        return True
    if relative.name == "pipeline.lock" or relative.name.endswith(".lock"):
        return True
    return relative.suffix.lower() in {".part", ".tmp"}


def path_replacements(settings: dict, repo_root: Path) -> list[tuple[str, str]]:
    workspace = Path(settings["workspace_dir"]).expanduser().resolve()
    mounted = mount_root(settings)
    cluster_project = str(
        settings.get("cluster_project_root", "/lsdf/kit/ipf/projects/Bio-O-Ton")
    ).rstrip("/")
    cluster_outputs = cluster_project + "/Data_automatisation_skripts/outputs"
    cluster_pipeline = cluster_project + "/Data_automatisation_skripts/bio_o_ton_pipeline/scripts_horeka"

    mappings = [
        (workspace / "outputs", cluster_outputs),
        (workspace / "lsdf_cache", cluster_project),
        (workspace / "model_checkpoints", cluster_pipeline + "/bacpipe/model_checkpoints"),
        (repo_root.resolve(), cluster_pipeline),
        (mounted, cluster_project),
    ]
    replacements: list[tuple[str, str]] = []
    for local, remote in mappings:
        variants = {str(local), str(local).replace("\\", "/")}
        for variant in sorted(variants, key=len, reverse=True):
            replacements.append((variant.rstrip("\\/"), remote))
    return sorted(set(replacements), key=lambda pair: len(pair[0]), reverse=True)


def translate_text(value: str, replacements: list[tuple[str, str]]) -> str:
    translated = value
    for local, remote in replacements:
        translated = translated.replace(local, remote)
    return translated.replace("\\", "/") if any(remote in translated for _, remote in replacements) else translated


def translate_json(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {
            translate_text(str(key), replacements): translate_json(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [translate_json(item, replacements) for item in value]
    if isinstance(value, str):
        return translate_text(value, replacements)
    return value


def remote_is_newer(source: Path, destination: Path) -> bool:
    if not destination.is_file():
        return False
    source_stat = source.stat()
    destination_stat = destination.stat()
    return destination_stat.st_mtime > source_stat.st_mtime + 1.0


def same_file(source: Path, destination: Path) -> bool:
    if not destination.is_file():
        return False
    source_stat = source.stat()
    destination_stat = destination.stat()
    # Published text/path-bearing Parquet files may differ in byte size because
    # local prefixes are translated. Exact preserved mtimes identify them.
    return abs(source_stat.st_mtime - destination_stat.st_mtime) < 1.0


def set_source_times(source: Path, destination: Path) -> None:
    source_stat = source.stat()
    os.utime(destination, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))


def write_translated_text(
    source: Path,
    temporary: Path,
    replacements: list[tuple[str, str]],
) -> None:
    if source.suffix.lower() == ".json":
        payload = load_json(source)
        temporary.write_text(
            json.dumps(translate_json(payload, replacements), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        with source.open("r", encoding="utf-8-sig", newline="") as reader, temporary.open(
            "w", encoding="utf-8", newline=""
        ) as writer:
            for line in reader:
                writer.write(translate_text(line, replacements))
    set_source_times(source, temporary)


def parquet_needs_translation(source: Path) -> bool:
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pq.ParquetFile(source).schema_arrow
    return any(
        (pa.types.is_string(field.type) or pa.types.is_large_string(field.type))
        and any(marker in field.name.lower() for marker in PATH_COLUMN_MARKERS)
        for field in schema
    )


def write_translated_parquet(
    source: Path,
    temporary: Path,
    replacements: list[tuple[str, str]],
) -> None:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(source)
    schema = parquet.schema_arrow
    writer = pq.ParquetWriter(temporary, schema, compression="zstd")
    try:
        for batch in parquet.iter_batches(batch_size=65536):
            table = pa.Table.from_batches([batch], schema=schema)
            columns = []
            for field, column in zip(schema, table.columns):
                translated = column
                if (
                    pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
                ) and any(marker in field.name.lower() for marker in PATH_COLUMN_MARKERS):
                    for local, remote in replacements:
                        translated = pc.replace_substring(translated, local, remote)
                    translated = pc.replace_substring(translated, "\\", "/")
                columns.append(translated)
            writer.write_table(pa.Table.from_arrays(columns, schema=schema))
    finally:
        writer.close()
    set_source_times(source, temporary)


def atomic_publish(
    source: Path,
    destination: Path,
    replacements: list[tuple[str, str]],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".local-upload.part")
    try:
        suffix = source.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            write_translated_text(source, temporary, replacements)
        elif suffix == ".parquet" and parquet_needs_translation(source):
            write_translated_parquet(source, temporary, replacements)
        else:
            shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def publish_outputs(settings: dict, repo_root: Path) -> dict:
    workspace = Path(settings["workspace_dir"]).expanduser().resolve()
    source_root = workspace / "outputs"
    relative_remote = str(
        settings.get("horeka_outputs_relative", "Data_automatisation_skripts/outputs")
    ).replace("/", os.sep)
    destination_root = mount_root(settings) / relative_remote
    remote_lock = destination_root / "step_0_control" / "pipeline.lock"
    if remote_lock.exists():
        raise RuntimeError(
            f"Remote Pipeline-Lock vorhanden; LSDF-Upload wird nicht gestartet: {remote_lock}"
        )
    if not source_root.is_dir():
        raise FileNotFoundError(f"Lokaler Outputordner fehlt: {source_root}")
    if not destination_root.is_dir():
        raise FileNotFoundError(f"LSDF-Outputordner ist nicht lesbar: {destination_root}")

    replacements = path_replacements(settings, repo_root)
    state_root = source_root / "_local_publish"
    state_path = state_root / "latest.json"
    state_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    state: dict[str, Any] = {
        "schema_version": "2026-08-03-local-publish-v1",
        "status": "in_progress",
        "source_root": str(source_root),
        "destination_root": str(destination_root),
        "started_unix": started,
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    uploaded = 0
    uploaded_bytes = 0
    unchanged = 0
    remote_newer = 0
    excluded_count = 0
    errors: list[str] = []
    last_progress = started
    print(f"LSDF PUBLISH: {source_root} -> {destination_root}")
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        if excluded(relative):
            excluded_count += 1
            continue
        destination = destination_root / relative
        try:
            if same_file(source, destination):
                unchanged += 1
                continue
            if remote_is_newer(source, destination):
                remote_newer += 1
                continue
            atomic_publish(source, destination, replacements)
            uploaded += 1
            uploaded_bytes += source.stat().st_size
        except Exception as exc:
            errors.append(f"{relative}: {type(exc).__name__}: {exc}")

        now = time.time()
        if now - last_progress >= 30:
            print(
                f"  hochgeladen={uploaded:,}, unveraendert={unchanged:,}, "
                f"remote_neuer={remote_newer:,}, GiB={uploaded_bytes / 2**30:.2f}"
            )
            last_progress = now

    state.update(
        {
            "status": "failed" if errors else "complete",
            "finished_unix": time.time(),
            "uploaded_files": uploaded,
            "uploaded_bytes": uploaded_bytes,
            "unchanged_files": unchanged,
            "remote_newer_files": remote_newer,
            "excluded_files": excluded_count,
            "errors": errors[:100],
        }
    )
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(
        f"LSDF PUBLISH: hochgeladen={uploaded:,}, unveraendert={unchanged:,}, "
        f"remote_neuer={remote_newer:,}, ausgeschlossen={excluded_count:,}, "
        f"GiB={uploaded_bytes / 2**30:.2f}"
    )
    if errors:
        print(f"ERROR: {len(errors)} Dateien konnten nicht veroeffentlicht werden.", file=sys.stderr)
        for error in errors[:10]:
            print(f"- {error}", file=sys.stderr)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    settings = load_json(args.settings)
    if not bool(settings.get("publish_successful_outputs_to_lsdf", True)):
        print("LSDF-Publish ist in local.settings.json deaktiviert.")
        return 0
    state = publish_outputs(settings, args.repo_root.resolve())
    return 0 if state.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

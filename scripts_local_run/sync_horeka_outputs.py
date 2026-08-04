#!/usr/bin/env python3
"""Bootstrap generated Horeka products into the local output workspace."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


EXCLUDED_TOP_LEVEL = {"step_0_slurm_logs", "step_0_local_logs"}
EXCLUDED_CONTROL_DIRS = {"run_plans", "full_rebuild"}
EXCLUDED_SUFFIXES = {".part", ".tmp"}
DEFAULT_EXCLUDED_DIRECTORY_NAMES = {
    "_chunk_checkpoints",
    "grid10m_chunks",
    "ix_chunks",
    "parquet_10",
}
DEFAULT_EXCLUDED_RELATIVE_DIRECTORIES = {
    "step_5_2_weather_download/hostrada_cache",
    "step_5_3_hostrada_monthly_download/netcdf",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


def excluded(
    relative: Path,
    excluded_directory_names: set[str] | None = None,
    excluded_relative_directories: set[str] | None = None,
) -> bool:
    parts = relative.parts
    if not parts:
        return False
    directory_names = (
        DEFAULT_EXCLUDED_DIRECTORY_NAMES
        if excluded_directory_names is None
        else excluded_directory_names
    )
    relative_directories = (
        DEFAULT_EXCLUDED_RELATIVE_DIRECTORIES
        if excluded_relative_directories is None
        else excluded_relative_directories
    )
    normalised = "/".join(parts).strip("/").casefold()
    if any(
        normalised == prefix or normalised.startswith(prefix + "/")
        for prefix in relative_directories
    ):
        return True
    if any(part in directory_names for part in parts[:-1]):
        return True
    if any(part == "pipeline.lock" or part.endswith(".lock") for part in parts):
        return True
    if parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    if len(parts) >= 2 and parts[0] == "step_0_control" and parts[1] in EXCLUDED_CONTROL_DIRS:
        return True
    return relative.suffix.lower() in EXCLUDED_SUFFIXES


def same_file(source_stat: os.stat_result, destination: Path) -> bool:
    if not destination.is_file():
        return False
    destination_stat = destination.stat()
    return (
        destination_stat.st_size == source_stat.st_size
        and abs(destination_stat.st_mtime - source_stat.st_mtime) < 1.0
    )


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def copy_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int,
    delay_seconds: float,
) -> os.stat_result:
    last_error: OSError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            source_stat = source.stat()
            atomic_copy(source, destination)
            return source_stat
        except OSError as exc:
            last_error = exc
            if attempt < max(1, attempts):
                time.sleep(max(0.0, delay_seconds) * attempt)
    assert last_error is not None
    raise last_error


def write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sync_outputs(settings: dict, *, refresh: bool = False) -> dict:
    mounted_project = mount_root(settings)
    relative_source = str(
        settings.get("horeka_outputs_relative", "Data_automatisation_skripts/outputs")
    ).replace("/", os.sep)
    source_root = mounted_project / relative_source
    workspace = Path(settings["workspace_dir"]).expanduser().resolve()
    destination_root = workspace / "outputs"
    state_path = destination_root / "_local_bootstrap" / "horeka_outputs.json"

    previous = load_json(state_path) if state_path.is_file() else {}
    if previous.get("status") == "complete" and not refresh:
        print(f"HOREKA OUTPUTS bereits uebernommen: {state_path}")
        print("Mit -RefreshHorekaOutputs werden spaetere Horeka-Ergebnisse erneut abgeglichen.")
        return previous
    if not source_root.is_dir():
        raise FileNotFoundError(f"Horeka-Outputordner ist nicht lesbar: {source_root}")

    started = time.time()
    excluded_directory_names = {
        str(value)
        for value in settings.get(
            "bootstrap_excluded_directories",
            sorted(DEFAULT_EXCLUDED_DIRECTORY_NAMES),
        )
        if str(value).strip()
    }
    excluded_relative_directories = {
        str(value).replace("\\", "/").strip("/").casefold()
        for value in settings.get(
            "bootstrap_excluded_relative_directories",
            sorted(DEFAULT_EXCLUDED_RELATIVE_DIRECTORIES),
        )
        if str(value).strip()
    }
    copy_attempts = max(1, int(settings.get("bootstrap_copy_attempts", 3)))
    retry_seconds = max(0.0, float(settings.get("bootstrap_retry_seconds", 1.0)))
    state = {
        "schema_version": "2026-08-04-horeka-output-bootstrap-v3",
        "status": "in_progress",
        "source_root": str(source_root),
        "destination_root": str(destination_root),
        "refresh": refresh,
        "excluded_directory_names": sorted(excluded_directory_names),
        "excluded_relative_directories": sorted(excluded_relative_directories),
        "copy_attempts": copy_attempts,
        "started_unix": started,
    }
    write_state(state_path, state)

    copied_files = 0
    copied_bytes = 0
    unchanged_files = 0
    preserved_local_files = 0
    excluded_files = 0
    excluded_directories = 0
    examined_files = 0
    errors: list[str] = []
    last_progress = started

    print(f"HOREKA OUTPUT BOOTSTRAP: {source_root} -> {destination_root}")
    print("Lokale neuere Dateien werden nicht ueberschrieben.")
    print(
        "Nicht uebernommen werden Zwischenchunks: "
        + ", ".join(sorted(excluded_directory_names))
    )
    print(
        "Direkt vom LSDF verwendete Downloadcaches: "
        + ", ".join(sorted(excluded_relative_directories))
    )

    def walk_error(exc: OSError) -> None:
        errors.append(f"directory_scan: {type(exc).__name__}: {exc}")

    for current, directories, filenames in os.walk(
        source_root,
        topdown=True,
        onerror=walk_error,
    ):
        current_path = Path(current)
        kept_directories = []
        for directory in directories:
            relative_directory = (current_path / directory).relative_to(source_root)
            if directory in excluded_directory_names or excluded(
                relative_directory / "_",
                excluded_directory_names,
                excluded_relative_directories,
            ):
                excluded_directories += 1
            else:
                kept_directories.append(directory)
        directories[:] = kept_directories

        for filename in filenames:
            source = current_path / filename
            relative = source.relative_to(source_root)
            if excluded(
                relative,
                excluded_directory_names,
                excluded_relative_directories,
            ):
                excluded_files += 1
                continue
            examined_files += 1
            destination = destination_root / relative
            try:
                source_stat = source.stat()
                if same_file(source_stat, destination):
                    unchanged_files += 1
                    continue
                if destination.is_file():
                    destination_stat = destination.stat()
                    if not refresh or destination_stat.st_mtime >= source_stat.st_mtime:
                        preserved_local_files += 1
                        continue
                source_stat = copy_with_retry(
                    source,
                    destination,
                    attempts=copy_attempts,
                    delay_seconds=retry_seconds,
                )
                copied_files += 1
                copied_bytes += source_stat.st_size
            except OSError as exc:
                errors.append(f"{relative}: {type(exc).__name__}: {exc}")

            now = time.time()
            if now - last_progress >= 30:
                print(
                    f"  kopiert={copied_files:,}, unveraendert={unchanged_files:,}, "
                    f"lokal_behalten={preserved_local_files:,}, GiB={copied_bytes / 2**30:.2f}"
                )
                last_progress = now

    if errors and examined_files == 0:
        final_status = "failed"
    elif errors:
        final_status = "partial"
    else:
        final_status = "complete"

    state.update(
        {
            "status": final_status,
            "finished_unix": time.time(),
            "copied_files": copied_files,
            "copied_bytes": copied_bytes,
            "unchanged_files": unchanged_files,
            "preserved_local_files": preserved_local_files,
            "excluded_files": excluded_files,
            "excluded_directories": excluded_directories,
            "examined_files": examined_files,
            "errors": errors[:100],
        }
    )
    write_state(state_path, state)
    print(
        f"HOREKA OUTPUTS: kopiert={copied_files:,}, unveraendert={unchanged_files:,}, "
        f"lokal_behalten={preserved_local_files:,}, ausgeschlossen={excluded_files:,}, "
        f"Chunkordner={excluded_directories:,}, GiB={copied_bytes / 2**30:.2f}"
    )
    if errors:
        level = "ERROR" if final_status == "failed" else "WARNING"
        print(
            f"{level}: {len(errors)} Pfade konnten nicht uebernommen werden; "
            "der naechste Lauf versucht sie erneut.",
            file=sys.stderr,
        )
        for error in errors[:10]:
            print(f"- {error}", file=sys.stderr)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    settings = load_json(args.settings)
    if not bool(settings.get("bootstrap_horeka_outputs", True)):
        print("Horeka-Output-Bootstrap ist in local.settings.json deaktiviert.")
        return 0
    state = sync_outputs(settings, refresh=args.refresh)
    return 0 if state.get("status") in {"complete", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

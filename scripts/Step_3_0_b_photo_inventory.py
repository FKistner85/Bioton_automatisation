#!/usr/bin/env python3
"""Step 3_0_b: Copy, inventory and validate Dawn Chorus photo files.

Files are discovered recursively by the ``_photo`` filename tag rather than by
an extension allow-list. Pillow verifies the image container and then fully
loads pixel data to detect truncated or corrupt files.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from common import print_path_report, resolve_existing_path, resolve_output_path

TAG_RE = re.compile(r"^(?P<id>\d+)_photo(?:$|[._-])", re.IGNORECASE)

DEFAULT_SOURCE = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/Images_SoundRecordings"
)
DEFAULT_PROCESSED = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs"
)

DETAIL_COLUMNS = [
    "dawn_chorus_id", "source_relative_path", "source_path",
    "destination_path", "filename", "extension", "size_bytes", "mtime_ns",
    "copied", "copy_verified", "image_verify_ok", "pixel_load_ok",
    "image_format", "width_px", "height_px", "mode", "exif_present",
    "has_issues", "issues",
]
FILE_LIST_COLUMNS = [
    "dawn_chorus_id", "source_relative_path", "source_path", "filename",
    "extension", "size_bytes", "mtime_ns",
]
NETWORK_ERROR_MARKERS = tuple(
    f"WinError {code}" for code in (53, 64, 121, 995, 1203)
)


def row_has_transport_error(row: dict[str, Any]) -> bool:
    issues = str(row.get("issues", ""))
    return any(marker in issues for marker in NETWORK_ERROR_MARKERS)


def load_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    section = config.get("photo_inventory", {})
    if not isinstance(section, dict):
        raise TypeError("'photo_inventory' must be a JSON object.")
    return config, section


def discover(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Photo source directory not found: {source_dir}")
    return sorted(
        path for path in source_dir.rglob("*")
        if path.is_file() and "_photo" in path.stem.lower()
    )


def build_file_list(files: list[Path], source_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in files:
        stat = path.stat()
        match = TAG_RE.match(path.stem)
        rows.append({
            "dawn_chorus_id": match.group("id") if match else "",
            "source_relative_path": path.relative_to(source_dir).as_posix(),
            "source_path": str(path),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        })
    return rows


def expected_download_ids(metadata_csv: Path, value_column: str) -> set[str]:
    """Return metadata IDs that have a non-empty media URL."""
    if not metadata_csv.is_file():
        raise FileNotFoundError(f"Dawn Chorus metadata CSV not found: {metadata_csv}")
    expected: set[str] = set()
    with metadata_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"id", value_column}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise KeyError(f"Missing metadata columns in {metadata_csv}: {sorted(missing)}")
        for row in reader:
            value = str(row.get(value_column, "")).strip()
            raw_id = str(row.get("id", "")).strip()
            if not value or value.lower() == "nan" or not raw_id:
                continue
            try:
                expected.add(str(int(float(raw_id))))
            except ValueError:
                continue
    return expected


def resolve_photo_directory(raw: str | Path, label: str, create_if_missing: bool) -> Path:
    report = resolve_existing_path(raw, label=label, expected="dir", required=False)
    print_path_report(report)
    if report.exists and report.is_dir:
        return report.resolved
    if not create_if_missing:
        raise NotADirectoryError(f"Photo {label} directory not found: {raw}")
    path = resolve_output_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    print(f"Created/using photo {label} directory: {path}")
    return path


def validate_and_copy(task: tuple[Path, Path, Path, bool]) -> dict[str, Any]:
    source, source_root, destination_root, force = task
    relative = source.relative_to(source_root)
    destination = destination_root / relative
    stat = source.stat()
    match = TAG_RE.match(source.stem)
    dawn_id = match.group("id") if match else ""
    issues: list[str] = []

    if not match:
        issues.append("filename_does_not_match_<id>_photo_pattern")

    destination.parent.mkdir(parents=True, exist_ok=True)
    copied = False
    try:
        same_file = source.resolve() == destination.resolve()
        needs_copy = (
            not same_file
            and (
                force
                or not destination.is_file()
                or destination.stat().st_size != stat.st_size
                or destination.stat().st_mtime_ns != stat.st_mtime_ns
            )
        )
        if needs_copy:
            shutil.copy2(source, destination)
            copied = True
    except Exception as exc:
        issues.append(f"copy_failed:{type(exc).__name__}:{exc}")

    copy_verified = False
    if destination.is_file():
        try:
            copy_verified = destination.stat().st_size == stat.st_size
            if not copy_verified:
                issues.append("copy_size_mismatch")
        except OSError as exc:
            issues.append(f"copy_verification_failed:{type(exc).__name__}:{exc}")
    else:
        issues.append("destination_missing_after_copy")

    target = destination if destination.is_file() else source
    verify_ok = False
    pixel_load_ok = False
    image_format = ""
    width = ""
    height = ""
    mode = ""
    exif_present = False

    try:
        with Image.open(target) as image:
            image_format = str(image.format or "")
            width, height = image.size
            mode = str(image.mode)
            exif_present = bool(image.getexif())
            image.verify()
        verify_ok = True
    except Exception as exc:
        issues.append(f"image_verify_failed:{type(exc).__name__}:{exc}")

    if verify_ok:
        try:
            with Image.open(target) as image:
                image.load()
            pixel_load_ok = True
        except Exception as exc:
            issues.append(f"pixel_load_failed:{type(exc).__name__}:{exc}")

    if width and height and (int(width) <= 0 or int(height) <= 0):
        issues.append(f"invalid_dimensions:{width}x{height}")

    return {
        "dawn_chorus_id": dawn_id,
        "source_relative_path": relative.as_posix(),
        "source_path": str(source),
        "destination_path": str(destination),
        "filename": source.name,
        "extension": source.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "copied": copied,
        "copy_verified": copy_verified,
        "image_verify_ok": verify_ok,
        "pixel_load_ok": pixel_load_ok,
        "image_format": image_format,
        "width_px": width,
        "height_px": height,
        "mode": mode,
        "exif_present": exif_present,
        "has_issues": bool(issues),
        "issues": " | ".join(issues),
    }


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            row["source_relative_path"]: row
            for row in csv.DictReader(handle)
            if row.get("source_relative_path")
        }


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Create a fast filesystem list without decoding legacy photos.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config, settings = load_config(args.config)
        processed_root = resolve_output_path(settings.get("processed_dir", DEFAULT_PROCESSED))
        create_source = bool(settings.get("create_source_dir_if_missing", True))
        source_dir = resolve_photo_directory(
            settings.get("source_dir", DEFAULT_SOURCE),
            label="image",
            create_if_missing=create_source,
        )
        output_dir = resolve_output_path(settings.get("output_dir", source_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        detailed_csv = resolve_output_path(settings.get(
            "detailed_log",
            processed_root / "photo_inventory_detailed.csv",
        ))
        compact_csv = resolve_output_path(settings.get(
            "compact_log",
            processed_root / "photo_inventory_compact.csv",
        ))
        file_list_csv = resolve_output_path(settings.get(
            "file_list_log", processed_root / "photo_file_list.csv",
        ))
        missing_ids_csv = resolve_output_path(settings.get(
            "missing_ids_log", processed_root / "photo_missing_ids.csv",
        ))
        status_dir = resolve_output_path(config.get("status_dir", processed_root / "_status"))
        state_file = resolve_output_path(settings.get(
            "state_file",
            status_dir / "step_3_0_b_photo_inventory_state.json",
        ))
        allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
        workers = max(1, min(int(settings.get("workers", allocated)), allocated))

        files = discover(source_dir)
        if args.list_only:
            file_rows = build_file_list(files, source_dir)
            existing_ids = {
                str(row["dawn_chorus_id"])
                for row in file_rows
                if row["dawn_chorus_id"] and int(row["size_bytes"]) > 0
            }
            expected_ids = expected_download_ids(
                Path(config["dawn_chorus_csv"]), "photo"
            )
            missing_ids = sorted(
                expected_ids - existing_ids,
                key=lambda value: int(value),
            )
            write_csv(file_list_csv, file_rows, FILE_LIST_COLUMNS)
            write_csv(
                missing_ids_csv,
                [{"dawn_chorus_id": value} for value in missing_ids],
                ["dawn_chorus_id"],
            )
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps({
                "mode": "list_only",
                "source_dir": str(source_dir),
                "source_files": len(file_rows),
                "file_list_log": str(file_list_csv),
                "expected_download_ids": len(expected_ids),
                "missing_download_ids": len(missing_ids),
                "missing_ids_log": str(missing_ids_csv),
            }, indent=2), encoding="utf-8")
            print(f"Fast photo file list rows     : {len(file_rows):,}")
            print(f"Missing photo download IDs    : {len(missing_ids):,}")
            print(f"File list                     : {file_list_csv}")
            print(f"Missing IDs                   : {missing_ids_csv}")
            return 0
        existing = read_existing(detailed_csv)
        current_rel = {path.relative_to(source_dir).as_posix() for path in files}
        retained = {
            key: value for key, value in existing.items()
            if key in current_rel
        }
        tasks = []
        for path in files:
            rel = path.relative_to(source_dir).as_posix()
            stat = path.stat()
            old = existing.get(rel)
            destination = output_dir / path.relative_to(source_dir)
            unchanged = (
                not args.force
                and old is not None
                and not row_has_transport_error(old)
                and old.get("size_bytes") == str(stat.st_size)
                and old.get("mtime_ns") == str(stat.st_mtime_ns)
                and destination.is_file()
                and destination.stat().st_size == stat.st_size
            )
            if not unchanged:
                tasks.append((path, source_dir, output_dir, args.force))

        print(f"Photo-tagged source files      : {len(files):,}")
        print(f"Previously valid manifest rows : {len(retained):,}")
        print(f"New/changed files to process   : {len(tasks):,}")
        print(f"Worker processes               : {workers}")

        if tasks:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(validate_and_copy, task) for task in tasks]
                for index, future in enumerate(as_completed(futures), 1):
                    row = future.result()
                    retained[row["source_relative_path"]] = {
                        key: str(value) for key, value in row.items()
                    }
                    if index % 500 == 0 or index == len(futures):
                        print(f"Processed {index:,}/{len(futures):,}")

        rows = [retained[key] for key in sorted(retained)]
        transport_rows = [row for row in rows if row_has_transport_error(row)]
        if transport_rows:
            raise ConnectionError(
                "Photo inventory stopped because the LSDF transport failed. "
                f"Affected rows: {len(transport_rows)}; sample: "
                f"{transport_rows[0].get('issues', '')}"
            )
        write_csv(detailed_csv, rows, DETAIL_COLUMNS)

        compact_by_id: dict[str, bool] = {}
        for row in rows:
            dawn_id = row.get("dawn_chorus_id", "")
            if dawn_id:
                compact_by_id[dawn_id] = (
                    compact_by_id.get(dawn_id, False)
                    or str(row.get("has_issues", "")).lower() == "true"
                )
        compact_rows = [
            {"dawn_chorus_id": dawn_id, "has_issues": has_issues}
            for dawn_id, has_issues in sorted(
                compact_by_id.items(), key=lambda item: int(item[0])
            )
        ]
        write_csv(
            compact_csv, compact_rows,
            ["dawn_chorus_id", "has_issues"],
        )

        issue_count = sum(
            str(row.get("has_issues", "")).lower() == "true" for row in rows
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with state_file.open("w", encoding="utf-8") as handle:
            json.dump({
                "source_dir": str(source_dir),
                "output_dir": str(output_dir),
                "detailed_log": str(detailed_csv),
                "compact_log": str(compact_csv),
                "source_files": len(files),
                "manifest_rows": len(rows),
                "files_with_issues": issue_count,
            }, handle, indent=2)

        print("Step 3_0_b completed.")
        print(f"Manifest rows               : {len(rows):,}")
        print(f"Files with issues           : {issue_count:,}")
        print(f"Copied photo directory      : {output_dir}")
        print(f"Detailed log                : {detailed_csv}")
        print(f"Compact log                 : {compact_csv}")
        print(f"State file                  : {state_file}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

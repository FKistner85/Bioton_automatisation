#!/usr/bin/env python3
"""Step 3_1_b: Download missing or problematic Dawn Chorus photos.

Compares IDs in dawn-chorus-soundscape.csv with Step 3_0_b logs, downloads
missing/problematic files from the ``photo`` URL column, validates them with
Pillow, and updates the existing detailed and compact photo inventories.

Each ID has a persistent maximum of five total download attempts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

from common import (
    print_path_report,
    read_ids_file,
    resolve_existing_path,
    resolve_output_path,
    run_mastertable_batch_update,
    write_progress_snapshot,
)

DETAIL_COLUMNS = [
    "dawn_chorus_id", "source_relative_path", "source_path",
    "destination_path", "filename", "extension", "size_bytes", "mtime_ns",
    "copied", "copy_verified", "image_verify_ok", "pixel_load_ok",
    "image_format", "width_px", "height_px", "mode", "exif_present",
    "has_issues", "issues",
]

RETRY_COLUMNS = [
    "dawn_chorus_id", "url", "attempt_count", "max_attempts",
    "last_attempt_utc", "last_http_status", "last_error",
    "current_filename", "has_issues", "terminal_failure",
]


def read_csv_dict(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            str(row.get(key, "")).strip(): row
            for row in csv.DictReader(handle)
            if str(row.get(key, "")).strip()
        }


def row_has_nonempty_file(row: dict[str, Any]) -> bool:
    try:
        return int(float(str(row.get("size_bytes", "0") or "0"))) > 0
    except (TypeError, ValueError):
        return False


def resolve_or_create_dir(raw: str | Path, label: str) -> Path:
    report = resolve_existing_path(raw, label=label, expected="dir", required=False)
    print_path_report(report)
    if report.exists and report.is_dir:
        return report.resolved
    path = resolve_output_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    print(f"Created/using {label} directory: {path}")
    return path


def resolve_worker_count(settings: dict[str, Any]) -> tuple[int, int, int]:
    allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", "1") or "1")
    max_workers = int(settings.get("max_workers", 24))
    override = os.environ.get("BIOOTON_MEDIA_DOWNLOAD_WORKERS", "").strip()
    configured_raw = override or str(settings.get("workers", "auto")).strip()
    configured = allocated if configured_raw.lower() == "auto" else int(configured_raw)
    workers = max(1, min(configured, allocated, max_workers))
    return workers, allocated, max_workers


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def extension_from_url(url: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix
    return suffix.lower() if suffix else ".jpg"


def download_atomic(url: str, destination: Path, timeout: int) -> tuple[int | None, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Bio-O-Ton-media-downloader/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
        if temporary.stat().st_size == 0:
            raise OSError("Downloaded file is empty.")
        temporary.replace(destination)
        return status, ""
    except urllib.error.HTTPError as exc:
        temporary.unlink(missing_ok=True)
        return exc.code, f"HTTPError:{exc.code}:{exc.reason}"
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        return None, f"{type(exc).__name__}:{exc}"


def validate(path: Path, dawn_id: str) -> dict[str, Any]:
    issues: list[str] = []
    verify_ok = load_ok = False
    image_format = mode = ""
    width = height = ""
    exif_present = False

    try:
        with Image.open(path) as image:
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
            with Image.open(path) as image:
                image.load()
            load_ok = True
        except Exception as exc:
            issues.append(f"pixel_load_failed:{type(exc).__name__}:{exc}")

    stat = path.stat()
    return {
        "dawn_chorus_id": dawn_id,
        "source_relative_path": path.name,
        "source_path": "",
        "destination_path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "copied": False,
        "copy_verified": True,
        "image_verify_ok": verify_ok,
        "pixel_load_ok": load_ok,
        "image_format": image_format,
        "width_px": width,
        "height_px": height,
        "mode": mode,
        "exif_present": exif_present,
        "has_issues": bool(issues),
        "issues": " | ".join(issues),
    }


def rebuild_compact(detail_rows: dict[str, dict[str, Any]], path: Path) -> None:
    by_id: dict[str, bool] = {}
    for row in detail_rows.values():
        dawn_id = str(row.get("dawn_chorus_id", "")).strip()
        if dawn_id:
            by_id[dawn_id] = by_id.get(dawn_id, False) or str(row.get("has_issues", "")).lower() == "true"
    rows = [
        {"dawn_chorus_id": dawn_id, "has_issues": issue}
        for dawn_id, issue in sorted(by_id.items(), key=lambda item: int(item[0]))
    ]
    write_csv_atomic(path, rows, ["dawn_chorus_id", "has_issues"])


def process_download_task(task: dict[str, Any]) -> dict[str, Any]:
    dawn_id = task["dawn_id"]
    url = task["url"]
    state = dict(task["state"])
    attempts = int(state.get("attempt_count", 0) or 0)

    if not url:
        state["last_error"] = "missing_photo_url"
        state["has_issues"] = "True"
        state["terminal_failure"] = "True"
        return {"dawn_id": dawn_id, "state": state, "detail": None}

    destination = task["output_dir"] / f"{dawn_id}_photo{extension_from_url(url)}"
    attempts += 1
    if task["sleep_seconds"] > 0:
        time.sleep(float(task["sleep_seconds"]))
    status, error = download_atomic(url, destination, int(task["timeout"]))
    state.update({
        "url": url,
        "attempt_count": str(attempts),
        "max_attempts": str(task["max_attempts"]),
        "last_attempt_utc": pd.Timestamp.utcnow().isoformat(),
        "last_http_status": "" if status is None else str(status),
        "last_error": error,
        "current_filename": destination.name,
    })

    if error:
        state["has_issues"] = "True"
        state["terminal_failure"] = str(attempts >= int(task["max_attempts"]))
        return {"dawn_id": dawn_id, "state": state, "detail": None}

    detail = validate(destination, dawn_id)
    has_issues = bool(detail["has_issues"])
    state["has_issues"] = str(has_issues)
    state["last_error"] = str(detail["issues"])
    state["terminal_failure"] = str(has_issues and attempts >= int(task["max_attempts"]))
    return {"dawn_id": dawn_id, "state": state, "detail": detail}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.json")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Process every metadata ID and reset exhausted retry state.",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="CSV containing IDs whose source URL changed or needs reconciliation.",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Download only IDs absent from the fast file list; ignore legacy QC flags.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with args.config.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        settings = config.get("photo_download", {})
        inventory = config["photo_inventory"]
        source_csv_report = resolve_existing_path(
            config["dawn_chorus_csv"],
            label="metadata CSV",
            expected="file",
        )
        print_path_report(source_csv_report)
        source_csv = source_csv_report.resolved
        output_dir = resolve_or_create_dir(
            inventory.get("output_dir", inventory["source_dir"]),
            label="image",
        )
        detail_csv = resolve_output_path(inventory["detailed_log"])
        compact_csv = resolve_output_path(inventory["compact_log"])
        file_list_csv = resolve_output_path(
            inventory.get("file_list_log", detail_csv.parent / "photo_file_list.csv")
        )
        retry_csv = resolve_output_path(settings.get("retry_log", output_dir.parent / "photo_download_retry_log.csv"))
        max_attempts = int(settings.get("max_attempts", 5))
        timeout = int(settings.get("timeout_seconds", 120))
        sleep_seconds = float(settings.get("sleep_between_downloads_seconds", 0.2))
        workers, allocated_cpus, max_workers = resolve_worker_count(settings)
        batch_write_size = int(settings.get("batch_write_size", 10))
        master_update_batch_size = int(settings.get("master_update_batch_size", 250))

        metadata = pd.read_csv(source_csv, usecols=["id", "photo"], low_memory=False)
        metadata["id"] = pd.to_numeric(metadata["id"], errors="coerce").astype("Int64")
        metadata = metadata[metadata["id"].notna()].drop_duplicates("id", keep="first")
        requested_ids = read_ids_file(args.ids_file)

        detail_rows = read_csv_dict(detail_csv, "source_relative_path")
        compact = read_csv_dict(compact_csv, "dawn_chorus_id")
        retries = read_csv_dict(retry_csv, "dawn_chorus_id")
        file_list_rows = read_csv_dict(file_list_csv, "source_relative_path")
        existing_ids = {
            str(row.get("dawn_chorus_id", "")).strip()
            for row in file_list_rows.values()
            if str(row.get("dawn_chorus_id", "")).strip()
            and row_has_nonempty_file(row)
        }

        good_ids = {
            str(row.get("dawn_chorus_id", "")).strip()
            for row in detail_rows.values()
            if str(row.get("dawn_chorus_id", "")).strip()
            and str(row.get("has_issues", "")).lower() == "false"
        }

        candidates = []
        for _, row in metadata.iterrows():
            dawn_id = str(int(row["id"]))
            url = "" if pd.isna(row["photo"]) else str(row["photo"]).strip()
            compact_issue = compact.get(dawn_id, {}).get("has_issues", "true").lower() == "true"
            if args.missing_only:
                selected = (
                    dawn_id not in existing_ids
                    and (args.ids_file is None or dawn_id in requested_ids)
                )
            else:
                selected = args.force or dawn_id in requested_ids or dawn_id not in good_ids or compact_issue
            if selected:
                candidates.append((dawn_id, url))

        print(f"Metadata IDs                  : {len(metadata):,}")
        print(f"Good photo IDs in inventory  : {len(good_ids):,}")
        print(f"Photo IDs in fast file list  : {len(existing_ids):,}")
        print(f"Missing/problem IDs          : {len(candidates):,}")

        tasks: list[dict[str, Any]] = []
        for index, (dawn_id, url) in enumerate(candidates, 1):
            state = retries.get(dawn_id, {
                "dawn_chorus_id": dawn_id, "url": url, "attempt_count": "0",
                "max_attempts": str(max_attempts), "last_attempt_utc": "",
                "last_http_status": "", "last_error": "", "current_filename": "",
                "has_issues": "True", "terminal_failure": "False",
            })
            previous_url = str(state.get("url", "")).strip()
            if args.force or previous_url != url:
                state = {
                    "dawn_chorus_id": dawn_id, "url": url, "attempt_count": "0",
                    "max_attempts": str(max_attempts), "last_attempt_utc": "",
                    "last_http_status": "", "last_error": "", "current_filename": "",
                    "has_issues": "True", "terminal_failure": "False",
                }
            attempts = int(state.get("attempt_count", 0) or 0)
            if str(state.get("terminal_failure", "")).lower() == "true" or attempts >= max_attempts:
                continue
            tasks.append({
                "index": index,
                "dawn_id": dawn_id,
                "url": url,
                "state": state,
                "output_dir": output_dir,
                "timeout": timeout,
                "max_attempts": max_attempts,
                "sleep_seconds": sleep_seconds,
            })

        print(f"Download tasks to run         : {len(tasks):,}")
        print(f"Parallel workers              : {workers}")
        print(f"Allocated Slurm CPUs          : {allocated_cpus}")
        print(f"Configured max workers        : {max_workers}")
        started = time.monotonic()
        completed_since_write = 0
        completed_since_master: list[str] = []
        progress_path = detail_csv.parent / "progress.json"
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(process_download_task, task) for task in tasks]
            for completed, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                dawn_id = result["dawn_id"]
                state = result["state"]
                detail = result["detail"]
                retries[dawn_id] = state
                if detail is not None:
                    detail_rows[str(detail["source_relative_path"])] = detail

                completed_since_write += 1
                completed_since_master.append(dawn_id)
                elapsed = time.monotonic() - started
                rate = completed / elapsed if elapsed > 0 else 0.0
                eta = (len(tasks) - completed) / rate if rate > 0 else 0.0
                status_label = (
                    "OK"
                    if detail is not None and not bool(detail["has_issues"])
                    else "ISSUE"
                )
                print(
                    f"[{completed}/{len(tasks)}] {status_label} {dawn_id} "
                    f"ETA {eta / 60:.1f} min"
                )

                if completed_since_write >= max(1, batch_write_size) or completed == len(tasks):
                    write_csv_atomic(detail_csv, list(detail_rows.values()), DETAIL_COLUMNS)
                    rebuild_compact(detail_rows, compact_csv)
                    write_csv_atomic(retry_csv, list(retries.values()), RETRY_COLUMNS)
                    write_progress_snapshot(
                        progress_path,
                        step_name="step_3_1_b_photo_download",
                        total_batches=len(tasks),
                        completed_batches=completed,
                        succeeded=sum(str(value.get("has_issues", "")).lower() == "false" for value in retries.values()),
                        failed=sum(str(value.get("has_issues", "")).lower() == "true" for value in retries.values()),
                        started_monotonic=started,
                        extra={"workers": workers, "master_update_batch_size": master_update_batch_size},
                    )
                    if master_update_batch_size > 0 and len(completed_since_master) >= master_update_batch_size:
                        run_mastertable_batch_update(
                            args.config,
                            completed_since_master,
                            step_name="step_3_1_b_photo_download",
                            request_dir=detail_csv.parent / "master_update_requests",
                        )
                        completed_since_master = []
                    completed_since_write = 0

        issue_count = sum(str(row.get("has_issues", "")).lower() == "true" for row in detail_rows.values())
        terminal_count = sum(str(row.get("terminal_failure", "")).lower() == "true" for row in retries.values())
        print("Step 3_1_b completed.")
        print(f"Inventory files with issues : {issue_count:,}")
        print(f"Terminal failures           : {terminal_count:,}")
        print(f"Retry log                   : {retry_csv}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

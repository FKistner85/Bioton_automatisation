#!/usr/bin/env python3
"""Step 4_1: Mirror Sentinel-2 GeoTIFFs from Google Drive."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from common import (
    finish_step_manifest,
    start_step_manifest,
    utc_now_iso,
    write_batch_status,
)


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TIF_ID_PATTERN = re.compile(r"(\d+)(?=\.tiff?$)", flags=re.IGNORECASE)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "sentinel2_download" not in config:
        raise KeyError("Missing sentinel2_download section in config.")
    return config


def get_drive_service(
    credentials_path: Path,
    token_path: Path,
    allow_interactive_auth: bool = False,
):
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not allow_interactive_auth:
                return None
            if not credentials_path.is_file():
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def extract_dawn_chorus_id(name: str) -> str:
    match = TIF_ID_PATTERN.search(name)
    return match.group(1) if match else ""


def load_wanted_ids(config: dict[str, Any], settings: dict[str, Any]) -> set[str]:
    metadata_csv = settings.get("metadata_csv")
    if metadata_csv is None and config.get("status_dir"):
        candidate = Path(config["status_dir"]) / "dawnchorus_metadata_clean.csv"
        if candidate.is_file():
            metadata_csv = str(candidate)
    if metadata_csv is None:
        metadata_csv = config.get("dawn_chorus_csv")
    if metadata_csv is None or not Path(metadata_csv).is_file():
        return set()

    try:
        frame = pd.read_csv(metadata_csv, sep=";", low_memory=False)
        if len(frame.columns) == 1:
            frame = pd.read_csv(metadata_csv, low_memory=False)
    except Exception:
        frame = pd.read_csv(metadata_csv, low_memory=False)
    lower_to_original = {column.lower(): column for column in frame.columns}
    id_column = None
    for candidate in ("dawn_chorus_id", "id", "recording_id"):
        if candidate in lower_to_original:
            id_column = lower_to_original[candidate]
            break
    if id_column is None:
        raise KeyError(f"No ID column found in Sentinel-2 metadata CSV: {metadata_csv}")
    ids = pd.to_numeric(frame[id_column], errors="coerce").dropna().astype("int64")
    return {str(value) for value in ids.tolist()}


def iter_folder(service, folder_id: str, page_size: int = 200):
    query = f"'{folder_id}' in parents and trashed=false"
    page_token = None
    while True:
        result = (
            service.files()
            .list(
                q=query,
                pageSize=page_size,
                fields=(
                    "nextPageToken, "
                    "files(id,name,mimeType,md5Checksum,modifiedTime,size)"
                ),
                pageToken=page_token,
            )
            .execute()
        )
        yield from result.get("files", [])
        page_token = result.get("nextPageToken")
        if not page_token:
            break


def validate_tif(
    path: Path,
    expected_bands: int,
    expected_height: int,
    expected_width: int,
) -> tuple[bool, dict[str, Any]]:
    try:
        with rasterio.open(path) as src:
            arr = src.read()
            bands, height, width = arr.shape
            nodata = src.nodata
        invalid = arr == nodata if nodata is not None else ~np.isfinite(arr)
        valid = arr[~invalid]
        stats = {
            "bands": bands,
            "height": height,
            "width": width,
            "valid_pixels": int(valid.size),
            "invalid_pixels": int(invalid.sum()),
        }
        if valid.size:
            stats.update(
                {
                    "min": float(valid.min()),
                    "max": float(valid.max()),
                    "mean": float(valid.mean()),
                    "std": float(valid.std()),
                }
            )
        ok = (
            bands == expected_bands
            and height == expected_height
            and width == expected_width
            and valid.size > 0
            and stats.get("std", 0.0) != 0.0
        )
        return ok, stats
    except Exception as exc:
        return False, {"error": repr(exc)}


def download_one(
    service,
    file_obj: dict[str, Any],
    output_dir: Path,
    force: bool = False,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / file_obj["name"]
    if not force and path.exists() and path.stat().st_size > 0:
        return path
    request = service.files().get_media(fileId=file_obj["id"])
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with io.FileIO(temporary, "wb") as file:
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    temporary.replace(path)
    return path


def read_log(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as file:
        return {
            str(row.get("name", "")).strip(): row
            for row in csv.DictReader(file)
            if str(row.get("name", "")).strip()
        }


def write_log_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = sorted({key for row in rows for key in row})
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def drive_metadata_matches(
    previous: dict[str, Any] | None,
    file_obj: dict[str, Any],
) -> bool:
    if not previous:
        return False
    comparisons = {
        "drive_file_id": file_obj.get("id", ""),
        "drive_md5_checksum": file_obj.get("md5Checksum", ""),
        "drive_modified_time": file_obj.get("modifiedTime", ""),
        "drive_size": file_obj.get("size", ""),
    }
    if not any(str(previous.get(key, "")).strip() for key in comparisons):
        return False
    return all(
        str(previous.get(key, "")).strip() == str(value).strip()
        for key, value in comparisons.items()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Sentinel-2 TIFs.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--allow-interactive-auth",
        action="store_true",
        help="Allow browser-based OAuth setup. Do not use this in unattended Slurm jobs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        settings = config["sentinel2_download"]
        output_dir = Path(settings["output_dir"])
        log_csv = Path(settings["log_csv"])
        credentials_path = Path(settings.get("credentials_path", "credentials.json"))
        token_path = Path(settings.get("token_path", "token.json"))
        if not credentials_path.is_absolute():
            credentials_path = args.config.resolve().parent / credentials_path
        if not token_path.is_absolute():
            token_path = args.config.resolve().parent / token_path
        log_csv.parent.mkdir(parents=True, exist_ok=True)
        batch_write_size = int(settings.get("batch_write_size", 10))
        batch_status_dir = log_csv.parent / "_file_status"
        mirror_only_metadata_ids = bool(settings.get("mirror_only_metadata_ids", True))
        previous = read_log(log_csv)
        rows = list(previous.values())
        wanted_ids = load_wanted_ids(config, settings)
        manifest_path, manifest = start_step_manifest(
            config,
            "step_4_1_sentinel2_download",
            config_path=args.config,
            inputs=[credentials_path, token_path],
            outputs=[output_dir, log_csv],
            parameters={
                "folder_id": settings["google_drive_folder_id"],
                "wanted_ids": len(wanted_ids),
                "mirror_only_metadata_ids": mirror_only_metadata_ids,
                "force": args.force,
                "allow_interactive_auth": args.allow_interactive_auth,
            },
            force=args.force,
        )
        service = get_drive_service(
            credentials_path,
            token_path,
            allow_interactive_auth=args.allow_interactive_auth,
        )
        if service is None:
            message = (
                "Google Drive credentials/token missing or interactive auth disabled; "
                "Sentinel-2 download skipped."
            )
            print(message)
            finish_step_manifest(
                manifest_path,
                manifest,
                "skipped",
                result={"reason": message},
                warnings=[message],
            )
            return 0

        processed_since_write = 0
        seen_drive_files = 0
        candidate_files = 0
        skipped_not_wanted = 0
        skipped_existing_ok = 0
        downloaded_or_validated = 0
        failed = 0
        for file_obj in iter_folder(service, settings["google_drive_folder_id"]):
            name = file_obj.get("name", "")
            if not name.lower().endswith((".tif", ".tiff")):
                continue
            seen_drive_files += 1
            dawn_id = extract_dawn_chorus_id(name)
            if mirror_only_metadata_ids and wanted_ids and dawn_id not in wanted_ids:
                skipped_not_wanted += 1
                continue
            candidate_files += 1
            batch_started_utc = utc_now_iso()
            batch_id = dawn_id or name
            path = output_dir / name
            previous_row = previous.get(name)
            remote_unchanged = drive_metadata_matches(previous_row, file_obj)
            previous_ok = (
                previous_row is not None
                and str(previous_row.get("ok", "")).lower() == "true"
            )
            if (
                not args.force
                and remote_unchanged
                and previous_ok
                and path.exists()
                and path.stat().st_size > 0
            ):
                print(f"{name}: skipped_log_ok")
                skipped_existing_ok += 1
                write_batch_status(
                    batch_status_dir,
                    batch_id,
                    "skipped",
                    outputs=[path],
                    result={"name": name, "reason": "existing_log_ok"},
                    started_utc=batch_started_utc,
                )
                continue

            remote_changed = previous_row is not None and not remote_unchanged
            if remote_changed:
                path = download_one(service, file_obj, output_dir, force=True)
                ok, stats = validate_tif(
                    path,
                    int(settings.get("expected_bands", 12)),
                    int(settings.get("expected_height", 101)),
                    int(settings.get("expected_width", 101)),
                )
            elif not args.force and path.exists() and path.stat().st_size > 0:
                ok, stats = validate_tif(
                    path,
                    int(settings.get("expected_bands", 12)),
                    int(settings.get("expected_height", 101)),
                    int(settings.get("expected_width", 101)),
                )
                if ok:
                    print(f"{name}: OK existing_local")
                else:
                    path = download_one(service, file_obj, output_dir, force=True)
                    ok, stats = validate_tif(
                        path,
                        int(settings.get("expected_bands", 12)),
                        int(settings.get("expected_height", 101)),
                        int(settings.get("expected_width", 101)),
                    )
            else:
                path = download_one(service, file_obj, output_dir, force=args.force)
                ok, stats = validate_tif(
                    path,
                    int(settings.get("expected_bands", 12)),
                    int(settings.get("expected_height", 101)),
                    int(settings.get("expected_width", 101)),
                )
            rows.append(
                {
                    "dawn_chorus_id": dawn_id,
                    "name": name,
                    "path": str(path),
                    "ok": ok,
                    "drive_file_id": file_obj.get("id", ""),
                    "drive_md5_checksum": file_obj.get("md5Checksum", ""),
                    "drive_modified_time": file_obj.get("modifiedTime", ""),
                    "drive_size": file_obj.get("size", ""),
                    **stats,
                }
            )
            previous[name] = rows[-1]
            rows = list(previous.values())
            print(f"{name}: {'OK' if ok else 'FAILED'}")
            downloaded_or_validated += 1
            if not ok:
                failed += 1
            write_batch_status(
                batch_status_dir,
                batch_id,
                "complete" if ok else "failed",
                outputs=[path],
                result={
                    "name": name,
                    "dawn_chorus_id": dawn_id,
                    "ok": bool(ok),
                    "remote_changed": remote_changed,
                    **stats,
                },
                error="" if ok else "Sentinel-2 validation failed.",
                started_utc=batch_started_utc,
            )
            processed_since_write += 1
            if processed_since_write >= max(1, batch_write_size):
                write_log_atomic(log_csv, rows)
                processed_since_write = 0

        write_log_atomic(log_csv, rows)
        print(f"Log: {log_csv}")
        result = {
            "drive_tif_files_seen": seen_drive_files,
            "wanted_ids": len(wanted_ids),
            "candidate_files": candidate_files,
            "skipped_not_wanted": skipped_not_wanted,
            "skipped_existing_ok": skipped_existing_ok,
            "downloaded_or_validated": downloaded_or_validated,
            "failed": failed,
        }
        finish_step_manifest(
            manifest_path,
            manifest,
            "partial" if failed else "complete",
            result=result,
        )
        return 0
    except Exception as exc:
        print(f"ERROR in Step 4_1: {exc}", file=sys.stderr)
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "failed",
                error=repr(exc),
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

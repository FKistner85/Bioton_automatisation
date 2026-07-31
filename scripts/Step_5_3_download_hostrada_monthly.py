#!/usr/bin/env python3
"""Step 5_3: Download monthly HOSTRADA NetCDF files for raster products."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "hostrada_monthly_download" not in config:
        raise KeyError("Missing hostrada_monthly_download section in config.")
    return config


def year_from_filename(filename: str) -> int:
    timestamp = filename.split("_")[-1].split("-")[0]
    return int(timestamp[:4])


def list_remote_files(session: requests.Session, base_url: str, pattern: str) -> list[str]:
    response = session.get(base_url, timeout=60)
    response.raise_for_status()
    regex = re.compile(r'href="([^"]+)"')
    wanted = re.compile(pattern)
    files = [
        match.group(1)
        for match in regex.finditer(response.text)
        if wanted.fullmatch(match.group(1))
    ]
    files.sort(key=lambda name: name.split("_")[-1].split("-")[0])
    return files


def download_file(
    url: str,
    destination: Path,
    chunk_size: int = 1024 * 1024,
    timeout: int = 300,
) -> str:
    if destination.exists() and destination.stat().st_size > 0:
        return "skipped_exists"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "bio-o-ton-hostrada/1.0"})
    with session.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with temporary.open("wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)
    temporary.replace(destination)
    return "downloaded"


def write_log_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = [
        "variable",
        "index",
        "total",
        "filename",
        "year",
        "path",
        "status",
        "size_bytes",
        "elapsed_seconds",
        "estimated_remaining_seconds",
        "error",
    ]
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def download_task(task: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    destination = Path(task["path"])
    try:
        status = download_file(
            task["url"],
            destination,
            chunk_size=int(task["chunk_size"]),
            timeout=int(task["timeout"]),
        )
        error = ""
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}:{exc}"
        destination.with_suffix(destination.suffix + ".part").unlink(missing_ok=True)
    return {
        **{key: task[key] for key in ["variable", "index", "total", "filename", "year", "path"]},
        "status": status,
        "size_bytes": destination.stat().st_size if destination.exists() else 0,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "estimated_remaining_seconds": "",
        "error": error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download monthly HOSTRADA NetCDF files."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument(
        "--variable",
        default=None,
        help="Optional variable key from config, e.g. Ta or Windspeed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_config(args.config)["hostrada_monthly_download"]
        output_dir = Path(settings["output_dir"])
        start_year = int(settings.get("start_year", 2017))
        workers = int(settings.get("workers", 4))
        chunk_size = int(settings.get("request_chunk_bytes", 1024 * 1024))
        timeout = int(settings.get("http_timeout_seconds", 300))
        variables: dict[str, Any] = settings["variables"]
        selected = [args.variable] if args.variable else sorted(variables)
        session = requests.Session()
        session.headers.update({"User-Agent": "bio-o-ton-hostrada/1.0"})
        log_csv = Path(settings["log_csv"])

        tasks: list[dict[str, Any]] = []
        for variable in selected:
            spec = variables[variable]
            files = [
                name
                for name in list_remote_files(
                    session,
                    spec["base_url"],
                    spec["filename_regex"],
                )
                if year_from_filename(name) >= start_year
            ]
            for index, name in enumerate(files, start=1):
                destination = output_dir / variable / name
                tasks.append(
                    {
                        "variable": variable,
                        "index": index,
                        "total": len(files),
                        "filename": name,
                        "year": year_from_filename(name),
                        "path": str(destination),
                        "url": spec["base_url"] + name,
                        "chunk_size": chunk_size,
                        "timeout": timeout,
                    }
                )

        print(f"HOSTRADA monthly files selected: {len(tasks):,}")
        print(f"Parallel workers              : {workers}")
        rows: list[dict[str, Any]] = []
        started = time.monotonic()

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(download_task, task) for task in tasks]
            for done, future in enumerate(as_completed(futures), start=1):
                row = future.result()
                elapsed = time.monotonic() - started
                rate = done / elapsed if elapsed > 0 else 0.0
                eta = (len(tasks) - done) / rate if rate > 0 else 0.0
                row["estimated_remaining_seconds"] = round(eta, 1)
                rows.append(row)
                write_log_atomic(log_csv, rows)
                print(
                    f"[{done}/{len(tasks)}] {row['variable']} "
                    f"{row['status']}: {row['filename']} "
                    f"ETA {eta / 60:.1f} min"
                )

        print(f"Log: {log_csv}")
        failed = sum(row["status"] == "failed" for row in rows)
        return 1 if failed else 0
    except Exception as exc:
        print(f"ERROR in Step 5_3: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

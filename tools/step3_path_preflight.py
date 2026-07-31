#!/usr/bin/env python3
"""Preflight path validation for Step 3 audio/photo pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from common import (  # noqa: E402
    print_path_report,
    resolve_existing_path,
    resolve_output_path,
)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def print_output_path(label: str, raw: str | Path) -> None:
    resolved = resolve_output_path(raw)
    parent = resolved.parent
    print(f"Configured {label} path: {raw}")
    print(f"Resolved {label} path: {resolved}")
    print(f"Parent exists: {parent.exists()}")
    print(f"Parent is directory: {parent.is_dir()}")
    print(f"Parent writable: {os.access(parent, os.W_OK) if parent.exists() else False}")
    print()


def print_directory_creation_path(label: str, raw: str | Path) -> bool:
    resolved = resolve_output_path(raw)
    parent = resolved.parent
    exists = resolved.exists()
    usable = resolved.is_dir() if exists else parent.is_dir() and os.access(parent, os.W_OK)
    print(f"Configured {label} path: {raw}")
    print(f"Resolved {label} path: {resolved}")
    print(f"Exists: {exists}")
    print(f"Is directory: {resolved.is_dir()}")
    print(f"Parent exists: {parent.exists()}")
    print(f"Parent is directory: {parent.is_dir()}")
    print(f"Parent writable: {os.access(parent, os.W_OK) if parent.exists() else False}")
    print(f"Usable/createable: {usable}")
    print()
    return usable


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Step 3 paths without processing data."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        audio = config.get("audio_inventory", {})
        photo = config.get("photo_inventory", {})

        checks = [
            resolve_existing_path(
                config["dawn_chorus_csv"],
                label="metadata CSV",
                expected="file",
                required=False,
            ),
            resolve_existing_path(
                audio["source_dir"],
                label="audio",
                expected="dir",
                required=False,
            ),
        ]

        print("Step 3 path preflight")
        print("=" * 72)
        for result in checks:
            print_path_report(result)
            print()
        image_source_usable = print_directory_creation_path(
            "image source",
            photo["source_dir"],
        )
        image_output_usable = print_directory_creation_path(
            "image output",
            photo.get("output_dir", photo["source_dir"]),
        )

        output_paths = [
            ("audio detailed log", audio["detailed_log"]),
            ("audio compact log", audio["compact_log"]),
            ("audio state file", audio["state_file"]),
            ("photo detailed log", photo["detailed_log"]),
            ("photo compact log", photo["compact_log"]),
            ("photo state file", photo["state_file"]),
            (
                "audio retry log",
                config.get("audio_download", {}).get(
                    "retry_log",
                    Path(audio["detailed_log"]).parent
                    / "audio_download_retry_log.csv",
                ),
            ),
            (
                "photo retry log",
                config.get("photo_download", {}).get(
                    "retry_log",
                    Path(photo["detailed_log"]).parent
                    / "photo_download_retry_log.csv",
                ),
            ),
        ]
        print("Step 3 output/write path preflight")
        print("=" * 72)
        for label, raw in output_paths:
            print_output_path(label, raw)

        failures = [
            result
            for result in checks
            if not result.exists
            or not result.readable
            or (
                result.label == "metadata CSV"
                and not result.is_file
            )
            or (
                result.label != "metadata CSV"
                and not result.is_dir
            )
        ]
        if failures or not image_source_usable or not image_output_usable:
            sys.stdout.flush()
            print("ERROR: Step 3 preflight found missing/unreadable paths.", file=sys.stderr)
            for result in failures:
                print(f"- {result.label}: {result.configured}", file=sys.stderr)
            if not image_source_usable:
                print(f"- image source: {photo['source_dir']}", file=sys.stderr)
            if not image_output_usable:
                print(f"- image output: {photo.get('output_dir', photo['source_dir'])}", file=sys.stderr)
            return 1

        print("Step 3 preflight completed successfully.")
        return 0
    except Exception as exc:
        print(f"ERROR: Step 3 preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

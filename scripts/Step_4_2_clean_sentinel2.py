#!/usr/bin/env python3
"""Step 4_2: Flag or remove Sentinel-2 GeoTIFFs with invalid shape."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import rasterio


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "sentinel2_cleaning" not in config:
        raise KeyError("Missing sentinel2_cleaning section in config.")
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flag or remove Sentinel-2 TIFs with invalid dimensions."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_config(args.config)["sentinel2_cleaning"]
        source_dir = Path(settings["source_dir"])
        expected_bands = int(settings.get("expected_bands", 12))
        expected_height = int(settings.get("expected_height", 101))
        expected_width = int(settings.get("expected_width", 101))
        dry_run = bool(settings.get("dry_run", True))
        log_csv = Path(settings["log_csv"])
        log_csv.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for tif_path in sorted(source_dir.glob("*.tif")):
            row: dict[str, Any] = {"path": str(tif_path), "name": tif_path.name}
            try:
                with rasterio.open(tif_path) as src:
                    row.update(
                        {
                            "bands": src.count,
                            "height": src.height,
                            "width": src.width,
                        }
                    )
                bad = (
                    row["bands"] != expected_bands
                    or row["height"] != expected_height
                    or row["width"] != expected_width
                )
                row["bad_shape"] = bad
                row["deleted"] = False
                if bad and not dry_run:
                    tif_path.unlink()
                    row["deleted"] = True
            except Exception as exc:
                row["error"] = str(exc)
                row["bad_shape"] = True
                row["deleted"] = False
            rows.append(row)

        with log_csv.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=sorted({key for row in rows for key in row}),
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"Checked: {len(rows):,}")
        print(f"Flagged: {sum(bool(row.get('bad_shape')) for row in rows):,}")
        print(f"Log: {log_csv}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 4_2: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

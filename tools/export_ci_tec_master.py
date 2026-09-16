#!/usr/bin/env python3
"""Export the ci-tec README columns from a complete master CSV, without coercion."""
from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path

COLUMNS = [
    "dawn_chorus_id", "lon", "lat", "grid_100m_id", "grid_10m_id",
    "datetime_local", "sound_exists", "sound_has_issues",
    "sentinel_exists", "sentinel_has_issues", "weather_point_exists",
    "weather_point_has_issues", "weather_raster_hostrada_100m_exists",
    "weather_raster_hostrada_100m_has_issues",
]


def export(source: Path, destination: Path) -> int:
    if source.resolve() == destination.resolve():
        raise ValueError("The compact export must not replace the complete master.")
    with source.open(encoding="utf-8-sig", newline="") as incoming:
        reader = csv.DictReader(incoming)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing master columns: {', '.join(sorted(missing))}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", delete=False,
                dir=destination.parent, prefix=destination.name + ".", suffix=".tmp",
            ) as outgoing:
                temporary = Path(outgoing.name)
                writer = csv.DictWriter(outgoing, fieldnames=COLUMNS, extrasaction="ignore")
                writer.writeheader()
                count = 0
                for row in reader:
                    writer.writerow(row)
                    count += 1
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or args.input.with_name("Bio_O_Ton_Master_CI_TEC.csv")
    count = export(args.input, destination)
    print(f"ci-tec master: {destination} ({count:,} rows, {len(COLUMNS)} columns)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build or verify checkpointed HOSTRADA variable/year raster products.

The normal Slurm path uses one deterministic ``variable x year`` task per
array element. The sequential default remains useful for local debugging.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import re
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import load_config
from Step_5_4_prepare_hostrada_rasters import (
    VARIABLES,
    build_year,
    expected_tile_jobs,
    finish_force_resume,
    prepare_force_resume,
    tile_status_is_complete,
)


YEAR_MONTH_PATTERN = re.compile(r"_(\d{4})(\d{2})\d{6}-\d{10}\.nc$")


def complete_years(input_dir: Path, variable: str) -> list[int]:
    months_by_year: dict[int, set[int]] = {}
    for path in (input_dir / variable).glob("*.nc"):
        match = YEAR_MONTH_PATTERN.search(path.name)
        if not match:
            continue
        year, month = int(match.group(1)), int(match.group(2))
        months_by_year.setdefault(year, set()).add(month)
    return sorted(year for year, months in months_by_year.items() if len(months) == 12)


def configured_jobs(config: dict, end_year: int | None = None) -> list[tuple[str, int]]:
    """Return stable array positions without relying on a mutable file listing."""
    start_year = int(config["hostrada_monthly_download"].get("start_year", 2017))
    final_year = end_year or datetime.now(timezone.utc).year
    if final_year < start_year:
        return []
    return [
        (variable, year)
        for variable in sorted(VARIABLES)
        for year in range(start_year, final_year + 1)
    ]


def task_is_complete(input_dir: Path, variable: str, year: int) -> bool:
    return year in complete_years(input_dir, variable)


def verify_complete_jobs(settings: dict) -> tuple[int, int]:
    """Ensure all complete source years have every expected output tile."""
    input_dir = Path(settings["input_dir"])
    checked = 0
    incomplete = 0
    for variable in sorted(VARIABLES):
        for year in complete_years(input_dir, variable):
            checked += 1
            output_dir = Path(settings["output_root"]) / f"Hostrada_{variable}"
            status_dir = output_dir / "_tile_status" / str(year)
            jobs = expected_tile_jobs(variable, year, settings)
            if not jobs or not all(
                tile_status_is_complete(status_dir, batch_id, output_path)
                for batch_id, _x, _y, output_path in jobs
            ):
                incomplete += 1
                print(f"INCOMPLETE: {variable} {year}")
    return checked, incomplete


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--task-index", type=int)
    parser.add_argument("--task-count", action="store_true")
    parser.add_argument("--verify-array", action="store_true")
    parser.add_argument("--end-year", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    settings = config["hostrada_raster_products"]
    input_dir = Path(settings["input_dir"])
    if args.task_count:
        print(len(configured_jobs(config, args.end_year)))
        return 0

    if args.verify_array:
        checked, incomplete = verify_complete_jobs(settings)
        print(
            f"Verified HOSTRADA variable/year products: {checked:,}; "
            f"incomplete: {incomplete:,}"
        )
        return 1 if incomplete else 0

    if args.task_index is None:
        jobs = [
            (variable, year)
            for variable in sorted(VARIABLES)
            for year in complete_years(input_dir, variable)
        ]
    else:
        jobs = configured_jobs(config, args.end_year)
        if args.task_index < 0 or args.task_index >= len(jobs):
            raise ValueError(
                f"Task index {args.task_index} outside 0..{len(jobs) - 1}"
            )
        variable, year = jobs[args.task_index]
        if not task_is_complete(input_dir, variable, year):
            print(
                f"[{args.task_index + 1}/{len(jobs)}] {variable} {year}: "
                "monthly input year is incomplete; skipping."
            )
            return 0
        jobs = [(variable, year)]
    print(f"Complete HOSTRADA variable/year jobs: {len(jobs):,}")
    started = time.monotonic()
    for index, (variable, year) in enumerate(jobs, start=1):
        effective_force = prepare_force_resume(
            settings,
            variable,
            year,
            args.force,
        )
        outputs = build_year(
            variable,
            year,
            settings,
            force=effective_force,
        )
        finish_force_resume(settings, variable, year)
        elapsed = time.monotonic() - started
        rate = index / elapsed if elapsed else 0.0
        eta = (len(jobs) - index) / rate if rate else 0.0
        print(
            f"[{index}/{len(jobs)}] {variable} {year}: "
            f"{len(outputs):,} tiles; ETA {eta / 3600:.2f} h"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Step 5_4: Build Susi-compatible HOSTRADA annual raster tile products."""

from __future__ import annotations

import argparse
import calendar
import gc
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rioxarray  # noqa: F401
import xarray as xr
from rasterio.transform import Affine

from common import (
    atomic_write_json,
    finish_step_manifest,
    output_is_nonempty,
    source_signature,
    start_step_manifest,
    utc_now_iso,
    write_batch_status,
)


VARIABLES = {
    "Ta": ("tas", "tas_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
    "Rh": ("hurs", "hurs_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
    "Radiation": ("rsds", "rsds_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
    "CloudCover": ("clt", "clt_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
    "Winddirection": ("sfcWind_direction", "sfcWind_direction_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
    "Windspeed": ("sfcWind", "sfcWind_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day:02d}23.nc"),
}


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "hostrada_raster_products" not in config:
        raise KeyError("Missing hostrada_raster_products section in config.")
    return config


def snap_down(value: int, base: int, step: int) -> int:
    return base + math.floor((value - base) / step) * step


def snap_up(value: int, base: int, step: int) -> int:
    return base + math.ceil((value - base) / step) * step


def month_path(input_dir: Path, variable: str, year: int, month: int) -> Path:
    _, last_day = calendar.monthrange(year, month)
    _, template = VARIABLES[variable]
    return input_dir / variable / template.format(
        year=year,
        month=month,
        last_day=last_day,
    )


def tile_status_is_complete(status_dir: Path, batch_id: str, output_path: Path) -> bool:
    status_path = status_dir / f"{batch_id}.json"
    if not output_is_nonempty(output_path) or not status_path.is_file():
        return False
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return status.get("status") in {"complete", "skipped"}


def expected_tile_jobs(
    variable: str,
    year: int,
    settings: dict[str, Any],
) -> list[tuple[str, int, int, Path]]:
    """Return the stable tile layout without opening any NetCDF input."""
    output_dir = Path(settings["output_root"]) / f"Hostrada_{variable}"
    tile = int(settings.get("tile_size_m", 50000))
    x_min = int(settings["x_min"])
    y_min = int(settings["y_min"])
    x_max = int(settings["x_max"])
    y_max = int(settings["y_max"])
    grid_x_min = snap_down(x_min, x_min, tile)
    grid_x_max = snap_up(x_max, x_min, tile)
    grid_y_min = snap_down(y_min, y_max, tile)
    grid_y_max = snap_up(y_max, y_max, tile)
    jobs = []
    for x in range(grid_x_min, grid_x_max, tile):
        for y in range(grid_y_min, grid_y_max, tile):
            out_path = output_dir / f"{variable}_{year}_tile_x{x:05d}_y{y:05d}.tif"
            batch_id = f"{variable}_{year}_tile_x{x:05d}_y{y:05d}"
            jobs.append((batch_id, x, y, out_path))
    return jobs


def prepare_force_resume(
    settings: dict[str, Any],
    variable: str,
    year: int,
    force: bool,
) -> bool:
    if not force:
        return False
    output_dir = Path(settings["output_root"]) / f"Hostrada_{variable}"
    status_dir = output_dir / "_tile_status" / str(year)
    state_path = output_dir / "_force_state" / f"{variable}_{year}.json"
    input_dir = Path(settings["input_dir"])
    signature = source_signature(
        [month_path(input_dir, variable, year, month) for month in range(1, 13)]
    )
    state: dict[str, Any] = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    if (
        state.get("status") == "in_progress"
        and state.get("source_signature") == signature
    ):
        print(f"Resuming interrupted full raster generation: {variable} {year}")
        return False
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_output = output_dir.resolve()
    resolved_status = status_dir.resolve()
    if resolved_output not in resolved_status.parents:
        raise ValueError(f"Unsafe tile status directory: {status_dir}")
    if status_dir.exists():
        shutil.rmtree(status_dir)
    atomic_write_json(
        state_path,
        {
            "schema_version": "2026-07-23-hostrada-force-state-v1",
            "workflow_run_id": os.environ.get("BIOOTON_RUN_ID", ""),
            "variable": variable,
            "year": year,
            "source_signature": signature,
            "status": "in_progress",
            "started_utc": utc_now_iso(),
            "finished_utc": "",
        },
    )
    return False


def finish_force_resume(
    settings: dict[str, Any],
    variable: str,
    year: int,
) -> None:
    output_dir = Path(settings["output_root"]) / f"Hostrada_{variable}"
    state_path = output_dir / "_force_state" / f"{variable}_{year}.json"
    if not state_path.is_file():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if state.get("status") != "in_progress":
        return
    state["status"] = "complete"
    state["finished_utc"] = utc_now_iso()
    state["completed_workflow_run_id"] = os.environ.get("BIOOTON_RUN_ID", "")
    atomic_write_json(state_path, state)


def build_year(variable: str, year: int, settings: dict[str, Any], force: bool = False) -> list[Path]:
    data_name, _ = VARIABLES[variable]
    input_dir = Path(settings["input_dir"])
    output_dir = Path(settings["output_root"]) / f"Hostrada_{variable}"
    output_dir.mkdir(parents=True, exist_ok=True)
    status_dir = output_dir / "_tile_status" / str(year)

    res = int(settings.get("resolution_m", 100))
    tile = int(settings.get("tile_size_m", 50000))
    src_crs = settings.get("source_crs", "EPSG:3034")
    dst_crs = settings.get("target_crs", "EPSG:3035")
    scale = int(settings.get("scale", 100))
    nodata = int(settings.get("nodata", -9999))

    x_min = int(settings["x_min"])
    y_min = int(settings["y_min"])
    x_max = int(settings["x_max"])
    y_max = int(settings["y_max"])
    x0 = x_min
    y0 = y_max

    grid_x_min = snap_down(x_min, x0, tile)
    grid_x_max = snap_up(x_max, x0, tile)
    grid_y_min = snap_down(y_min, y0, tile)
    grid_y_max = snap_up(y_max, y0, tile)
    width_full = int((grid_x_max - grid_x_min) // res)
    height_full = int((grid_y_max - grid_y_min) // res)
    transform = Affine(res, 0, grid_x_min, 0, -res, grid_y_max)

    tile_jobs = expected_tile_jobs(variable, year, settings)

    if not force and tile_jobs and all(
        tile_status_is_complete(status_dir, batch_id, out_path)
        for batch_id, _x, _y, out_path in tile_jobs
    ):
        print(
            f"All {len(tile_jobs):,} HOSTRADA tiles already complete for "
            f"{variable} {year}; skipping NetCDF processing."
        )
        return [out_path for _batch_id, _x, _y, out_path in tile_jobs]

    bands = []
    band_names = []
    for month in range(1, 13):
        path = month_path(input_dir, variable, year, month)
        if not path.exists():
            raise FileNotFoundError(f"Missing HOSTRADA file: {path}")
        ds = xr.open_dataset(path)
        data = ds[data_name].rio.write_crs(src_crs, inplace=False)
        quantiles = data.quantile([0.1, 0.5, 0.9], dim="time", skipna=True)
        quantiles = quantiles.rio.write_crs(src_crs, inplace=False)
        for quantile, label in [(0.1, "p10"), (0.5, "p50"), (0.9, "p90")]:
            bands.append(quantiles.sel(quantile=quantile, drop=True))
            band_names.append(f"{label}_m{month:02d}")
        ds.close()

    year_stack = xr.concat(bands, dim="band").assign_coords(
        band=np.arange(1, 37)
    )
    year_stack = year_stack.drop_vars(["lon", "lat"], errors="ignore")
    year_stack = year_stack.rio.set_spatial_dims(
        x_dim="X",
        y_dim="Y",
        inplace=False,
    )
    year_stack = year_stack.rio.write_crs(src_crs, inplace=False)
    projected = year_stack.rio.reproject(
        dst_crs,
        transform=transform,
        shape=(height_full, width_full),
        resampling=rasterio.enums.Resampling.bilinear,
        nodata=np.nan,
    )
    scaled = np.rint(projected * scale).where(np.isfinite(projected), nodata)
    raster = scaled.astype("int16").rio.write_nodata(nodata, inplace=False)

    outputs = []
    for batch_id, x, y, out_path in tile_jobs:
        batch_started_utc = utc_now_iso()
        if not force and tile_status_is_complete(status_dir, batch_id, out_path):
            write_batch_status(
                status_dir,
                batch_id,
                "skipped",
                outputs=[out_path],
                result={"reason": "existing_complete_tile"},
                started_utc=batch_started_utc,
            )
            outputs.append(out_path)
            continue
        write_batch_status(
            status_dir,
            batch_id,
            "running",
            result={"variable": variable, "year": year, "x": x, "y": y},
            started_utc=batch_started_utc,
        )
        try:
            clipped = raster.rio.clip_box(
                minx=x,
                miny=y,
                maxx=x + tile,
                maxy=y + tile,
            )
            temporary = out_path.with_name(f"{out_path.stem}.part.tif")
            temporary.unlink(missing_ok=True)
            clipped.rio.to_raster(
                temporary,
                compress="deflate",
                tiled=True,
                blockxsize=512,
                blockysize=512,
                BIGTIFF="IF_SAFER",
                NUM_THREADS=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")),
            )
            with rasterio.open(temporary, "r+") as dst:
                for band_index, name in enumerate(band_names, start=1):
                    dst.set_band_description(band_index, name)
            temporary.replace(out_path)
            write_batch_status(
                status_dir,
                batch_id,
                "complete",
                outputs=[out_path],
                result={"variable": variable, "year": year, "x": x, "y": y},
                started_utc=batch_started_utc,
            )
            outputs.append(out_path)
        except Exception as exc:
            write_batch_status(
                status_dir,
                batch_id,
                "failed",
                outputs=[out_path],
                result={"variable": variable, "year": year, "x": x, "y": y},
                error=repr(exc),
                started_utc=batch_started_utc,
            )
            raise

    del year_stack, projected, scaled, raster, bands, band_names
    gc.collect()
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare HOSTRADA annual raster tile products."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument("--variable", required=True, choices=sorted(VARIABLES))
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        settings = config["hostrada_raster_products"]
        input_dir = Path(settings["input_dir"])
        inputs = [
            month_path(input_dir, args.variable, args.year, month)
            for month in range(1, 13)
        ]
        output_dir = Path(settings["output_root"]) / f"Hostrada_{args.variable}"
        manifest_path, manifest = start_step_manifest(
            config,
            "step_5_4_prepare_hostrada_rasters",
            config_path=args.config,
            inputs=inputs,
            outputs=[output_dir],
            parameters={
                "variable": args.variable,
                "year": args.year,
                "resolution_m": int(settings.get("resolution_m", 100)),
                "tile_size_m": int(settings.get("tile_size_m", 50000)),
                "force": args.force,
            },
            force=args.force,
        )
        effective_force = prepare_force_resume(
            settings,
            args.variable,
            args.year,
            args.force,
        )
        outputs = build_year(
            args.variable,
            args.year,
            settings,
            force=effective_force,
        )
        finish_force_resume(settings, args.variable, args.year)
        print(f"Wrote {len(outputs):,} tiles")
        for path in outputs:
            print(path)
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "complete",
                result={"tiles": len(outputs), "output_dir": str(output_dir)},
            )
        return 0
    except Exception as exc:
        print(f"ERROR in Step 5_4: {exc}", file=sys.stderr)
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

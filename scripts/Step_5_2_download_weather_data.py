#!/usr/bin/env python3
"""Step 5_2: Download and extract HOSTRADA weather data per recording.

The scientific/data-processing logic is adapted directly from
``HOSTRADA_download_v5.ipynb``. Only pipeline integration was added:

- paths and runtime settings are read from ``config.json``;
- standard ``--config`` and ``--force`` command-line arguments;
- outputs, cache and log paths are created automatically;
- existing per-recording CSVs are skipped unless ``--force`` is used;
- a non-zero exit status is returned when recordings fail.

Configuration section::

    "weather_download": {
      "input_csv": "/path/to/Bio_O_Ton_Data_Master.csv",
      "output_dir": "/path/to/PointData/Weather/Hostrada",
      "cache_dir": "/path/to/hostrada_cache",
      "preceding_days": 10,
      "input_timezone": "Europe/Berlin"
    }

``input_csv`` may be omitted when the top-level ``dawn_chorus_csv`` points to
an input table containing ID, coordinates and recording date/time.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import logging
import os
import sys
import threading
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import xarray as xr
from pyproj import Transformer
from tqdm import tqdm

from common import (
    finish_step_manifest,
    processed_root_from_config,
    read_ids_file,
    run_mastertable_batch_update,
    start_step_manifest,
    utc_now_iso,
    write_batch_status,
    write_progress_snapshot,
)

HOSTRADA_BASE_URL = (
    "https://opendata.dwd.de/climate_environment/CDC/grids_germany/"
    "hourly/hostrada"
)

VARIABLES = {
    "air_temperature_mean": ("tas", "tas"),
    "cloud_cover": ("clt", "clt"),
    "humidity_relative": ("hurs", "hurs"),
    "radiation_downwelling": ("rsds", "rsds"),
    "wind_direction": ("sfcWind_direction", "sfcWind_direction"),
    "wind_speed": ("sfcWind", "sfcWind"),
}

DEFAULT_PRECEDING_DAYS = 10
DEFAULT_INPUT_TIMEZONE = "Europe/Berlin"
INPUT_CRS = "EPSG:4326"
HOSTRADA_CRS = "EPSG:3034"
DEFAULT_MAX_DOWNLOAD_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 5
DEFAULT_HTTP_TIMEOUT_SECONDS = 120
DEFAULT_REQUEST_CHUNK_BYTES = 1024 * 1024

logger = logging.getLogger("bioOton_hostrada")
_known_missing: set[tuple[str, int, int]] = set()
_global_datasets: dict[tuple[str, int, int], xr.Dataset | None] = {}
_worker_transformer: Transformer | None = None
_worker_preceding_days: int | None = None
_worker_input_timezone: str | None = None
_worker_cache_dir: Path | None = None
_worker_download_settings: dict[str, int] | None = None


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    section = config.get("weather_download")
    if not isinstance(section, dict):
        raise KeyError("Missing 'weather_download' section in config.json.")

    input_csv = section.get("input_csv") or config.get("dawn_chorus_csv")
    missing = []
    if not input_csv:
        missing.append("input_csv (or top-level dawn_chorus_csv)")
    for key in ("output_dir", "cache_dir"):
        if not section.get(key):
            missing.append(key)
    if missing:
        raise KeyError(
            "Missing required weather_download key(s): " + ", ".join(missing)
        )
    return config


def setup_logger(log_file: Path) -> None:
    warnings.filterwarnings("ignore", category=UserWarning, module="rioxarray")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False


def recording_time_window_utc(
    recording_dt_naive_or_aware: pd.Timestamp,
    preceding_days: int,
    input_tz: str,
) -> pd.DatetimeIndex:
    ts = pd.Timestamp(recording_dt_naive_or_aware)
    if ts.tzinfo is None:
        ts = ts.tz_localize(input_tz, ambiguous=True, nonexistent="shift_forward")
    local_day_start = ts.normalize()
    window_start_local = local_day_start - pd.Timedelta(days=preceding_days)
    window_end_local = local_day_start + pd.Timedelta(hours=23)
    return pd.date_range(
        start=window_start_local.tz_convert("UTC"),
        end=window_end_local.tz_convert("UTC"),
        freq="1h",
        tz="UTC",
    )


def months_spanning(times_utc: pd.DatetimeIndex) -> list[tuple[int, int]]:
    utc = times_utc.tz_convert("UTC") if times_utc.tz is not None else times_utc
    return sorted({(timestamp.year, timestamp.month) for timestamp in utc})


def hostrada_filename(abbr: str, year: int, month: int) -> str:
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}{month:02d}0100"
    end = f"{year:04d}{month:02d}{last_day:02d}23"
    return f"{abbr}_1hr_HOSTRADA-v1-0_BE_gn_{start}-{end}.nc"


def hostrada_url(variable_folder: str, abbr: str, year: int, month: int) -> str:
    return (
        f"{HOSTRADA_BASE_URL}/{variable_folder}/"
        f"{hostrada_filename(abbr, year, month)}"
    )


def download_with_retry(
    url: str,
    destination: Path,
    max_retries: int,
    retry_backoff_seconds: int,
    http_timeout_seconds: int,
    request_chunk_bytes: int,
) -> bool:
    if destination.exists() and destination.stat().st_size > 0:
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.with_suffix(destination.suffix + ".download.lock")
    lock_owned = False
    lock_wait_started = time.monotonic()
    lock_wait_seconds = max(1800, http_timeout_seconds * max_retries * 2)
    while not lock_owned:
        if destination.exists() and destination.stat().st_size > 0:
            return True
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            os.write(
                descriptor,
                f"pid={os.getpid()} thread={threading.get_ident()}\n".encode(),
            )
            os.close(descriptor)
            lock_owned = True
        except FileExistsError:
            try:
                lock_age = time.time() - lock_path.stat().st_mtime
                if lock_age > lock_wait_seconds * 2:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() - lock_wait_started > lock_wait_seconds:
                logger.error("Timed out waiting for cache lock: %s", lock_path)
                return False
            time.sleep(2)

    temporary = destination.with_suffix(
        destination.suffix
        + f".part.{os.getpid()}.{threading.get_ident()}"
    )
    try:
        if destination.exists() and destination.stat().st_size > 0:
            return True
        wait = retry_backoff_seconds
        for attempt in range(1, max_retries + 1):
            try:
                with requests.get(
                    url, stream=True, timeout=http_timeout_seconds
                ) as response:
                    if response.status_code == 404:
                        logger.warning("HTTP 404 (not published yet?): %s", url)
                        return False
                    response.raise_for_status()
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=request_chunk_bytes):
                            if chunk:
                                handle.write(chunk)
                temporary.replace(destination)
                return True
            except Exception as exc:
                logger.warning(
                    "Download failed (attempt %s/%s) for %s: %r",
                    attempt,
                    max_retries,
                    url,
                    exc,
                )
                temporary.unlink(missing_ok=True)
                if attempt < max_retries:
                    time.sleep(wait)
                    wait *= 2
        logger.error("Giving up on %s after %s attempts.", url, max_retries)
        return False
    finally:
        temporary.unlink(missing_ok=True)
        if lock_owned:
            lock_path.unlink(missing_ok=True)


def ensure_cached(
    variable_folder: str,
    abbr: str,
    year: int,
    month: int,
    cache_dir: Path,
    settings: dict[str, int],
) -> Path | None:
    key = (variable_folder, year, month)
    if key in _known_missing:
        return None
    local = cache_dir / variable_folder / hostrada_filename(abbr, year, month)
    if local.exists() and local.stat().st_size > 0:
        return local
    ok = download_with_retry(
        hostrada_url(variable_folder, abbr, year, month),
        local,
        settings["max_download_retries"],
        settings["retry_backoff_seconds"],
        settings["http_timeout_seconds"],
        settings["request_chunk_bytes"],
    )
    if not ok:
        _known_missing.add(key)
    return local if ok else None


def _find_dim(dims: tuple[str, ...], candidates: tuple[str, ...]) -> str | None:
    for dimension in dims:
        if dimension.lower() in candidates:
            return dimension
    return None


def get_dataset(
    variable_folder: str,
    abbr: str,
    year: int,
    month: int,
    cache_dir: Path,
    settings: dict[str, int],
) -> xr.Dataset | None:
    key = (variable_folder, year, month)
    if key in _global_datasets:
        return _global_datasets[key]
    local = ensure_cached(
        variable_folder, abbr, year, month, cache_dir, settings
    )
    if local is None:
        _global_datasets[key] = None
        return None
    try:
        dataset = xr.open_dataset(local, engine="netcdf4")
        _global_datasets[key] = dataset
        return dataset
    except Exception as exc:
        logger.error("Failed to open NetCDF %s: %r", local, exc)
        _global_datasets[key] = None
        return None


def extract_nearest_values(
    dataset: xr.Dataset,
    nc_variable: str,
    x_3034: float,
    y_3034: float,
    times_utc: pd.DatetimeIndex,
) -> np.ndarray:
    output = np.full(len(times_utc), np.nan, dtype=float)
    if dataset is None or nc_variable not in dataset.variables:
        return output
    try:
        data_array = dataset[nc_variable]
        x_dimension = _find_dim(data_array.dims, ("x", "rlon"))
        y_dimension = _find_dim(data_array.dims, ("y", "rlat"))
        if x_dimension is None or y_dimension is None:
            logger.warning(
                "Unexpected dims %s for %s; filling NaN.",
                data_array.dims,
                nc_variable,
            )
            return output
        point = data_array.sel(
            {x_dimension: x_3034, y_dimension: y_3034}, method="nearest"
        )
        times_naive = times_utc.tz_convert("UTC").tz_localize(None)
        file_times = pd.DatetimeIndex(point["time"].values)
        mask = np.isin(times_naive.values, file_times.values)
        if mask.any():
            values = point.sel(time=times_naive[mask].values).values
            output[mask] = np.asarray(values, dtype=float)
        return output
    except Exception as exc:
        logger.warning(
            "Extraction failed for %s: %r; filling NaN.", nc_variable, exc
        )
        return output


def point_within_raster(dataset: xr.Dataset, x_3034: float, y_3034: float) -> bool:
    try:
        coordinate_names = list(dataset.coords)
        x_coordinate = _find_dim(tuple(coordinate_names), ("x", "rlon"))
        y_coordinate = _find_dim(tuple(coordinate_names), ("y", "rlat"))
        if x_coordinate is None or y_coordinate is None:
            return True
        xs = dataset[x_coordinate].values
        ys = dataset[y_coordinate].values
        return (
            float(xs.min()) - 500 <= x_3034 <= float(xs.max()) + 500
            and float(ys.min()) - 500 <= y_3034 <= float(ys.max()) + 500
        )
    except Exception:
        return True


def process_recording(
    recording_id: str,
    latitude: float,
    longitude: float,
    recording_datetime: pd.Timestamp,
    output_path: Path,
    transformer: Transformer,
    preceding_days: int,
    input_timezone: str,
    cache_dir: Path,
    download_settings: dict[str, int],
) -> str:
    try:
        times_utc = recording_time_window_utc(
            recording_datetime, preceding_days, input_timezone
        )
        x_3034, y_3034 = transformer.transform(longitude, latitude)
        month_pairs = months_spanning(times_utc)

        bounds_checked = False
        bounds_ok = True
        for variable_folder, (abbr, _nc_variable) in VARIABLES.items():
            for year, month in month_pairs:
                probe = get_dataset(
                    variable_folder,
                    abbr,
                    year,
                    month,
                    cache_dir,
                    download_settings,
                )
                if probe is not None:
                    bounds_ok = point_within_raster(probe, x_3034, y_3034)
                    bounds_checked = True
                    break
            if bounds_checked:
                break

        if bounds_checked and not bounds_ok:
            logger.warning(
                "[%s] Point (%.5f, %.5f) is outside HOSTRADA extent; "
                "writing NaN-only CSV.",
                recording_id,
                latitude,
                longitude,
            )
            frame = pd.DataFrame(
                {
                    "datetime": times_utc.tz_convert(input_timezone).tz_localize(None)
                }
            )
            for variable_folder in VARIABLES:
                frame[variable_folder] = np.nan
            frame.to_csv(output_path, index=False)
            return "out_of_bounds"

        columns: dict[str, Any] = {
            "datetime": times_utc.tz_convert(input_timezone).tz_localize(None)
        }
        unavailable_source_months:ç®¹¶‰žËkºwµç@€¥¹‘¥•Í}‘½¹”è±¥ÍÑm¥¹Ñt€ômt4(€€€€€€€¥¹Ù•¹Ñ½Éå}ÕÍ•€ô‰½½°¡Ý•…Ñ¡•É}¥¹Ù•¹Ñ½Éä¤4(€€€€€€€™½È¥¹‘•à°É½Ü¥¸É•½É‘¥¹Ì¹¥Ñ•ÉÉ½ÝÌ ¤è4(€€€€€€€€€€€É•½É‘¥¹}¥€ôÍÑÈ¡É½Ýl‰%‰t¤4(€€€€€€€€€€€½ÕÑÁÕÐ€ôÍ…™•}½ÕÑÁÕÑ}Á…Ñ ¡½ÕÑÁÕÑ}‘¥È°ÍÑÈ¡É½Ýl‰%‰t¤¤4(€€€€€€€€€€€¥¹Ù•¹Ñ½Éå}É½Ü€ôÝ•…Ñ¡•É}¥¹Ù•¹Ñ½Éä¹•Ð¡É•½É‘¥¹}¥¤(€€€€€€€€€€€¥˜€ (€€€€€€€€€€€€€€€…ÉÌ¹µ¥ÍÍ¥¹}½¹±ä(€€€€€€€€€€€€€€€…¹¹½Ð…ÉÌ¹™½É”(€€€€€€€€€€€€€€€…¹½ÕÑÁÕÐ¹•á¥ÍÑÌ ¤(€€€€€€€€€€€€€€€…¹½ÕÑÁÕÐ¹ÍÑ…Ð ¤¹ÍÑ}Í¥é”€ø€À(€€€€€€€€€€€€¤è(€€€€€€€€€€€€€€€¥¹‘¥•Í}‘½¹”¹…ÁÁ•¹¡¥¹‘•à¤(€€€€€€€€€€€€€€€ÝÉ¥Ñ•}‰…Ñ¡}ÍÑ…ÑÕÌ (€€€€€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÍ}‘¥È°(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°(€€€€€€€€€€€€€€€€€€€€‰Í­¥ÁÁ•ˆ°(€€€€€€€€€€€€€€€€€€€½ÕÑÁÕÑÌõm½ÕÑÁÕÑt°(€€€€€€€€€€€€€€€€€€€É•ÍÕ±Ðõì‰É•…Í½¸ˆè€‰•á¥ÍÑ¥¹}¹½¹•µÁÑå}Ý•…Ñ¡•É}ÍÙ}µ¥ÍÍ¥¹}½¹±ä‰ô°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€•±¥˜€ (€€€€€€€€€€€€€€€¹½Ð…ÉÌ¹™½É”(€€€€€€€€€€€€€€€…¹É•½É‘¥¹}¥¹½Ð¥¸É•ÅÕ•ÍÑ•‘}¥‘Ì4(€€€€€€€€€€€€€€€…¹¥¹Ù•¹Ñ½Éå}ÕÍ•4(€€€€€€€€€€€€€€€…¹¥¹Ù•¹Ñ½Éå}µ…É­Í}Ý•…Ñ¡•É}½¬¡¥¹Ù•¹Ñ½Éå}É½Ü¤4(€€€€€€€€€€€€¤è4(€€€€€€€€€€€€€€€¥¹‘¥•Í}‘½¹”¹…ÁÁ•¹¡¥¹‘•à¤4(€€€€€€€€€€€€€€€ÝÉ¥Ñ•}‰…Ñ¡}ÍÑ…ÑÕÌ 4(€€€€€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÍ}‘¥È°4(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€€‰Í­¥ÁÁ•ˆ°4(€€€€€€€€€€€€€€€€€€€½ÕÑÁÕÑÌõm½ÕÑÁÕÑt°4(€€€€€€€€€€€€€€€€€€€É•ÍÕ±Ðõì‰É•…Í½¸ˆè€‰Ý•…Ñ¡•É}¥¹Ù•¹Ñ½Éå}½¬‰ô°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€•±¥˜€ 4(€€€€€€€€€€€€€€€¹½Ð…ÉÌ¹™½É”4(€€€€€€€€€€€€€€€…¹É•½É‘¥¹}¥¹½Ð¥¸É•ÅÕ•ÍÑ•‘}¥‘Ì4(€€€€€€€€€€€€€€€…¹¹½Ð¥¹Ù•¹Ñ½Éå}ÕÍ•4(€€€€€€€€€€€€€€€…¹½ÕÑÁÕÐ¹•á¥ÍÑÌ ¤4(€€€€€€€€€€€€€€€…¹½ÕÑÁÕÐ¹ÍÑ…Ð ¤¹ÍÑ}Í¥é”€ø€À4(€€€€€€€€€€€€¤è4(€€€€€€€€€€€€€€€¥¹‘¥•Í}‘½¹”¹…ÁÁ•¹¡¥¹‘•à¤4(€€€€€€€€€€€€€€€ÝÉ¥Ñ•}‰…Ñ¡}ÍÑ…ÑÕÌ 4(€€€€€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÍ}‘¥È°4(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€€‰Í­¥ÁÁ•ˆ°4(€€€€€€€€€€€€€€€€€€€½ÕÑÁÕÑÌõm½ÕÑÁÕÑt°4(€€€€€€€€€€€€€€€€€€€É•ÍÕ±Ðõì4(€€€€€€€€€€€€€€€€€€€€€€€€‰É•…Í½¸ˆè€‰•á¥ÍÑ¥¹}¹½¹•µÁÑå}Ý•…Ñ¡•É}ÍÙ}Ý¥Ñ¡½ÕÑ}¥¹Ù•¹Ñ½Éäˆ4(€€€€€€€€€€€€€€€€€€€ô°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€¥¹‘¥•Í}Ñ½}ÁÉ½•ÍÌ¹…ÁÁ•¹¡¥¹‘•à¤4(4(€€€€€€€±½•È¹¥¹™¼ ‰Q½Ñ…°É•½É‘¥¹Ì¥¸¥¹ÁÕÐMX€è€•Ìˆ°±•¸¡É•½É‘¥¹Ì¤¤4(€€€€€€€±½•È¹¥¹™¼ ‰]•…Ñ¡•È¥¹Ù•¹Ñ½ÉäÉ½ÝÌ±½…‘•€è€•Ìˆ°±•¸¡Ý•…Ñ¡•É}¥¹Ù•¹Ñ½Éä¤¤4(€€€€€€€±½•È¹¥¹™¼ ‰±É•…‘äÁÉ½•ÍÍ•€¡Í­¥ÁÁ¥¹œ¤€€è€•Ìˆ°±•¸¡¥¹‘¥•Í}‘½¹”¤¤4(€€€€€€€±½•È¹¥¹™¼ ‰9•Ü€¼™½É•€¡Ñ¼ÁÉ½•ÍÌ¤€€€€€è€•Ìˆ°±•¸¡¥¹‘¥•Í}Ñ½}ÁÉ½•ÍÌ¤¤4(4(€€€€€€€¹••‘•èÍ•ÑmÑÕÁ±•mÍÑÈ°ÍÑÈ°¥¹Ð°¥¹Ñut€ôÍ•Ð ¤4(€€€€€€€™½È¥¹‘•à¥¸¥¹‘¥•Í}Ñ½}ÁÉ½•ÍÌè4(€€€€€€€€€€€É½Ü€ôÉ•½É‘¥¹Ì¹¥±½m¥¹‘•át4(€€€€€€€€€€€ÑÉäè4(€€€€€€€€€€€€€€€Ñ¥µ•Ì€ôÉ•½É‘¥¹}Ñ¥µ•}Ý¥¹‘½Ý}ÕÑŒ 4(€€€€€€€€€€€€€€€€€€€É½Ýl‰‘…Ñ•Ñ¥µ”‰t°ÁÉ••‘¥¹}‘…åÌ°¥¹ÁÕÑ}Ñ¥µ•é½¹”4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€™½Èå•…È°µ½¹Ñ ¥¸µ½¹Ñ¡Í}ÍÁ…¹¹¥¹œ¡Ñ¥µ•Ì¤è4(€€€€€€€€€€€€€€€€€€€™½ÈÙ…É¥…‰±•}™½±‘•È°€¡…‰‰È°}¹}Ù…É¥…‰±”¤¥¸YI%	1L¹¥Ñ•µÌ ¤è4(€€€€€€€€€€€€€€€€€€€€€€€¹••‘•¹…‘ ¡Ù…É¥…‰±•}™½±‘•È°…‰‰È°å•…È°µ½¹Ñ ¤¤4(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸è4(€€€€€€€€€€€€€€€Á…ÍÌ4(4(€€€€€€€±½•È¹¥¹™¼ 4(€€€€€€€€€€€€‰AÉ”µ‘½Ý¹±½…‘¥¹œ€•ÌÕ¹¥ÅÕ”µ½¹Ñ¡±ä™¥±•ÌÝ¥Ñ €•ÌÝ½É­•ÉÌ¸¸¸ˆ°4(€€€€€€€€€€€±•¸¡¹••‘•¤°4(€€€€€€€€€€€…¡•}Ý½É­•ÉÌ°4(€€€€€€€€¤4(€€€€€€€Ý…ÉµÕÁ}ÍÑ…ÉÑ•€ôÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤4(€€€€€€€¹••‘•‘}±¥ÍÐ€ôÍ½ÉÑ•¡¹••‘•¤4(€€€€€€€Ý¥Ñ Q¡É•…‘A½½±á•ÕÑ½È¡µ…á}Ý½É­•ÉÌõµ…à Ä°…¡•}Ý½É­•ÉÌ¤¤…Ì•á•ÕÑ½Èè4(€€€€€€€€€€€™ÕÑÕÉ•Ì€ôì4(€€€€€€€€€€€€€€€•á•ÕÑ½È¹ÍÕ‰µ¥Ð 4(€€€€€€€€€€€€€€€€€€€•¹ÍÕÉ•}…¡•°4(€€€€€€€€€€€€€€€€€€€Ù…É¥…‰±•}™½±‘•È°4(€€€€€€€€€€€€€€€€€€€…‰‰È°4(€€€€€€€€€€€€€€€€€€€å•…È°4(€€€€€€€€€€€€€€€€€€€µ½¹Ñ °4(€€€€€€€€€€€€€€€€€€€…¡•}‘¥È°4(€€€€€€€€€€€€€€€€€€€‘½Ý¹±½…‘}Í•ÑÑ¥¹Ì°4(€€€€€€€€€€€€€€€€¤è€¡Ù…É¥…‰±•}™½±‘•È°å•…È°µ½¹Ñ ¤4(€€€€€€€€€€€€€€€™½ÈÙ…É¥…‰±•}™½±‘•È°…‰‰È°å•…È°µ½¹Ñ ¥¸¹••‘•‘}±¥ÍÐ4(€€€€€€€€€€€ô4(€€€€€€€€€€€™½È½µÁ±•Ñ•°™ÕÑÕÉ”¥¸•¹Õµ•É…Ñ” 4(€€€€€€€€€€€€€€€ÑÅ‘´ 4(€€€€€€€€€€€€€€€€€€€…Í}½µÁ±•Ñ•¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€Ñ½Ñ…°õ±•¸¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€‘•ÍŒô‰…¡”Ý…É´µÕÀˆ°4(€€€€€€€€€€€€€€€€€€€Õ¹¥Ðô‰™¥±”ˆ°4(€€€€€€€€€€€€€€€€¤°4(€€€€€€€€€€€€€€€ÍÑ…ÉÐôÄ°4(€€€€€€€€€€€€¤è4(€€€€€€€€€€€€€€€™ÕÑÕÉ”¹É•ÍÕ±Ð ¤4(€€€€€€€€€€€€€€€•±…ÁÍ•€ôÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤€´Ý…ÉµÕÁ}ÍÑ…ÉÑ•4(€€€€€€€€€€€€€€€É…Ñ”€ô½µÁ±•Ñ•€¼•±…ÁÍ•¥˜•±…ÁÍ•€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€•Ñ„€ô€¡±•¸¡™ÕÑÕÉ•Ì¤€´½µÁ±•Ñ•¤€¼É…Ñ”¥˜É…Ñ”€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€¥˜½µÁ±•Ñ•€”µ…à Ä°…¡•}Ý½É­•ÉÌ¤€ôô€Àè4(€€€€€€€€€€€€€€€€€€€±½•È¹¥¹™¼ 4(€€€€€€€€€€€€€€€€€€€€€€€€‰…¡”Ý…É´µÕÀQè€”¸Å˜µ¥¸€ •Ì¼•Ì¤ˆ°4(€€€€€€€€€€€€€€€€€€€€€€€•Ñ„€¼€ØÀ°4(€€€€€€€€€€€€€€€€€€€€€€€½µÁ±•Ñ•°4(€€€€€€€€€€€€€€€€€€€€€€€±•¸¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€€¤4(4(€€€€€€€ÁÉ½•ÍÍ•‘}½¬è±¥ÍÑmÍÑÉt€ômt4(€€€€€€€ÁÉ½•ÍÍ•‘}½ÕÑ}½™}‰½Õ¹‘Ìè±¥ÍÑmÍÑÉt€ômt4(€€€€€€€ÁÉ½•ÍÍ•‘}ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”è±¥ÍÑmÍÑÉt€ômt4(€€€€€€€ÁÉ½•ÍÍ•‘}™…¥±•è±¥ÍÑmÍÑÉt€ômt4(4(€€€€€€€É•½É‘¥¹}Ñ…Í­Ì€ômt4(€€€€€€€™½È¥¹‘•à¥¸¥¹‘¥•Í}Ñ½}ÁÉ½•ÍÌè4(€€€€€€€€€€€É½Ü€ôÉ•½É‘¥¹Ì¹¥±½m¥¹‘•át4(€€€€€€€€€€€É•½É‘¥¹}¥€ôÍÑÈ¡É½Ýl‰%‰t¤4(€€€€€€€€€€€É•½É‘¥¹}Ñ…Í­Ì¹…ÁÁ•¹ 4(€€€€€€€€€€€€€€€ì4(€€€€€€€€€€€€€€€€€€€€‰É•½É‘¥¹}¥ˆèÉ•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€€‰±…Ðˆè™±½…Ð¡É½Ýl‰±…Ð‰t¤°4(€€€€€€€€€€€€€€€€€€€€‰±¹œˆè™±½…Ð¡É½Ýl‰±¹œ‰t¤°4(€€€€€€€€€€€€€€€€€€€€‰‘…Ñ•Ñ¥µ”ˆèÁ¹Q¥µ•ÍÑ…µÀ¡É½Ýl‰‘…Ñ•Ñ¥µ”‰t¤¹¥Í½™½Éµ…Ð ¤°4(€€€€€€€€€€€€€€€€€€€€‰½ÕÑÁÕÑ}Á…Ñ ˆèÍÑÈ¡Í…™•}½ÕÑÁÕÑ}Á…Ñ ¡½ÕÑÁÕÑ}‘¥È°É•½É‘¥¹}¥¤¤°4(€€€€€€€€€€€€€€€ô4(€€€€€€€€€€€€¤4(4(€€€€€€€‘•˜É•µ•µ‰•È¡É•½É‘¥¹}¥èÍÑÈ°ÍÑ…ÑÕÌèÍÑÈ¤€´ø9½¹”è4(€€€€€€€€€€€¥˜ÍÑ…ÑÕÌ€ôô€‰½¬ˆè4(€€€€€€€€€€€€€€€ÁÉ½•ÍÍ•‘}½¬¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(€€€€€€€€€€€•±¥˜ÍÑ…ÑÕÌ€ôô€‰½ÕÑ}½™}‰½Õ¹‘Ìˆè4(€€€€€€€€€€€€€€€ÁÉ½•ÍÍ•‘}½ÕÑ}½™}‰½Õ¹‘Ì¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(€€€€€€€€€€€•±¥˜ÍÑ…ÑÕÌ€ôô€‰ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”ˆè4(€€€€€€€€€€€€€€€ÁÉ½•ÍÍ•‘}ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€ÁÉ½•ÍÍ•‘}™…¥±•¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(4(€€€€€€€‘•˜É•µ•µ‰•É}Ý¥Ñ¡}ÍÑ…ÑÕÍ}™¥±”¡É•½É‘¥¹}¥èÍÑÈ°ÍÑ…ÑÕÌèÍÑÈ°½ÕÑÁÕÑ}Á…Ñ èA…Ñ °ÍÑ…ÉÑ•‘}ÕÑŒèÍÑÈð9½¹”€ô9½¹”¤€´ø9½¹”è4(€€€€€€€€€€€É•µ•µ‰•È¡É•½É‘¥¹}¥°ÍÑ…ÑÕÌ¤4(€€€€€€€€€€€¥˜ÍÑ…ÑÕÌ¥¸ì‰½¬ˆ°€‰½ÕÑ}½™}‰½Õ¹‘Ìˆ°€‰ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”‰ôè4(€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÌ€ô€‰½µÁ±•Ñ”ˆ4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÌ€ô€‰™…¥±•ˆ4(€€€€€€€€€€€ÝÉ¥Ñ•}‰…Ñ¡}ÍÑ…ÑÕÌ 4(€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÍ}‘¥È°4(€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÑÕÌ°4(€€€€€€€€€€€€€€€½ÕÑÁÕÑÌõm½ÕÑÁÕÑ}Á…Ñ¡t°4(€€€€€€€€€€€€€€€É•ÍÕ±Ðõì‰É•½É‘¥¹}ÍÑ…ÑÕÌˆèÍÑ…ÑÕÍô°4(€€€€€€€€€€€€€€€•ÉÉ½Èôˆˆ¥˜‰…Ñ¡}ÍÑ…ÑÕÌ€ôô€‰½µÁ±•Ñ”ˆ•±Í”˜‰É•½É‘¥¹}ÍÑ…ÑÕÌõíÍÑ…ÑÕÍôˆ°4(€€€€€€€€€€€€€€€ÍÑ…ÉÑ•‘}ÕÑŒõÍÑ…ÉÑ•‘}ÕÑŒ°4(€€€€€€€€€€€€¤4(4(€€€€€€€ÍÑ…ÉÑ•‘}É•½É‘Ì€ôÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤4(€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•Èè±¥ÍÑmÍÑÉt€ômt4(€€€€€€€ÁÉ½É•ÍÍ}¹…µ”€ô€ 4(€€€€€€€€€€€˜‰ÁÉ½É•ÍÍ}Í¡…É‘}í…ÉÌ¹Ñ…Í­}¥¹‘•àèÀÍ‘ô¹©Í½¸ˆ4(€€€€€€€€€€€¥˜…ÉÌ¹Ñ…Í­}½Õ¹Ð€ø€Ä4(€€€€€€€€€€€•±Í”€‰ÁÉ½É•ÍÌ¹©Í½¸ˆ4(€€€€€€€€¤4(€€€€€€€ÁÉ½É•ÍÍ}Á…Ñ €ô€ 4(€€€€€€€€€€€ÁÉ½•ÍÍ•‘}É½½Ñ}™É½µ}½¹™¥œ¡½¹™¥œ¤4(€€€€€€€€€€€€¼€‰ÍÑ•Á|Õ|É}Ý•…Ñ¡•É}‘½Ý¹±½…ˆ4(€€€€€€€€€€€€¼ÁÉ½É•ÍÍ}¹…µ”4(€€€€€€€€¤4(4(€€€€€€€‘•˜É•Á½ÉÑ}É•½É‘¥¹}ÁÉ½É•ÍÌ¡½µÁ±•Ñ•è¥¹Ð°Ñ½Ñ…°è¥¹Ð¤€´ø9½¹”è4(€€€€€€€€€€€ÝÉ¥Ñ•}ÁÉ½É•ÍÍ}Í¹…ÁÍ¡½Ð 4(€€€€€€€€€€€€€€€ÁÉ½É•ÍÍ}Á…Ñ °4(€€€€€€€€€€€€€€€ÍÑ•Á}¹…µ”ô‰ÍÑ•Á|Õ|É}Ý•…Ñ¡•É}‘½Ý¹±½…ˆ°4(€€€€€€€€€€€€€€€Ñ½Ñ…±}‰…Ñ¡•ÌõÑ½Ñ…°°4(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}‰…Ñ¡•Ìõ½µÁ±•Ñ•°4(€€€€€€€€€€€€€€€ÍÕ••‘•õ±•¸¡ÁÉ½•ÍÍ•‘}½¬¤°4(€€€€€€€€€€€€€€€™…¥±•õ±•¸¡ÁÉ½•ÍÍ•‘}™…¥±•¤°4(€€€€€€€€€€€€€€€Í­¥ÁÁ•õ±•¸¡¥¹‘¥•Í}‘½¹”¤°4(€€€€€€€€€€€€€€€ÍÑ…ÉÑ•‘}µ½¹½Ñ½¹¥ŒõÍÑ…ÉÑ•‘}É•½É‘Ì°4(€€€€€€€€€€€€€€€•áÑÉ„õì4(€€€€€€€€€€€€€€€€€€€€‰É•½É‘¥¹}Ý½É­•ÉÌˆèÉ•½É‘¥¹}Ý½É­•ÉÌ°4(€€€€€€€€€€€€€€€€€€€€‰µ…ÍÑ•É}ÕÁ‘…Ñ•}‰…Ñ¡}Í¥é”ˆèµ…ÍÑ•É}ÕÁ‘…Ñ•}‰…Ñ¡}Í¥é”°4(€€€€€€€€€€€€€€€€€€€€‰ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”ˆè±•¸¡ÁÉ½•ÍÍ•‘}ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”¤°4(€€€€€€€€€€€€€€€ô°4(€€€€€€€€€€€€¤4(€€€€€€€€€€€¥˜€ 4(€€€€€€€€€€€€€€€µ…ÍÑ•É}ÕÁ‘…Ñ•}‰…Ñ¡}Í¥é”€ø€À4(€€€€€€€€€€€€€€€…¹±•¸¡½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È¤€øôµ…ÍÑ•É}ÕÁ‘…Ñ•}‰…Ñ¡}Í¥é”4(€€€€€€€€€€€€¤è4(€€€€€€€€€€€€€€€ÉÕ¹}µ…ÍÑ•ÉÑ…‰±•}‰…Ñ¡}ÕÁ‘…Ñ” 4(€€€€€€€€€€€€€€€€€€€…ÉÌ¹½¹™¥œ°4(€€€€€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È°4(€€€€€€€€€€€€€€€€€€€ÍÑ•Á}¹…µ”ô‰ÍÑ•Á|Õ|É}Ý•…Ñ¡•É}‘½Ý¹±½…ˆ°4(€€€€€€€€€€€€€€€€€€€É•ÅÕ•ÍÑ}‘¥ÈõÁÉ½É•ÍÍ}Á…Ñ ¹Á…É•¹Ð€¼€‰µ…ÍÑ•É}ÕÁ‘…Ñ•}É•ÅÕ•ÍÑÌˆ°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È¹±•…È ¤4(4(€€€€€€€¥˜É•½É‘¥¹}Ý½É­•ÉÌ€ø€Ä…¹É•½É‘¥¹}Ñ…Í­Ìè4(€€€€€€€€€€€½ÕÑÁÕÑ}‰å}¥€ôì4(€€€€€€€€€€€€€€€ÍÑÈ¡Ñ…Í­l‰É•½É‘¥¹}¥‰t¤èA…Ñ ¡Ñ…Í­l‰½ÕÑÁÕÑ}Á…Ñ ‰t¤4(€€€€€€€€€€€€€€€™½ÈÑ…Í¬¥¸É•½É‘¥¹}Ñ…Í­Ì4(€€€€€€€€€€€ô4(€€€€€€€€€€€Ý¥Ñ AÉ½•ÍÍA½½±á•ÕÑ½È 4(€€€€€€€€€€€€€€€µ…á}Ý½É­•ÉÌõÉ•½É‘¥¹}Ý½É­•ÉÌ°4(€€€€€€€€€€€€€€€¥¹¥Ñ¥…±¥é•Èõ¥¹¥Ñ}É•½É‘¥¹}Ý½É­•È°4(€€€€€€€€€€€€€€€¥¹¥Ñ…ÉÌô 4(€€€€€€€€€€€€€€€€€€€ÁÉ••‘¥¹}‘…åÌ°4(€€€€€€€€€€€€€€€€€€€¥¹ÁÕÑ}Ñ¥µ•é½¹”°4(€€€€€€€€€€€€€€€€€€€ÍÑÈ¡…¡•}‘¥È¤°4(€€€€€€€€€€€€€€€€€€€‘½Ý¹±½…‘}Í•ÑÑ¥¹Ì°4(€€€€€€€€€€€€€€€€€€€±¥ÍÐ¡}­¹½Ý¹}µ¥ÍÍ¥¹œ¤°4(€€€€€€€€€€€€€€€€¤°4(€€€€€€€€€€€€¤…Ì•á•ÕÑ½Èè4(€€€€€€€€€€€€€€€™ÕÑÕÉ•Ì€ôl4(€€€€€€€€€€€€€€€€€€€•á•ÕÑ½È¹ÍÕ‰µ¥Ð¡ÁÉ½•ÍÍ}É•½É‘¥¹}Ý½É­•È°Ñ…Í¬¤4(€€€€€€€€€€€€€€€€€€€™½ÈÑ…Í¬¥¸É•½É‘¥¹}Ñ…Í­Ì4(€€€€€€€€€€€€€€€t4(€€€€€€€€€€€€€€€™½È½µÁ±•Ñ•°™ÕÑÕÉ”¥¸•¹Õµ•É…Ñ” 4(€€€€€€€€€€€€€€€€€€€ÑÅ‘´ 4(€€€€€€€€€€€€€€€€€€€€€€€…Í}½µÁ±•Ñ•¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€€€€€Ñ½Ñ…°õ±•¸¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€€€€€‘•ÍŒô‰I•½É‘¥¹Ìˆ°4(€€€€€€€€€€€€€€€€€€€€€€€Õ¹¥Ðô‰É•Œˆ°4(€€€€€€€€€€€€€€€€€€€€¤°4(€€€€€€€€€€€€€€€€€€€ÍÑ…ÉÐôÄ°4(€€€€€€€€€€€€€€€€¤è4(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°ÍÑ…ÑÕÌ€ô™ÕÑÕÉ”¹É•ÍÕ±Ð ¤4(€€€€€€€€€€€€€€€€€€€É•µ•µ‰•É}Ý¥Ñ¡}ÍÑ…ÑÕÍ}™¥±” 4(€€€€€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€€€€€ÍÑ…ÑÕÌ°4(€€€€€€€€€€€€€€€€€€€€€€€½ÕÑÁÕÑ}‰å}¥‘mÉ•½É‘¥¹}¥‘t°4(€€€€€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(€€€€€€€€€€€€€€€€€€€¥˜½µÁ±•Ñ•€”µ…à Ä°É•½É‘¥¹}‰…Ñ¡}Í¥é”¤€ôô€À½È½µÁ±•Ñ•€ôô±•¸¡™ÕÑÕÉ•Ì¤è4(€€€€€€€€€€€€€€€€€€€€€€€•±…ÁÍ•€ôÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤€´ÍÑ…ÉÑ•‘}É•½É‘Ì4(€€€€€€€€€€€€€€€€€€€€€€€É…Ñ”€ô½µÁ±•Ñ•€¼•±…ÁÍ•¥˜•±…ÁÍ•€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€€€€€€€€€•Ñ„€ô€¡±•¸¡™ÕÑÕÉ•Ì¤€´½µÁ±•Ñ•¤€¼É…Ñ”¥˜É…Ñ”€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€€€€€€€€€±½•È¹¥¹™¼ 4(€€€€€€€€€€€€€€€€€€€€€€€€€€€€‰I•½É‘¥¹œQè€”¸Å˜µ¥¸€ •Ì¼•Ì¤ˆ°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€•Ñ„€¼€ØÀ°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€½µÁ±•Ñ•°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€±•¸¡™ÕÑÕÉ•Ì¤°4(€€€€€€€€€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€€€€€€€€€É•Á½ÉÑ}É•½É‘¥¹}ÁÉ½É•ÍÌ¡½µÁ±•Ñ•°±•¸¡™ÕÑÕÉ•Ì¤¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€ÑÉ…¹Í™½Éµ•È€ôQÉ…¹Í™½Éµ•È¹™É½µ}ÉÌ¡%9AUQ}IL°!=MQI}IL°…±Ý…åÍ}áäõQÉÕ”¤4(€€€€€€€€€€€ÁÉ½É•ÍÌ€ôÑÅ‘´ 4(€€€€€€€€€€€€€€€É•½É‘¥¹}Ñ…Í­Ì°4(€€€€€€€€€€€€€€€Ñ½Ñ…°õ±•¸¡É•½É‘¥¹}Ñ…Í­Ì¤°4(€€€€€€€€€€€€€€€‘•ÍŒô‰I•½É‘¥¹Ìˆ°4(€€€€€€€€€€€€€€€Õ¹¥Ðô‰É•Œˆ°4(€€€€€€€€€€€€¤4(€€€€€€€€€€€™½È½µÁ±•Ñ•°Ñ…Í¬¥¸•¹Õµ•É…Ñ”¡ÁÉ½É•ÍÌ°ÍÑ…ÉÐôÄ¤è4(€€€€€€€€€€€€€€€É•½É‘¥¹}¥€ôÍÑÈ¡Ñ…Í­l‰É•½É‘¥¹}¥‰t¤4(€€€€€€€€€€€€€€€‰…Ñ¡}ÍÑ…ÉÑ•‘}ÕÑŒ€ôÕÑ}¹½Ý}¥Í¼ ¤4(€€€€€€€€€€€€€€€ÁÉ½É•ÍÌ¹Í•Ñ}Á½ÍÑ™¥á}ÍÑÈ¡É•½É‘¥¹}¥‘lèÈÑt¤4(€€€€€€€€€€€€€€€ÍÑ…ÑÕÌ€ôÁÉ½•ÍÍ}É•½É‘¥¹œ 4(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€™±½…Ð¡Ñ…Í­l‰±…Ð‰t¤°4(€€€€€€€€€€€€€€€€€€€™±½…Ð¡Ñ…Í­l‰±¹œ‰t¤°4(€€€€€€€€€€€€€€€€€€€Á¹Q¥µ•ÍÑ…µÀ¡Ñ…Í­l‰‘…Ñ•Ñ¥µ”‰t¤°4(€€€€€€€€€€€€€€€€€€€A…Ñ ¡Ñ…Í­l‰½ÕÑÁÕÑ}Á…Ñ ‰t¤°4(€€€€€€€€€€€€€€€€€€€ÑÉ…¹Í™½Éµ•È°4(€€€€€€€€€€€€€€€€€€€ÁÉ••‘¥¹}‘…åÌ°4(€€€€€€€€€€€€€€€€€€€¥¹ÁÕÑ}Ñ¥µ•é½¹”°4(€€€€€€€€€€€€€€€€€€€…¡•}‘¥È°4(€€€€€€€€€€€€€€€€€€€‘½Ý¹±½…‘}Í•ÑÑ¥¹Ì°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€É•µ•µ‰•É}Ý¥Ñ¡}ÍÑ…ÑÕÍ}™¥±” 4(€€€€€€€€€€€€€€€€€€€É•½É‘¥¹}¥°4(€€€€€€€€€€€€€€€€€€€ÍÑ…ÑÕÌ°4(€€€€€€€€€€€€€€€€€€€A…Ñ ¡Ñ…Í­l‰½ÕÑÁÕÑ}Á…Ñ ‰t¤°4(€€€€€€€€€€€€€€€€€€€ÍÑ…ÉÑ•‘}ÕÑŒõ‰…Ñ¡}ÍÑ…ÉÑ•‘}ÕÑŒ°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È¹…ÁÁ•¹¡É•½É‘¥¹}¥¤4(€€€€€€€€€€€€€€€¥˜½µÁ±•Ñ•€”µ…à Ä°É•½É‘¥¹}‰…Ñ¡}Í¥é”¤€ôô€À½È½µÁ±•Ñ•€ôô±•¸¡É•½É‘¥¹}Ñ…Í­Ì¤è4(€€€€€€€€€€€€€€€€€€€•±…ÁÍ•€ôÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤€´ÍÑ…ÉÑ•‘}É•½É‘Ì4(€€€€€€€€€€€€€€€€€€€É…Ñ”€ô½µÁ±•Ñ•€¼•±…ÁÍ•¥˜•±…ÁÍ•€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€€€€€•Ñ„€ô€¡±•¸¡É•½É‘¥¹}Ñ…Í­Ì¤€´½µÁ±•Ñ•¤€¼É…Ñ”¥˜É…Ñ”€ø€À•±Í”€À¸À4(€€€€€€€€€€€€€€€€€€€±½•È¹¥¹™¼ 4(€€€€€€€€€€€€€€€€€€€€€€€€‰I•½É‘¥¹œQè€”¸Å˜µ¥¸€ •Ì¼•Ì¤ˆ°4(€€€€€€€€€€€€€€€€€€€€€€€•Ñ„€¼€ØÀ°4(€€€€€€€€€€€€€€€€€€€€€€€½µÁ±•Ñ•°4(€€€€€€€€€€€€€€€€€€€€€€€±•¸¡É•½É‘¥¹}Ñ…Í­Ì¤°4(€€€€€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€€€€€É•Á½ÉÑ}É•½É‘¥¹}ÁÉ½É•ÍÌ¡½µÁ±•Ñ•°±•¸¡É•½É‘¥¹}Ñ…Í­Ì¤¤4(4(€€€€€€€¥˜½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•Èè4(€€€€€€€€€€€ÉÕ¹}µ…ÍÑ•ÉÑ…‰±•}‰…Ñ¡}ÕÁ‘…Ñ” 4(€€€€€€€€€€€€€€€…ÉÌ¹½¹™¥œ°4(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È°4(€€€€€€€€€€€€€€€ÍÑ•Á}¹…µ”ô‰ÍÑ•Á|Õ|É}Ý•…Ñ¡•É}‘½Ý¹±½…ˆ°4(€€€€€€€€€€€€€€€É•ÅÕ•ÍÑ}‘¥ÈõÁÉ½É•ÍÍ}Á…Ñ ¹Á…É•¹Ð€¼€‰µ…ÍÑ•É}ÕÁ‘…Ñ•}É•ÅÕ•ÍÑÌˆ°4(€€€€€€€€€€€€¤4(€€€€€€€€€€€½µÁ±•Ñ•‘}Í¥¹•}µ…ÍÑ•È¹±•…È ¤4(4(€€€€€€€ÉÕ¹}™¥¹¥Í¡•‘}…Ð€ô‘…Ñ•Ñ¥µ”¹¹½Ü¡ÑèõÑ¥µ•é½¹”¹ÕÑŒ¤4(€€€€€€€±¥¹•Ì€ôl4(€€€€€€€€€€€€ˆˆ°4(€€€€€€€€€€€€ˆôˆ€¨€ÜÈ°4(€€€€€€€€€€€€ˆ	%<µ<µQ=8€´´MQ@€Õ|È!=MQI]Q!HQIU8MU55Idˆ°4(€€€€€€€€€€€€ˆôˆ€¨€ÜÈ°4(€€€€€€€€€€€˜ˆIÕ¸ÍÑ…ÉÑ•€€¡UQ¤€èíÉÕ¹}ÍÑ…ÉÑ•‘}…Ðè•d´•´´•€• è•4è•Môˆ°4(€€€€€€€€€€€˜ˆIÕ¸™¥¹¥Í¡•€¡UQ¤€èíÉÕ¹}™¥¹¥Í¡•‘}…Ðè•d´•´´•€• è•4è•Môˆ°4(€€€€€€€€€€€˜ˆ±…ÁÍ•€€€€€€€€€€€€èíÉÕ¹}™¥¹¥Í¡•‘}…Ð€´ÉÕ¹}ÍÑ…ÉÑ•‘}…Ñôˆ°4(€€€€€€€€€€€€ˆˆ°4(€€€€€€€€€€€˜ˆ%¹ÁÕÐMX€€€€€€€€€€€€€€€€€€€€èí¥¹ÁÕÑ}ÍÙôˆ°4(€€€€€€€€€€€˜ˆ=ÕÑÁÕÐ™½±‘•È€€€€€€€€€€€€€€€€èí½ÕÑÁÕÑ}‘¥Éôˆ°4(€€€€€€€€€€€˜ˆQ½Ñ…°É•½É‘¥¹Ì¥¸¥¹ÁÕÐ€€€€èí±•¸¡É•½É‘¥¹Ì¥ôˆ°4(€€€€€€€€€€€˜ˆ±É•…‘äÁÉ½•ÍÍ•€¡Í­¥ÁÁ•¤€€èí±•¸¡¥¹‘¥•Í}‘½¹”¥ôˆ°4(€€€€€€€€€€€˜ˆMÕ•ÍÍ™Õ±±äÁÉ½•ÍÍ•€€€€€€€èí±•¸¡ÁÉ½•ÍÍ•‘}½¬¥ôˆ°4(€€€€€€€€€€€˜ˆ=ÕÐµ½˜µ‰½Õ¹‘Ì€¡9…8µ™¥±±•¤€€€èí±•¸¡ÁÉ½•ÍÍ•‘}½ÕÑ}½™}‰½Õ¹‘Ì¥ôˆ°4(€€€€€€€€€€€˜ˆUÁÍÑÉ•…´‘…Ñ„Õ¹…Ù…¥±…‰±”€€€€èí±•¸¡ÁÉ½•ÍÍ•‘}ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”¥ôˆ°4(€€€€€€€€€€€˜ˆ…¥±•€€€€€€€€€€€€€€€€€€€€€€€èí±•¸¡ÁÉ½•ÍÍ•‘}™…¥±•¥ôˆ°4(€€€€€€€€€€€€ˆôˆ€¨€ÜÈ°4(€€€€€€€t4(€€€€€€€É•Á½ÉÐ€ô€‰q¸ˆ¹©½¥¸¡±¥¹•Ì¤4(€€€€€€€ÁÉ¥¹Ð¡É•Á½ÉÐ¤4(€€€€€€€±½•È¹¥¹™¼ ‰IÕ¸ÍÕµµ…Éäéq¸•Ìˆ°É•Á½ÉÐ¤4(€€€€€€€¥˜µ…¹¥™•ÍÑ}Á…Ñ ¥Ì¹½Ð9½¹”…¹µ…¹¥™•ÍÐ¥Ì¹½Ð9½¹”è4(€€€€€€€€€€€™¥¹¥Í¡}ÍÑ•Á}µ…¹¥™•ÍÐ 4(€€€€€€€€€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ °4(€€€€€€€€€€€€€€€µ…¹¥™•ÍÐ°4(€€€€€€€€€€€€€€€€‰Á…ÉÑ¥…°ˆ¥˜ÁÉ½•ÍÍ•‘}™…¥±••±Í”€‰½µÁ±•Ñ”ˆ°4(€€€€€€€€€€€€€€€É•ÍÕ±Ðõì4(€€€€€€€€€€€€€€€€€€€€‰¥¹ÁÕÑ}É•½É‘¥¹Ìˆè±•¸¡É•½É‘¥¹Ì¤°4(€€€€€€€€€€€€€€€€€€€€‰Í­¥ÁÁ•‘}•á¥ÍÑ¥¹œˆè±•¸¡¥¹‘¥•Í}‘½¹”¤°4(€€€€€€€€€€€€€€€€€€€€‰ÁÉ½•ÍÍ•‘}½¬ˆè±•¸¡ÁÉ½•ÍÍ•‘}½¬¤°4(€€€€€€€€€€€€€€€€€€€€‰½ÕÑ}½™}‰½Õ¹‘Ìˆè±•¸¡ÁÉ½•ÍÍ•‘}½ÕÑ}½™}‰½Õ¹‘Ì¤°4(€€€€€€€€€€€€€€€€€€€€‰ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”ˆè±•¸¡ÁÉ½•ÍÍ•‘}ÕÁÍÑÉ•…µ}Õ¹…Ù…¥±…‰±”¤°4(€€€€€€€€€€€€€€€€€€€€‰™…¥±•ˆè±•¸¡ÁÉ½•ÍÍ•‘}™…¥±•¤°4(€€€€€€€€€€€€€€€€€€€€‰Ñ…Í­}¥¹‘•àˆè…ÉÌ¹Ñ…Í­}¥¹‘•à°4(€€€€€€€€€€€€€€€€€€€€‰Ñ…Í­}½Õ¹Ðˆè…ÉÌ¹Ñ…Í­}½Õ¹Ð°4(€€€€€€€€€€€€€€€ô°4(€€€€€€€€€€€€¤4(€€€€€€€É•ÑÕÉ¸€Ä¥˜ÁÉ½•ÍÍ•‘}™…¥±••±Í”€À4(€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè4(€€€€€€€¥˜±½•È¹¡…¹‘±•ÉÌè4(€€€€€€€€€€€±½•È¹•á•ÁÑ¥½¸ ‰MÑ•À€Õ|È™…¥±•è€•Ìˆ°•áŒ¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰II=HèMÑ•À€Õ|È™…¥±•èí•áôˆ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ¤4(€€€€€€€¥˜µ…¹¥™•ÍÑ}Á…Ñ ¥Ì¹½Ð9½¹”…¹µ…¹¥™•ÍÐ¥Ì¹½Ð9½¹”è4(€€€€€€€€€€€™¥¹¥Í¡}ÍÑ•Á}µ…¹¥™•ÍÐ 4(€€€€€€€€€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ °4(€€€€€€€€€€€€€€€µ…¹¥™•ÍÐ°4(€€€€€€€€€€€€€€€€‰™…¥±•ˆ°4(€€€€€€€€€€€€€€€•ÉÉ½ÈõÉ•ÁÈ¡•áŒ¤°4(€€€€€€€€€€€€¤4(€€€€€€€É•ÑÕÉ¸€Ä4(€€€™¥¹…±±äè4(€€€€€€€±½Í•}‘…Ñ…Í•ÑÌ ¤4(4(4)¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè4(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤4(
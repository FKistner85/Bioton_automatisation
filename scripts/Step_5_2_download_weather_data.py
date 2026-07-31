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
        for variable_folder, (abbr, nc_variable) in VARIABLES.items():
            values = np.full(len(times_utc), np.nan, dtype=float)
            for year, month in month_pairs:
                dataset = get_dataset(
                    variable_folder,
                    abbr,
                    year,
                    month,
                    cache_dir,
                    download_settings,
                )
                if dataset is None:
                    continue
                month_mask = np.array(
                    [
                        timestamp.year == year and timestamp.month == month
                        for timestamp in times_utc
                    ]
                )
                if not month_mask.any():
                    continue
                subset = extract_nearest_values(
                    dataset,
                    nc_variable,
                    x_3034,
                    y_3034,
                    times_utc[month_mask],
                )
                values[month_mask] = subset
            columns[variable_folder] = values

        frame = pd.DataFrame(columns)
        expected_hours = (preceding_days + 1) * 24
        if len(frame) != expected_hours:
            logger.warning(
                "[%s] Built %s rows, expected %s.",
                recording_id,
                len(frame),
                expected_hours,
            )
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        frame.to_csv(temporary, index=False)
        temporary.replace(output_path)
        return "ok"
    except Exception as exc:
        logger.error("[%s] FAILED: %r", recording_id, exc)
        return "failed"


def resolve_worker_count(
    section: dict[str, Any],
    key: str,
    max_key: str,
    default: int,
    default_max: int,
) -> tuple[int, int, int]:
    allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", "1") or "1")
    configured_raw = str(section.get(key, default)).strip()
    configured = allocated if configured_raw.lower() == "auto" else int(configured_raw)
    max_workers = int(section.get(max_key, default_max))
    workers = max(1, min(configured, allocated, max_workers))
    return workers, allocated, max_workers


def init_recording_worker(
    preceding_days: int,
    input_timezone: str,
    cache_dir: str,
    download_settings: dict[str, int],
    known_missing: list[tuple[str, int, int]],
) -> None:
    global _worker_transformer
    global _worker_preceding_days
    global _worker_input_timezone
    global _worker_cache_dir
    global _worker_download_settings
    global _known_missing
    _worker_transformer = Transformer.from_crs(INPUT_CRS, HOSTRADA_CRS, always_xy=True)
    _worker_preceding_days = preceding_days
    _worker_input_timezone = input_timezone
    _worker_cache_dir = Path(cache_dir)
    _worker_download_settings = download_settings
    _known_missing = set(known_missing)


def process_recording_worker(task: dict[str, Any]) -> tuple[str, str]:
    if (
        _worker_transformer is None
        or _worker_preceding_days is None
        or _worker_input_timezone is None
        or _worker_cache_dir is None
        or _worker_download_settings is None
    ):
        raise RuntimeError("Step 5_2 worker was not initialised.")
    recording_id = str(task["recording_id"])
    status = process_recording(
        recording_id,
        float(task["lat"]),
        float(task["lng"]),
        pd.Timestamp(task["datetime"]),
        Path(task["output_path"]),
        _worker_transformer,
        _worker_preceding_days,
        _worker_input_timezone,
        _worker_cache_dir,
        _worker_download_settings,
    )
    return recording_id, status


def load_input_recordings(csv_path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(csv_path, sep=";", low_memory=False)
        if len(frame.columns) == 1:
            frame = pd.read_csv(csv_path, low_memory=False)
    except Exception:
        frame = pd.read_csv(csv_path, low_memory=False)

    if "date" in frame.columns and "time" in frame.columns and "datetime" not in frame.columns:
        frame["datetime"] = frame["date"].astype(str) + " " + frame["time"].astype(str)
    if "dawn_chorus_id" in frame.columns and "id" not in frame.columns:
        frame = frame.rename(columns={"dawn_chorus_id": "id"})

    lower_to_original = {column.lower(): column for column in frame.columns}
    aliases = {
        "ID": ["id", "recording_id", "rec_id"],
        "lat": ["lat", "latitude"],
        "lng": ["lng", "lon", "long", "longitude"],
        "datetime": ["datetime", "date_time", "recorded_at", "timestamp"],
    }
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for canonical, candidates in aliases.items():
        for candidate in candidates:
            if candidate in lower_to_original:
                resolved[canonical] = lower_to_original[candidate]
                break
        else:
            missing.append(canonical)
    if missing:
        raise ValueError(f"Input CSV missing required column(s): {missing}.")

    logger.info(
        "Resolved CSV columns: %s",
        ", ".join(f"{key}='{value}'" for key, value in resolved.items()),
    )
    frame = frame[
        [resolved["ID"], resolved["lat"], resolved["lng"], resolved["datetime"]]
    ].copy()
    frame.columns = ["ID", "lat", "lng", "datetime"]
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce", utc=False)
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce")
    frame["lng"] = pd.to_numeric(frame["lng"], errors="coerce")
    before = len(frame)
    frame = frame.dropna(subset=["ID", "lat", "lng", "datetime"]).reset_index(drop=True)
    if len(frame) < before:
        logger.warning("Dropped %s rows with missing/invalid fields.", before - len(frame))
    frame["ID"] = pd.to_numeric(frame["ID"], errors="coerce").astype("Int64")
    frame = frame.dropna(subset=["ID"]).reset_index(drop=True)
    frame["ID"] = frame["ID"].astype("int64").astype(str)
    return frame


def safe_output_path(output_dir: Path, recording_id: str) -> Path:
    safe_id = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in recording_id
    )
    return output_dir / f"weather_{safe_id}.csv"


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_weather_inventory(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    compact_log = Path(
        config.get("weather_inventory", {}).get("compact_log", "")
    )
    if not compact_log.is_file() or compact_log.stat().st_size == 0:
        return {}
    try:
        inventory = pd.read_csv(compact_log, low_memory=False, dtype=str)
    except Exception as exc:
        logger.warning("Could not read weather inventory %s: %r", compact_log, exc)
        return {}
    if "dawn_chorus_id" not in inventory.columns:
        logger.warning(
            "Weather inventory %s has no dawn_chorus_id column; ignoring it.",
            compact_log,
        )
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for _, row in inventory.iterrows():
        dawn_id = str(row.get("dawn_chorus_id", "")).strip()
        if dawn_id:
            rows[dawn_id] = row.to_dict()
    return rows


def inventory_marks_weather_ok(
    inventory_row: dict[str, Any] | None,
) -> bool:
    if not inventory_row:
        return False
    exists = truthy(inventory_row.get("weather_exists", "false"))
    has_issues = truthy(
        inventory_row.get(
            "weather_has_issues",
            inventory_row.get("has_issues", "true"),
        )
    )
    return exists and not has_issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 5_2: Download and extract HOSTRADA weather data."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all recording outputs; cached NetCDF files are retained.",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="CSV containing IDs whose timestamp or coordinates changed.",
    )
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--task-count", type=int, default=1)
    parser.add_argument(
        "--verify-shards",
        action="store_true",
        help="Verify that every requested ID has a non-empty weather CSV.",
    )
    return parser.parse_args()


def recording_shard(recording_id: str, task_count: int) -> int:
    if task_count <= 1:
        return 0
    if recording_id.isdigit():
        return int(recording_id) % task_count
    digest = hashlib.sha256(recording_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % task_count


def select_recordings(
    recordings: pd.DataFrame,
    requested_ids: set[str],
    *,
    ids_file_supplied: bool,
    task_index: int,
    task_count: int,
) -> pd.DataFrame:
    selected = recordings
    if ids_file_supplied:
        selected = selected[selected["ID"].isin(requested_ids)]
    if task_count > 1:
        selected = selected[
            selected["ID"].map(
                lambda recording_id: recording_shard(recording_id, task_count)
                == task_index
            )
        ]
    return selected.reset_index(drop=True)


def verify_requested_outputs(
    output_dir: Path,
    requested_ids: set[str],
) -> tuple[list[str], list[str]]:
    complete: list[str] = []
    missing: list[str] = []
    for recording_id in sorted(
        requested_ids,
        key=lambda value: int(value) if value.isdigit() else value,
    ):
        output = safe_output_path(output_dir, recording_id)
        if output.is_file() and output.stat().st_size > 0:
            complete.append(recording_id)
        else:
            missing.append(recording_id)
    return complete, missing


def close_datasets() -> None:
    for dataset in _global_datasets.values():
        if dataset is not None:
            try:
                dataset.close()
            except Exception:
                pass


def main() -> int:
    args = parse_args()
    run_started_at = datetime.now(tz=timezone.utc)
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        section = config["weather_download"]
        input_csv = Path(section.get("input_csv") or config["dawn_chorus_csv"])
        output_dir = Path(section["output_dir"])
        cache_dir = Path(section["cache_dir"])
        log_file = Path(section.get("log_file", output_dir / "_run_log.txt"))
        preceding_days = int(section.get("preceding_days", DEFAULT_PRECEDING_DAYS))
        input_timezone = str(section.get("input_timezone", DEFAULT_INPUT_TIMEZONE))
        download_settings = {
            "max_download_retries": int(
                section.get("max_download_retries", DEFAULT_MAX_DOWNLOAD_RETRIES)
            ),
            "retry_backoff_seconds": int(
                section.get("retry_backoff_seconds", DEFAULT_RETRY_BACKOFF_SECONDS)
            ),
            "http_timeout_seconds": int(
                section.get("http_timeout_seconds", DEFAULT_HTTP_TIMEOUT_SECONDS)
            ),
            "request_chunk_bytes": int(
                section.get("request_chunk_bytes", DEFAULT_REQUEST_CHUNK_BYTES)
            ),
        }
        cache_workers, allocated_cpus, cache_max_workers = resolve_worker_count(
            section,
            "cache_download_workers",
            "cache_download_max_workers",
            default=4,
            default_max=16,
        )
        recording_workers, _, recording_max_workers = resolve_worker_count(
            section,
            "recording_workers",
            "recording_max_workers",
            default=1,
            default_max=16,
        )
        recording_batch_size = int(section.get("recording_batch_size", 200))
        master_update_batch_size = int(section.get("master_update_batch_size", 500))
        if args.task_count < 1:
            raise ValueError("--task-count must be at least 1.")
        if args.task_index < 0 or args.task_index >= args.task_count:
            raise ValueError("--task-index must satisfy 0 <= index < task-count.")

        output_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        requested_ids = read_ids_file(args.ids_file)
        if args.verify_shards:
            available_ids = set(load_input_recordings(input_csv)["ID"])
            verification_ids = (
                requested_ids & available_ids
                if args.ids_file is not None
                else available_ids
            )
            complete, missing = verify_requested_outputs(
                output_dir,
                verification_ids,
            )
            print(f"Requested weather outputs : {len(verification_ids):,}")
            print(f"Complete weather outputs  : {len(complete):,}")
            print(f"Missing weather outputs   : {len(missing):,}")
            if missing:
                print(
                    "Missing IDs (first 20)      : " + ", ".join(missing[:20]),
                    file=sys.stderr,
                )
                return 1
            return 0
        if args.task_count > 1:
            log_file = log_file.with_name(
                f"{log_file.stem}_shard_{args.task_index:03d}{log_file.suffix}"
            )
        setup_logger(log_file)
        logger.info("Step 5_2 started.")
        logger.info("Input CSV        : %s", input_csv)
        logger.info("Output directory : %s", output_dir)
        logger.info("Cache directory  : %s", cache_dir)
        logger.info("Force mode       : %s", args.force)
        logger.info("Allocated CPUs    : %s", allocated_cpus)
        logger.info(
            "Cache workers     : %s (max %s)",
            cache_workers,
            cache_max_workers,
        )
        logger.info(
            "Recording workers : %s (max %s)",
            recording_workers,
            recording_max_workers,
        )
        logger.info(
            "Slurm shard       : %s/%s",
            args.task_index + 1,
            args.task_count,
        )

        recordings = load_input_recordings(input_csv)
        recordings = select_recordings(
            recordings,
            requested_ids,
            ids_file_supplied=args.ids_file is not None,
            task_index=args.task_index,
            task_count=args.task_count,
        )
        weather_inventory = load_weather_inventory(config)
        batch_status_dir = output_dir / "_recording_status"
        inventory_compact_log = Path(
            config.get("weather_inventory", {}).get("compact_log", "")
        )
        manifest_inputs = [input_csv]
        if inventory_compact_log.is_file():
            manifest_inputs.append(inventory_compact_log)
        manifest_path, manifest = start_step_manifest(
            config,
            "step_5_2_download_weather_data",
            config_path=args.config,
            inputs=manifest_inputs,
            outputs=[output_dir, cache_dir, log_file],
            parameters={
                "preceding_days": preceding_days,
                "input_timezone": input_timezone,
                "cache_workers": cache_workers,
                "recording_workers": recording_workers,
                "weather_inventory_used": bool(weather_inventory),
                "force": args.force,
                "requested_id_count": len(requested_ids),
            },
            force=args.force,
            batch_count=len(recordings),
        )
        indices_to_process: list[int] = []
        indices_done: list[int] = []
        inventory_used = bool(weather_inventory)
        for index, row in recordings.iterrows():
            recording_id = str(row["ID"])
            output = safe_output_path(output_dir, str(row["ID"]))
            inventory_row = weather_inventory.get(recording_id)
            if (
                not args.force
                and recording_id not in requested_ids
                and inventory_used
                and inventory_marks_weather_ok(inventory_row)
            ):
                indices_done.append(index)
                write_batch_status(
                    batch_status_dir,
                    recording_id,
                    "skipped",
                    outputs=[output],
                    result={"reason": "weather_inventory_ok"},
                )
            elif (
                not args.force
                and recording_id not in requested_ids
                and not inventory_used
                and output.exists()
                and output.stat().st_size > 0
            ):
                indices_done.append(index)
                write_batch_status(
                    batch_status_dir,
                    recording_id,
                    "skipped",
                    outputs=[output],
                    result={
                        "reason": "existing_nonempty_weather_csv_without_inventory"
                    },
                )
            else:
                indices_to_process.append(index)

        logger.info("Total recordings in input CSV : %s", len(recordings))
        logger.info("Weather inventory rows loaded : %s", len(weather_inventory))
        logger.info("Already processed (skipping)  : %s", len(indices_done))
        logger.info("New / forced (to process)     : %s", len(indices_to_process))

        needed: set[tuple[str, str, int, int]] = set()
        for index in indices_to_process:
            row = recordings.iloc[index]
            try:
                times = recording_time_window_utc(
                    row["datetime"], preceding_days, input_timezone
                )
                for year, month in months_spanning(times):
                    for variable_folder, (abbr, _nc_variable) in VARIABLES.items():
                        needed.add((variable_folder, abbr, year, month))
            except Exception:
                pass

        logger.info(
            "Pre-downloading %s unique monthly files with %s workers...",
            len(needed),
            cache_workers,
        )
        warmup_started = time.monotonic()
        needed_list = sorted(needed)
        with ThreadPoolExecutor(max_workers=max(1, cache_workers)) as executor:
            futures = {
                executor.submit(
                    ensure_cached,
                    variable_folder,
                    abbr,
                    year,
                    month,
                    cache_dir,
                    download_settings,
                ): (variable_folder, year, month)
                for variable_folder, abbr, year, month in needed_list
            }
            for completed, future in enumerate(
                tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="Cache warm-up",
                    unit="file",
                ),
                start=1,
            ):
                future.result()
                elapsed = time.monotonic() - warmup_started
                rate = completed / elapsed if elapsed > 0 else 0.0
                eta = (len(futures) - completed) / rate if rate > 0 else 0.0
                if completed % max(1, cache_workers) == 0:
                    logger.info(
                        "Cache warm-up ETA: %.1f min (%s/%s)",
                        eta / 60,
                        completed,
                        len(futures),
                    )

        processed_ok: list[str] = []
        processed_out_of_bounds: list[str] = []
        processed_failed: list[str] = []

        recording_tasks = []
        for index in indices_to_process:
            row = recordings.iloc[index]
            recording_id = str(row["ID"])
            recording_tasks.append(
                {
                    "recording_id": recording_id,
                    "lat": float(row["lat"]),
                    "lng": float(row["lng"]),
                    "datetime": pd.Timestamp(row["datetime"]).isoformat(),
                    "output_path": str(safe_output_path(output_dir, recording_id)),
                }
            )

        def remember(recording_id: str, status: str) -> None:
            if status == "ok":
                processed_ok.append(recording_id)
            elif status == "out_of_bounds":
                processed_out_of_bounds.append(recording_id)
            else:
                processed_failed.append(recording_id)

        def remember_with_status_file(recording_id: str, status: str, output_path: Path, started_utc: str | None = None) -> None:
            remember(recording_id, status)
            if status in {"ok", "out_of_bounds"}:
                batch_status = "complete"
            else:
                batch_status = "failed"
            write_batch_status(
                batch_status_dir,
                recording_id,
                batch_status,
                outputs=[output_path],
                result={"recording_status": status},
                error="" if batch_status == "complete" else f"recording_status={status}",
                started_utc=started_utc,
            )

        started_records = time.monotonic()
        completed_since_master: list[str] = []
        progress_name = (
            f"progress_shard_{args.task_index:03d}.json"
            if args.task_count > 1
            else "progress.json"
        )
        progress_path = (
            processed_root_from_config(config)
            / "step_5_2_weather_download"
            / progress_name
        )

        def report_recording_progress(completed: int, total: int) -> None:
            write_progress_snapshot(
                progress_path,
                step_name="step_5_2_weather_download",
                total_batches=total,
                completed_batches=completed,
                succeeded=len(processed_ok),
                failed=len(processed_failed),
                skipped=len(indices_done),
                started_monotonic=started_records,
                extra={
                    "recording_workers": recording_workers,
                    "master_update_batch_size": master_update_batch_size,
                },
            )
            if (
                master_update_batch_size > 0
                and len(completed_since_master) >= master_update_batch_size
            ):
                run_mastertable_batch_update(
                    args.config,
                    completed_since_master,
                    step_name="step_5_2_weather_download",
                    request_dir=progress_path.parent / "master_update_requests",
                )
                completed_since_master.clear()

        if recording_workers > 1 and recording_tasks:
            output_by_id = {
                str(task["recording_id"]): Path(task["output_path"])
                for task in recording_tasks
            }
            with ProcessPoolExecutor(
                max_workers=recording_workers,
                initializer=init_recording_worker,
                initargs=(
                    preceding_days,
                    input_timezone,
                    str(cache_dir),
                    download_settings,
                    list(_known_missing),
                ),
            ) as executor:
                futures = [
                    executor.submit(process_recording_worker, task)
                    for task in recording_tasks
                ]
                for completed, future in enumerate(
                    tqdm(
                        as_completed(futures),
                        total=len(futures),
                        desc="Recordings",
                        unit="rec",
                    ),
                    start=1,
                ):
                    recording_id, status = future.result()
                    remember_with_status_file(
                        recording_id,
                        status,
                        output_by_id[recording_id],
                    )
                    completed_since_master.append(recording_id)
                    if completed % max(1, recording_batch_size) == 0 or completed == len(futures):
                        elapsed = time.monotonic() - started_records
                        rate = completed / elapsed if elapsed > 0 else 0.0
                        eta = (len(futures) - completed) / rate if rate > 0 else 0.0
                        logger.info(
                            "Recording ETA: %.1f min (%s/%s)",
                            eta / 60,
                            completed,
                            len(futures),
                        )
                        report_recording_progress(completed, len(futures))
        else:
            transformer = Transformer.from_crs(INPUT_CRS, HOSTRADA_CRS, always_xy=True)
            progress = tqdm(
                recording_tasks,
                total=len(recording_tasks),
                desc="Recordings",
                unit="rec",
            )
            for completed, task in enumerate(progress, start=1):
                recording_id = str(task["recording_id"])
                batch_started_utc = utc_now_iso()
                progress.set_postfix_str(recording_id[:24])
                status = process_recording(
                    recording_id,
                    float(task["lat"]),
                    float(task["lng"]),
                    pd.Timestamp(task["datetime"]),
                    Path(task["output_path"]),
                    transformer,
                    preceding_days,
                    input_timezone,
                    cache_dir,
                    download_settings,
                )
                remember_with_status_file(
                    recording_id,
                    status,
                    Path(task["output_path"]),
                    started_utc=batch_started_utc,
                )
                completed_since_master.append(recording_id)
                if completed % max(1, recording_batch_size) == 0 or completed == len(recording_tasks):
                    elapsed = time.monotonic() - started_records
                    rate = completed / elapsed if elapsed > 0 else 0.0
                    eta = (len(recording_tasks) - completed) / rate if rate > 0 else 0.0
                    logger.info(
                        "Recording ETA: %.1f min (%s/%s)",
                        eta / 60,
                        completed,
                        len(recording_tasks),
                    )
                    report_recording_progress(completed, len(recording_tasks))

        if completed_since_master:
            run_mastertable_batch_update(
                args.config,
                completed_since_master,
                step_name="step_5_2_weather_download",
                request_dir=progress_path.parent / "master_update_requests",
            )
            completed_since_master.clear()

        run_finished_at = datetime.now(tz=timezone.utc)
        lines = [
            "",
            "=" * 72,
            " BIO-O-TON -- STEP 5_2 HOSTRADA WEATHER DATA RUN SUMMARY",
            "=" * 72,
            f" Run started  (UTC) : {run_started_at:%Y-%m-%d %H:%M:%S}",
            f" Run finished (UTC) : {run_finished_at:%Y-%m-%d %H:%M:%S}",
            f" Elapsed            : {run_finished_at - run_started_at}",
            "",
            f" Input CSV                    : {input_csv}",
            f" Output folder                : {output_dir}",
            f" Total recordings in input    : {len(recordings)}",
            f" Already processed (skipped)  : {len(indices_done)}",
            f" Successfully processed       : {len(processed_ok)}",
            f" Out-of-bounds (NaN-filled)   : {len(processed_out_of_bounds)}",
            f" Failed                       : {len(processed_failed)}",
            "=" * 72,
        ]
        report = "\n".join(lines)
        print(report)
        logger.info("Run summary:\n%s", report)
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "partial" if processed_failed else "complete",
                result={
                    "input_recordings": len(recordings),
                    "skipped_existing": len(indices_done),
                    "processed_ok": len(processed_ok),
                    "out_of_bounds": len(processed_out_of_bounds),
                    "failed": len(processed_failed),
                    "task_index": args.task_index,
                    "task_count": args.task_count,
                },
            )
        return 1 if processed_failed else 0
    except Exception as exc:
        if logger.handlers:
            logger.exception("Step 5_2 failed: %s", exc)
        else:
            print(f"ERROR: Step 5_2 failed: {exc}", file=sys.stderr)
        if manifest_path is not None and manifest is not None:
            finish_step_manifest(
                manifest_path,
                manifest,
                "failed",
                error=repr(exc),
            )
        return 1
    finally:
        close_datasets()


if __name__ == "__main__":
    raise SystemExit(main())

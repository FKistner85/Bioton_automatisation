#!/usr/bin/env python3
"""Step 5_1: Inventory and sanity-check HOSTRADA weather CSV files.

This step scans the configured weather output directory for ``weather_*.csv``
files, validates each file and writes one detailed file-level log plus one
compact ID-level log. Step 5_2 can use the compact log to reprocess only
missing or problematic recordings.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from common import atomic_write_csv, atomic_write_json, read_ids_file, utc_now_iso


FILENAME_RE = re.compile(r"^weather_(?P<id>.+)\.csv$", re.IGNORECASE)

DETAIL_COLUMNS = [
    "dawn_chorus_id",
    "record_type",
    "filename",
    "path",
    "size_bytes",
    "mtime_ns",
    "weather_exists",
    "read_ok",
    "row_count",
    "expected_rows",
    "required_columns_present",
    "missing_required_columns",
    "datetime_parse_ok",
    "datetime_interval_ok",
    "expected_time_window_ok",
    "first_datetime",
    "last_datetime",
    "expected_first_datetime",
    "expected_last_datetime",
    "max_nan_fraction",
    "observed_max_nan_fraction",
    "value_ranges_ok",
    "has_issues",
    "issues",
]

COMPACT_COLUMNS = [
    "dawn_chorus_id",
    "weather_exists",
    "weather_has_issues",
    "has_issues",
    "issue_codes",
    "row_count",
    "path",
    "size_bytes",
    "mtime_ns",
]


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)
    if not isinstance(config.get("weather_inventory"), dict):
        raise KeyError("Missing 'weather_inventory' section in config.")
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory and sanity-check HOSTRADA weather CSV files."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Revalidate every weather CSV instead of reusing clean unchanged rows.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Create a fast file list without reading legacy weather CSV content.",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="Only sanity-check these IDs while retaining prior validated rows.",
    )
    return parser.parse_args()


def weather_id_from_path(path: Path) -> str:
    match = FILENAME_RE.match(path.name)
    return match.group("id") if match else ""


def normalise_id(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "none", "<na>"} else text
    return str(int(numeric))


def read_metadata_ids(
    metadata_csv: Path,
    id_column: str,
    datetime_column: str,
) -> pd.DataFrame:
    if not metadata_csv.is_file():
        return pd.DataFrame(columns=["dawn_chorus_id", "metadata_datetime"])
    metadata = pd.read_csv(metadata_csv, low_memory=False, encoding="utf-8-sig")
    if id_column not in metadata.columns:
        raise ValueError(
            f"Metadata ID column '{id_column}' not found in {metadata_csv}."
        )
    result = pd.DataFrame()
    result["dawn_chorus_id"] = metadata[id_column].map(normalise_id)
    if datetime_column in metadata.columns:
        result["metadata_datetime"] = metadata[datetime_column]
    else:
        result["metadata_datetime"] = pd.NA
    result = result[result["dawn_chorus_id"] != ""]
    return result.drop_duplicates("dawn_chorus_id", keep="first")


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def issue_join(issues: list[str]) -> str:
    return "|".join(dict.fromkeys(issue for issue in issues if issue))


def expected_local_window(
    metadata_datetime: Any,
    preceding_days: int,
    input_timezone: str,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if pd.isna(metadata_datetime):
        return None, None
    timestamp = pd.Timestamp(metadata_datetime)
    if pd.isna(timestamp):
        return None, None
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(
            input_timezone,
            ambiguous=True,
            nonexistent="shift_forward",
        )
    else:
        timestamp = timestamp.tz_convert(input_timezone)
    start = timestamp.normalize() - pd.Timedelta(days=preceding_days)
    end = timestamp.normalize() + pd.Timedelta(hours=23)
    return start.tz_localize(None), end.tz_localize(None)


def check_numeric_ranges(
    frame: pd.DataFrame,
    settings: dict[str, Any],
) -> bool:
    ranges = {
        "air_temperature_mean": (
            float(settings.get("temperature_min_C", -60)),
            float(settings.get("temperature_max_C", 60)),
        ),
        "humidity_relative": (
            float(settings.get("humidity_min_percent", 0)),
            float(settings.get("humidity_max_percent", 100)),
        ),
    }
    ok = True
    for column, (minimum, maximum) in ranges.items():
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        if (values < minimum).any() or (values > maximum).any():
            ok = False
    return ok


def inspect_weather_csv(
    path: Path,
    metadata_datetime: Any,
    settings: dict[str, Any],
    download_settings: dict[str, Any],
) -> dict[str, Any]:
    dawn_id = weather_id_from_path(path)
    issues: list[str] = []
    if not dawn_id:
        issues.append("filename_does_not_match_weather_id_pattern")
    stat = path.stat()
    if stat.st_size == 0:
        return {
            "dawn_chorus_id": dawn_id,
            "record_type": "file",
            "filename": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "weather_exists": True,
            "read_ok": False,
            "row_count": 0,
            "expected_rows": int(settings.get("expected_rows", 264)),
            "required_columns_present": False,
            "missing_required_columns": "",
            "datetime_parse_ok": False,
            "datetime_interval_ok": False,
            "expected_time_window_ok": False,
            "first_datetime": "",
            "last_datetime": "",
            "expected_first_datetime": "",
            "expected_last_datetime": "",
            "max_nan_fraction": float(settings.get("max_nan_fraction", 0.0)),
            "observed_max_nan_fraction": 1.0,
            "value_ranges_ok": False,
            "has_issues": True,
            "issues": issue_join([*issues, "empty_file"]),
        }

    required_columns = [str(column) for column in settings.get("required_columns", [])]
    expected_rows = int(settings.get("expected_rows", 264))
    expected_interval_seconds = int(settings.get("expected_interval_seconds", 3600))
    max_nan_fraction = float(settings.get("max_nan_fraction", 0.0))
    preceding_days = int(download_settings.get("preceding_days", 10))
    input_timezone = str(download_settings.get("input_timezone", "Europe/Berlin"))

    read_ok = False
    row_count = 0
    required_present = False
    missing_required_columns: list[str] = []
    datetime_parse_ok = False
    datetime_interval_ok = False
    expected_time_window_ok = False
    first_datetime = ""
    last_datetime = ""
    expected_first_datetime = ""
    expected_last_datetime = ""
    observed_max_nan_fraction = math.nan
    value_ranges_ok = False

    try:
        frame = pd.read_csv(path, low_memory=False)
        read_ok = True
        row_count = len(frame)
        if row_count != expected_rows:
            issues.append("unexpected_row_count")

        missing_required_columns = [
            column for column in required_columns if column not in frame.columns
        ]
        required_present = not missing_required_columns
        if missing_required_columns:
            issues.append("missing_required_column")

        available_required = [
            column for column in required_columns if column in frame.columns
        ]
        if available_required:
            fractions = frame[available_required].isna().mean()
            observed_max_nan_fraction = float(fractions.max())
            if observed_max_nan_fraction > max_nan_fraction:
                issues.append("missing_value")
        else:
            observed_max_nan_fraction = 1.0

        if "datetime" in frame.columns:
            parsed = pd.to_datetime(frame["datetime"], errors="coerce")
            datetime_parse_ok = not parsed.isna().any()
            if not datetime_parse_ok:
                issues.append("unparseable_datetime")
            elif not parsed.empty:
                sorted_dt = parsed.sort_values().reset_index(drop=True)
                first_datetime = sorted_dt.iloc[0].isoformat()
                last_datetime = sorted_dt.iloc[-1].isoformat()
                if parsed.duplicated().any():
                    issues.append("duplicate_datetime")
                deltas = sorted_dt.diff().dropna().dt.total_seconds()
                datetime_interval_ok = bool(
                    deltas.empty or (deltas == expected_interval_seconds).all()
                )
                if not datetime_interval_ok:
                    issues.append("unexpected_time_interval")

                expected_first, expected_last = expected_local_window(
                    metadata_datetime,
                    preceding_days,
                    input_timezone,
                )
                if expected_first is not None and expected_last is not None:
                    expected_first_datetime = expected_first.isoformat()
                    expected_last_datetime = expected_last.isoformat()
                    expected_time_window_ok = bool(
                        sorted_dt.iloc[0] == expected_first
                        and sorted_dt.iloc[-1] == expected_last
                    )
                    if not expected_time_window_ok:
                        issues.append("unexpected_time_window")
                else:
                    expected_time_window_ok = True
        else:
            issues.append("missing_datetime_column")

        value_ranges_ok = check_numeric_ranges(frame, settings)
        if not value_ranges_ok:
            issues.append("implausible_value")

    except Exception as exc:
        issues.append(f"read_error:{type(exc).__name__}")

    return {
        "dawn_chorus_id": dawn_id,
        "record_type": "file",
        "filename": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "weather_exists": True,
        "read_ok": read_ok,
        "row_count": row_count,
        "expected_rows": expected_rows,
        "required_columns_present": required_present,
        "missing_required_columns": "|".join(missing_required_columns),
        "datetime_parse_ok": datetime_parse_ok,
        "datetime_interval_ok": datetime_interval_ok,
        "expected_time_window_ok": expected_time_window_ok,
        "first_datetime": first_datetime,
        "last_datetime": last_datetime,
        "expected_first_datetime": expected_first_datetime,
        "expected_last_datetime": expected_last_datetime,
        "max_nan_fraction": max_nan_fraction,
        "observed_max_nan_fraction": observed_max_nan_fraction,
        "value_ranges_ok": value_ranges_ok,
        "has_issues": bool(issues),
        "issues": issue_join(issues),
    }


def missing_row(dawn_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "dawn_chorus_id": dawn_id,
        "record_type": "expected_missing",
        "filename": "",
        "path": "",
        "size_bytes": "",
        "mtime_ns": "",
        "weather_exists": False,
        "read_ok": False,
        "row_count": 0,
        "expected_rows": int(settings.get("expected_rows", 264)),
        "required_columns_present": False,
        "missing_required_columns": "|".join(settings.get("required_columns", [])),
        "datetime_parse_ok": False,
        "datetime_interval_ok": False,
        "expected_time_window_ok": False,
        "first_datetime": "",
        "last_datetime": "",
        "expected_first_datetime": "",
        "expected_last_datetime": "",
        "max_nan_fraction": float(settings.get("max_nan_fraction", 0.0)),
        "observed_max_nan_fraction": "",
        "value_ranges_ok": False,
        "has_issues": True,
        "issues": "missing_file",
    }


def compact_from_detail(detail: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dawn_id, group in detail.groupby("dawn_chorus_id", sort=False):
        exists = group["weather_exists"].astype(str).str.lower().eq("true").any()
        has_issues = group["has_issues"].astype(str).str.lower().eq("true").any()
        issue_codes: list[str] = []
        for value in group["issues"]:
            issue_codes.extend(
                token.strip()
                for token in str(value).split("|")
                if token.strip() and token.strip().lower() != "nan"
            )
        file_rows = group[group["record_type"].astype(str).eq("file")]
        selected = file_rows.iloc[0] if not file_rows.empty else group.iloc[0]
        rows.append(
            {
                "dawn_chorus_id": dawn_id,
                "weather_exists": bool_text(bool(exists)),
                "weather_has_issues": bool_text(bool(has_issues)),
                "has_issues": bool_text(bool(has_issues)),
                "issue_codes": issue_join(issue_codes),
                "row_count": selected.get("row_count", ""),
                "path": selected.get("path", ""),
                "size_bytes": selected.get("size_bytes", ""),
                "mtime_ns": selected.get("mtime_ns", ""),
            }
        )
    return pd.DataFrame(rows, columns=COMPACT_COLUMNS)


def read_previous_detail(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    frame = pd.read_csv(
        path,
        low_memory=False,
        encoding="utf-8-sig",
        dtype="string",
    )
    if "path" not in frame.columns:
        return {}
    return {
        str(row["path"]): row.to_dict()
        for _, row in frame.iterrows()
        if str(row.get("path", "")).strip()
    }


def expected_window_strings(
    metadata_datetime: Any,
    download_settings: dict[str, Any],
) -> tuple[str, str]:
    first, last = expected_local_window(
        metadata_datetime,
        int(download_settings.get("preceding_days", 10)),
        str(download_settings.get("input_timezone", "Europe/Berlin")),
    )
    return (
        first.isoformat() if first is not None else "",
        last.isoformat() if last is not None else "",
    )


def previous_row_is_reusable(
    previous: dict[str, Any] | None,
    path: Path,
    metadata_datetime: Any,
    download_settings: dict[str, Any],
    force: bool,
) -> bool:
    if force or previous is None:
        return False
    stat = path.stat()
    if str(previous.get("size_bytes", "")) != str(stat.st_size):
        return False
    if str(previous.get("mtime_ns", "")) != str(stat.st_mtime_ns):
        return False
    if str(previous.get("has_issues", "")).strip().lower() != "false":
        return False
    expected_first, expected_last = expected_window_strings(
        metadata_datetime,
        download_settings,
    )
    old_first = str(previous.get("expected_first_datetime", "")).strip()
    old_last = str(previous.get("expected_last_datetime", "")).strip()
    old_first = "" if old_first.lower() == "nan" else old_first
    old_last = "" if old_last.lower() == "nan" else old_last
    return old_first == expected_first and old_last == expected_last


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    try:
        config = load_config(args.config)
        settings = config["weather_inventory"]
        download_settings = config.get("weather_download", {})

        directory = Path(settings["directory"])
        filename_glob = str(settings.get("filename_glob", "weather_*.csv"))
        metadata_csv = Path(settings.get("metadata_csv", ""))
        metadata = read_metadata_ids(
            metadata_csv,
            str(settings.get("metadata_id_column", "id")),
            str(settings.get("metadata_datetime_column", "datetime")),
        )
        metadata_by_id = dict(
            zip(metadata["dawn_chorus_id"], metadata["metadata_datetime"])
        )

        if not directory.is_dir():
            raise NotADirectoryError(f"Weather directory not found: {directory}")

        files = sorted(path for path in directory.glob(filename_glob) if path.is_file())
        discovered_ids = {weather_id_from_path(path) for path in files if weather_id_from_path(path)}
        expected_ids = set(metadata["dawn_chorus_id"].astype(str))
        detailed_log = Path(settings["detailed_log"])
        compact_log = Path(settings["compact_log"])
        state_file = Path(settings["state_file"])
        file_list_log = Path(
            settings.get("file_list_log", detailed_log.parent / "weather_file_list.csv")
        )
        missing_ids_log = Path(
            settings.get("missing_ids_log", detailed_log.parent / "weather_missing_ids.csv")
        )
        if args.list_only:
            file_rows = []
            for path in files:
                stat = path.stat()
                file_rows.append({
                    "dawn_chorus_id": weather_id_from_path(path),
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                })
            atomic_write_csv(
                pd.DataFrame(
                    file_rows,
                    columns=[
                        "dawn_chorus_id",
                        "filename",
                        "path",
                        "size_bytes",
                        "mtime_ns",
                    ],
                ),
                file_list_log,
            )
            missing_ids = sorted(
                expected_ids - discovered_ids,
                key=lambda value: int(value) if value.isdigit() else value,
            )
            atomic_write_csv(
                pd.DataFrame({"dawn_chorus_id": missing_ids}),
                missing_ids_log,
            )
            atomic_write_json(state_file, {
                "mode": "list_only",
                "directory": str(directory),
                "weather_files_found": len(file_rows),
                "file_list_log": str(file_list_log),
                "missing_weather_ids": len(missing_ids),
                "missing_ids_log": str(missing_ids_log),
            })
            print(f"Fast weather file list rows: {len(file_rows):,}")
            print(f"Missing weather IDs        : {len(missing_ids):,}")
            print(f"File list                  : {file_list_log}")
            print(f"Missing IDs                : {missing_ids_log}")
            return 0
        previous_by_path = read_previous_detail(detailed_log)
        requested_ids = read_ids_file(args.ids_file)

        allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", "1") or "1")
        configured_workers = int(settings.get("workers", allocated))
        workers = max(1, min(configured_workers, allocated))

        rows: list[dict[str, Any]] = []
        reused_rows: list[dict[str, Any]] = []
        files_to_check: list[Path] = []
        for path in files:
            dawn_id = weather_id_from_path(path)
            previous = previous_by_path.get(str(path))
            if args.ids_file is not None and dawn_id not in requested_ids:
                if previous is not None:
                    reused_rows.append(previous)
                continue
            if previous_row_is_reusable(
                previous,
                path,
                metadata_by_id.get(dawn_id, pd.NA),
                download_settings,
                args.force,
            ):
                reused_rows.append(previous)
            else:
                files_to_check.append(path)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    inspect_weather_csv,
                    path,
                    metadata_by_id.get(weather_id_from_path(path), pd.NA),
                    settings,
                    download_settings,
                ): path
                for path in files_to_check
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                if completed % max(1, workers * 20) == 0:
                    elapsed = time.monotonic() - started
                    rate = completed / elapsed if elapsed > 0 else 0.0
                    eta = (len(futures) - completed) / rate if rate > 0 else 0.0
                    print(
                        f"Weather inventory ETA: {eta / 60:.1f} min "
                        f"({completed}/{len(futures)})"
                    )

        rows.extend(reused_rows)
        missing_ids = expected_ids - discovered_ids
        if args.ids_file is not None:
            missing_ids &= requested_ids
        for dawn_id in sorted(missing_ids, key=lambda value: int(value) if value.isdigit() else value):
            rows.append(missing_row(dawn_id, settings))

        detail = pd.DataFrame(rows, columns=DETAIL_COLUMNS)
        detail = detail.sort_values(
            ["dawn_chorus_id", "record_type", "filename"],
            key=lambda series: series.astype("string").fillna(""),
        )
        compact = compact_from_detail(detail)

        atomic_write_csv(detail, detailed_log)
        atomic_write_csv(compact, compact_log)
        atomic_write_json(
            state_file,
            {
                "schema_version": "2026-07-23-weather-inventory-v1",
                "finished_utc": utc_now_iso(),
                "directory": str(directory),
                "metadata_csv": str(metadata_csv),
                "weather_files_found": int(len(files)),
                "weather_files_reused": int(len(reused_rows)),
                "weather_files_revalidated": int(len(files_to_check)),
                "metadata_ids": int(len(expected_ids)),
                "ids_missing_weather_file": int((compact["weather_exists"].astype(str).str.lower() != "true").sum()),
                "ids_with_issues": int((compact["weather_has_issues"].astype(str).str.lower() == "true").sum()),
                "detailed_log": str(detailed_log),
                "compact_log": str(compact_log),
            },
        )

        print(f"Weather files found       : {len(files):,}")
        print(f"Clean files reused        : {len(reused_rows):,}")
        print(f"Files revalidated         : {len(files_to_check):,}")
        print(f"Metadata IDs              : {len(expected_ids):,}")
        print(
            "IDs missing weather file  : "
            f"{(compact['weather_exists'].astype(str).str.lower() != 'true').sum():,}"
        )
        print(
            "IDs with issues           : "
            f"{(compact['weather_has_issues'].astype(str).str.lower() == 'true').sum():,}"
        )
        print(f"Detailed log              : {detailed_log}")
        print(f"Compact log               : {compact_log}")
        print(f"State file                : {state_file}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 5_1 weather inventory: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

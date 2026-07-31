#!/usr/bin/env python3
"""Step 1: Extract/upsert clean Dawn Chorus metadata and source fingerprints.

Configuration keys used:
    dawn_chorus_csv
    status_dir

Outputs:
    <status_dir>/dawnchorus_metadata_clean.csv
    <status_dir>/dawnchorus_metadata_log.csv
    <status_dir>/metadata_source_fingerprints.csv

Incremental behavior:
- New, changed and deleted IDs are detected from per-domain fingerprints.
- Metadata rows are updated by ID instead of append-only writes.
- All three outputs are replaced atomically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from common import atomic_write_csv


REQUIRED_COLUMNS = ["id", "lat", "lng", "datetime", "localtimes"]
DEFAULT_TIMEZONE = "Europe/Berlin"
CLEAN_FILENAME = "dawnchorus_metadata_clean.csv"
LOG_FILENAME = "dawnchorus_metadata_log.csv"
FINGERPRINT_FILENAME = "metadata_source_fingerprints.csv"
FINGERPRINT_GROUPS = {
    "metadata_fingerprint": ["id", "lat", "lng", "datetime", "localtimes"],
    "audio_fingerprint": ["id", "audio"],
    "photo_fingerprint": ["id", "photo"],
    "weather_fingerprint": ["id", "lat", "lng", "datetime", "localtimes"],
    "sentinel_fingerprint": ["id", "lat", "lng"],
}


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required_keys = ["dawn_chorus_csv", "status_dir"]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        raise KeyError(
            "Missing required config key(s): " + ", ".join(missing)
        )

    return config


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def strip_timezone_suffix(series: pd.Series) -> pd.Series:
    return clean_text(series).str.replace(
        r"(Z|[+-]\d{2}:?\d{2})$", "", regex=True
    )


def parse_walltime(series: pd.Series, timezone: str) -> pd.Series:
    parsed = pd.to_datetime(
        strip_timezone_suffix(series),
        errors="coerce",
        format="mixed",
    )
    return parsed.dt.tz_localize(
        timezone,
        ambiguous="NaT",
        nonexistent="NaT",
    )


def format_iso(series: pd.Series) -> pd.Series:
    output = series.dt.strftime("%Y-%m-%dT%H:%M:%S%z").astype("string")
    output = output.str.replace(
        r"([+-]\d{2})(\d{2})$",
        r"\1:\2",
        regex=True,
    )
    output[series.isna()] = pd.NA
    return output


def build_outputs(
    source: pd.DataFrame,
    timezone: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in source.columns
    ]
    if missing:
        raise ValueError(
            "Missing required Dawn Chorus columns: " + ", ".join(missing)
        )

    work = source[REQUIRED_COLUMNS].copy()
    work.insert(0, "source_row", work.index + 2)

    work["id"] = pd.to_numeric(
        work["id"], errors="coerce"
    ).astype("Int64")
    work["lat"] = pd.to_numeric(work["lat"], errors="coerce")
    work["lng"] = pd.to_numeric(work["lng"], errors="coerce")

    localtimes_raw = clean_text(work["localtimes"])
    datetime_raw = clean_text(work["datetime"])

    localtimes_parsed = parse_walltime(localtimes_raw, timezone)
    datetime_parsed = parse_walltime(datetime_raw, timezone)

    use_localtimes = localtimes_parsed.notna()
    use_datetime = ~use_localtimes & datetime_parsed.notna()

    effective = localtimes_parsed.copy()
    effective.loc[use_datetime] = datetime_parsed.loc[use_datetime]

    datetime_clean = format_iso(effective)

    clean = pd.DataFrame(
        {
            "id": work["id"],
            "datetime": datetime_clean,
            "lat": work["lat"],
            "lon": work["lng"],
        }
    )

    log = pd.DataFrame(
        {
            "source_row": work["source_row"],
            "id": work["id"],
            "datetime_clean": datetime_clean,
            "datetime_source": pd.Series(
                pd.NA, index=work.index, dtype="string"
            ),
            "conversion_needed": pd.Series(
                False, index=work.index, dtype="boolean"
            ),
            "conversion_step": pd.Series(
                pd.NA, index=work.index, dtype="string"
            ),
            "localtimes_raw": localtimes_raw,
            "datetime_raw": datetime_raw,
            "lat_raw": work["lat"],
            "lng_raw": work["lng"],
            "lat_clean": work["lat"],
            "lon_clean": work["lng"],
        }
    )

    log.loc[use_localtimes, "datetime_source"] = "localtimes"
    log.loc[use_datetime, "datetime_source"] = "datetime"

    log.loc[use_localtimes, "conversion_needed"] = True
    log.loc[use_localtimes, "conversion_step"] = (
        f"remove_timezone_suffix; "
        f"interpret_as_{timezone}_walltime; "
        "format_ISO8601"
    )

    log.loc[use_datetime, "conversion_needed"] = True
    log.loc[use_datetime, "conversion_step"] = (
        "fallback_to_datetime; "
        "remove_timezone_suffix; "
        f"interpret_as_{timezone}_walltime; "
        "format_ISO8601"
    )

    no_datetime = effective.isna()
    log.loc[no_datetime, "conversion_needed"] = False
    log.loc[no_datetime, "conversion_step"] = (
        "no_parseable_datetime"
    )

    return clean, log


def canonical(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value).strip()


def hash_values(row: pd.Series, columns: Iterable[str]) -> str:
    payload = "\x1f".join(
        f"{column}={canonical(row.get(column, ''))}"
        for column in columns
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_source(path: Path) -> pd.DataFrame:
    source = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    if len(source.columns) == 1:
        alternate = pd.read_csv(
            path,
            sep=";",
            low_memory=False,
            encoding="utf-8-sig",
        )
        if len(alternate.columns) > 1:
            source = alternate
    if "id" not in source.columns:
        raise ValueError("Missing required Dawn Chorus column: id")
    source = source.copy()
    source["id"] = pd.to_numeric(source["id"], errors="coerce").astype("Int64")
    source = source[source["id"].notna()]
    return source.loc[~source["id"].duplicated(keep="first")].copy()


def build_fingerprints(
    source: pd.DataFrame,
    *,
    timezone: str = DEFAULT_TIMEZONE,
) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "dawn_chorus_id": source["id"].astype("Int64").astype(str),
        }
    )
    for name, columns in FINGERPRINT_GROUPS.items():
        if name == "metadata_fingerprint":
            result[name] = source.apply(
                lambda row: hashlib.sha256(
                    (
                        hash_values(row, columns)
                        + f"\x1ftimezone={timezone}"
                    ).encode("utf-8")
                ).hexdigest(),
                axis=1,
            )
        else:
            result[name] = source.apply(
                lambda row: hash_values(row, columns),
                axis=1,
            )
    source_columns = sorted(
        {
            column
            for columns in FINGERPRINT_GROUPS.values()
            for column in columns
        }
    )
    result["source_fingerprint"] = source.apply(
        lambda row: hash_values(row, source_columns),
        axis=1,
    )
    return result.sort_values(
        "dawn_chorus_id",
        key=lambda values: pd.to_numeric(values, errors="coerce"),
    ).reset_index(drop=True)


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")


def fingerprint_map(
    frame: pd.DataFrame,
    column: str,
) -> dict[int, str]:
    if frame.empty or column not in frame.columns:
        return {}
    id_column = (
        "dawn_chorus_id"
        if "dawn_chorus_id" in frame.columns
        else "id"
    )
    ids = pd.to_numeric(frame[id_column], errors="coerce")
    return {
        int(dawn_id): str(value)
        for dawn_id, value in zip(ids, frame[column])
        if pd.notna(dawn_id)
    }


def changed_ids(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    column: str,
) -> set[int]:
    current_map = fingerprint_map(current, column)
    previous_map = fingerprint_map(previous, column)
    changed = {
        dawn_id
        for dawn_id, value in current_map.items()
        if previous_map.get(dawn_id) != value
    }
    return changed | (set(previous_map) - set(current_map))


def read_ids_file(path: Path | None) -> set[int] | None:
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(f"IDs file not found: {path}")
    frame = pd.read_csv(path, low_memory=False)
    for column in ("dawn_chorus_id", "id"):
        if column in frame.columns:
            return set(
                pd.to_numeric(frame[column], errors="coerce")
                .dropna()
                .astype(int)
            )
    raise KeyError(f"No dawn_chorus_id/id column in {path}")


def upsert_by_id(
    existing: pd.DataFrame,
    replacement: pd.DataFrame,
    target_ids: set[int],
) -> pd.DataFrame:
    if existing.empty:
        result = replacement.copy()
    else:
        existing = existing.copy()
        existing_ids = pd.to_numeric(existing["id"], errors="coerce")
        retained = existing.loc[~existing_ids.isin(target_ids)]
        result = pd.concat([retained, replacement], ignore_index=True)
    if "id" in result.columns:
        result = result.sort_values(
            "id",
            key=lambda values: pd.to_numeric(values, errors="coerce"),
        )
        result = result.drop_duplicates("id", keep="last")
    return result.reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Dawn Chorus metadata using config.json."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.json",
        help="Path to config.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Rebuild Step-1 outputs from the complete Dawn Chorus CSV."
        ),
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="Optional run-plan CSV with IDs to reconcile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)

        input_csv = Path(config["dawn_chorus_csv"])
        status_dir = Path(config["status_dir"])
        timezone = config.get(
            "metadata_extraction", {}
        ).get("timezone", DEFAULT_TIMEZONE)

        clean_csv = status_dir / CLEAN_FILENAME
        log_csv = status_dir / LOG_FILENAME
        fingerprint_csv = Path(
            config.get("metadata_extraction", {}).get(
                "fingerprint_csv",
                status_dir / FINGERPRINT_FILENAME,
            )
        )

        if not input_csv.is_file():
            raise FileNotFoundError(
                f"Dawn Chorus CSV not found: {input_csv}"
            )

        status_dir.mkdir(parents=True, exist_ok=True)

        source = read_source(input_csv)
        current_fingerprints = build_fingerprints(
            source,
            timezone=timezone,
        )
        previous_fingerprints = read_optional_csv(fingerprint_csv)
        existing_clean = read_optional_csv(clean_csv)
        existing_log = read_optional_csv(log_csv)
        requested_ids = read_ids_file(args.ids_file)

        source_changed = changed_ids(
            current_fingerprints,
            previous_fingerprints,
            "source_fingerprint",
        )
        metadata_changed = changed_ids(
            current_fingerprints,
            previous_fingerprints,
            "metadata_fingerprint",
        )
        current_ids = set(source["id"].dropna().astype(int))
        previous_ids = set(fingerprint_map(
            previous_fingerprints,
            "source_fingerprint",
        ))
        deleted_ids = previous_ids - current_ids

        if args.force:
            source_targets = current_ids | previous_ids
            metadata_targets = current_ids | previous_ids
        elif requested_ids is not None:
            source_targets = source_changed & requested_ids
            metadata_targets = metadata_changed & requested_ids
            metadata_targets |= deleted_ids & requested_ids
        else:
            source_targets = source_changed
            metadata_targets = metadata_changed

        selected = source[source["id"].isin(metadata_targets)].copy()
        if selected.empty:
            clean = pd.DataFrame(columns=["id", "datetime", "lat", "lon"])
            log = pd.DataFrame(
                columns=[
                    "source_row", "id", "datetime_clean",
                    "datetime_source", "conversion_needed",
                    "conversion_step", "localtimes_raw", "datetime_raw",
                    "lat_raw", "lng_raw", "lat_clean", "lon_clean",
                ]
            )
        else:
            clean, log = build_outputs(selected, timezone=timezone)

        if metadata_targets or not clean_csv.is_file() or not log_csv.is_file():
            merged_clean = upsert_by_id(
                existing_clean,
                clean,
                metadata_targets,
            )
            merged_log = upsert_by_id(
                existing_log,
                log,
                metadata_targets,
            )
            atomic_write_csv(merged_clean, clean_csv)
            atomic_write_csv(merged_log, log_csv)
        else:
            merged_clean = existing_clean
            merged_log = existing_log

        if (
            source_targets
            or metadata_targets
            or not fingerprint_csv.is_file()
            or args.force
        ):
            atomic_write_csv(current_fingerprints, fingerprint_csv)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Slurm job                   : {os.environ.get('SLURM_JOB_ID', 'none')}")
    print(f"Config                      : {args.config}")
    print(f"Input CSV                   : {input_csv}")
    print(f"Input rows                  : {len(source):,}")
    print(f"Previously fingerprinted IDs: {len(previous_ids):,}")
    print(f"Source IDs changed/new      : {len(source_targets):,}")
    print(f"Metadata IDs rebuilt/removed: {len(metadata_targets):,}")
    print(f"Deleted IDs                 : {len(deleted_ids):,}")

    if log.empty:
        print("Datetime from localtimes    : 0")
        print("Datetime fallback           : 0")
        print("Unparseable datetime        : 0")
    else:
        print(
            "Datetime from localtimes    : "
            f"{(log['datetime_source'] == 'localtimes').sum():,}"
        )
        print(
            "Datetime fallback           : "
            f"{(log['datetime_source'] == 'datetime').sum():,}"
        )
        print(
            "Unparseable datetime        : "
            f"{log['datetime_clean'].isna().sum():,}"
        )

    print(
        "Missing GPS pairs           : "
        f"{(clean['lat'].isna() | clean['lon'].isna()).sum():,}"
    )
    print(f"Clean CSV                   : {clean_csv}")
    print(f"Log CSV                     : {log_csv}")
    print(f"Fingerprint CSV             : {fingerprint_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

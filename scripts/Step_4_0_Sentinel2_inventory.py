#!/usr/bin/env python3
"""
Step 4_0: Inventory and validate Sentinel-2 GeoTIFF files.

The script scans the Sentinel-2 source directory, validates GeoTIFF files
directly at their original location and joins them with the Sentinel-2 quality
scores.

No files are copied or modified.

Compact output:
- dawn_chorus_id
- sentinel_exists
- sentinel_has_issues
- sentinel_quality_score

Detailed output:
- one row per GeoTIFF
- additional synthetic rows for scores without a corresponding GeoTIFF
- detailed raster metadata and issue descriptions

A low quality score does not automatically count as a technical issue.
Missing, invalid or inconsistent score information does count as an issue.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TIF_ID_PATTERN = re.compile(
    r"(\d+)(?=\.tiff?$)",
    flags=re.IGNORECASE,
)

DEFAULT_SOURCE = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/S2"
)

DEFAULT_SCORE_CSV = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/"
    "PointData/S2_Scores.csv"
)

DEFAULT_PROCESSED = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/"
    "Data_automatisation_skripts/outputs"
)

DETAIL_COLUMNS = [
    "dawn_chorus_id",
    "record_type",
    "source_relative_path",
    "source_path",
    "filename",
    "extension",
    "size_bytes",
    "mtime_ns",
    "id_extraction_ok",
    "raster_open_ok",
    "raster_read_ok",
    "driver",
    "width_px",
    "height_px",
    "band_count",
    "band_dtypes",
    "crs",
    "transform",
    "bounds",
    "nodata_values",
    "total_pixel_values",
    "valid_pixel_values",
    "nodata_pixel_values",
    "nan_pixel_values",
    "infinite_pixel_values",
    "nodata_fraction",
    "all_pixels_nodata",
    "constant_raster",
    "sentinel_quality_score",
    "score_present",
    "score_valid",
    "score_row_count",
    "has_issues",
    "issues",
]


def load_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the complete JSON config and the sentinel2_inventory section."""
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    section = config.get("sentinel2_inventory", {})

    if not isinstance(section, dict):
        raise TypeError("'sentinel2_inventory' must be a JSON object.")

    return config, section


def discover_tifs(
    source_dir: Path,
    recursive: bool,
) -> list[Path]:
    """Find all TIF and TIFF files in the Sentinel-2 source directory."""
    if not source_dir.is_dir():
        raise NotADirectoryError(
            f"Sentinel-2 source directory not found: {source_dir}"
        )

    iterator = (
        source_dir.rglob("*")
        if recursive
        else source_dir.iterdir()
    )

    return sorted(
        path
        for path in iterator
        if path.is_file()
        and path.suffix.lower() in {".tif", ".tiff"}
    )


def extract_dawn_chorus_id(path: Path) -> str:
    """Extract the last digit sequence immediately before .tif or .tiff."""
    match = TIF_ID_PATTERN.search(path.name)
    return match.group(1) if match else ""


def resolve_score_id_column(
    columns: list[str],
    configured: str | None = None,
) -> str:
    """Resolve common Dawn Chorus ID aliases without changing the source CSV."""
    lookup = {column.strip().lower(): column for column in columns}
    candidates = [
        configured,
        "id",
        "DC_id",
        "dawn_chorus_id",
        "recording_id",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = lookup.get(str(candidate).strip().lower())
        if resolved:
            return resolved
    raise ValueError(
        "Missing Dawn Chorus ID column in Sentinel-2 score CSV. "
        f"Tried {[candidate for candidate in candidates if candidate]}. "
        f"Available columns: {columns}"
    )


def load_scores(
    score_csv: Path,
    score_id_column: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """
    Load Sentinel-2 quality scores.

    For duplicate IDs, the highest valid numeric score is retained. Metadata
    about duplicate, missing and invalid values is kept for issue reporting.
    """
    if not score_csv.is_file():
        raise FileNotFoundError(
            f"Sentinel-2 score CSV not found: {score_csv}"
        )

    df = pd.read_csv(
        score_csv,
        low_memory=False,
        encoding="utf-8-sig",
    )

    required_columns = {"score"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Missing required columns in Sentinel-2 score CSV: "
            f"{sorted(missing_columns)}. "
            f"Available columns: {df.columns.tolist()}"
        )

    resolved_id_column = resolve_score_id_column(
        df.columns.tolist(),
        score_id_column,
    )
    df["dawn_chorus_id"] = pd.to_numeric(
        df[resolved_id_column],
        errors="coerce",
    ).astype("Int64")

    df["numeric_score"] = pd.to_numeric(
        df["score"],
        errors="coerce",
    )

    global_issues: list[str] = []

    invalid_id_count = int(df["dawn_chorus_id"].isna().sum())
    if invalid_id_count:
        global_issues.append(
            f"score_rows_with_invalid_id:{invalid_id_count}"
        )

    score_info: dict[str, dict[str, Any]] = {}

    valid_id_rows = df.dropna(
        subset=["dawn_chorus_id"]
    ).copy()

    for dawn_id, group in valid_id_rows.groupby(
        "dawn_chorus_id",
        sort=False,
    ):
        dawn_id_str = str(int(dawn_id))
        row_count = len(group)

        numeric_scores = group["numeric_score"].dropna()
        valid_scores = numeric_scores[
            numeric_scores.between(
                0,
                1,
                inclusive="both",
            )
        ]

        score_present = not numeric_scores.empty
        score_valid = not valid_scores.empty

        selected_score: float | None = (
            float(valid_scores.max())
            if score_valid
            else None
        )

        issues: list[str] = []

        missing_numeric_count = int(
            group["numeric_score"].isna().sum()
        )

        invalid_range_count = int(
            (
                group["numeric_score"].notna()
                & ~group["numeric_score"].between(
                    0,
                    1,
                    inclusive="both",
                )
            ).sum()
        )

        if row_count > 1:
            issues.append(
                f"duplicate_score_rows:{row_count}"
            )

        if missing_numeric_count:
            issues.append(
                f"non_numeric_or_missing_scores:{missing_numeric_count}"
            )

        if invalid_range_count:
            issues.append(
                f"scores_outside_0_1:{invalid_range_count}"
            )

        if not score_present:
            issues.append("quality_score_missing")

        elif not score_valid:
            issues.append("no_valid_quality_score")

        score_info[dawn_id_str] = {
            "score": selected_score,
            "score_present": score_present,
            "score_valid": score_valid,
            "score_row_count": row_count,
            "issues": issues,
        }

    return score_info, global_issues


def inspect_raster(path: Path) -> dict[str, Any]:
    """
    Open and fully read a GeoTIFF block by block.

    Block-wise reading validates the complete raster without loading the entire
    file into memory at once.
    """
    import rasterio
    from affine import Affine

    issues: list[str] = []

    raster_open_ok = False
    raster_read_ok = False

    driver = ""
    width = ""
    height = ""
    band_count = ""
    band_dtypes = ""
    crs = ""
    transform = ""
    bounds = ""
    nodata_values = ""

    total_values = 0
    valid_values = 0
    nodata_values_count = 0
    nan_values = 0
    infinite_values = 0

    global_min: float | None = None
    global_max: float | None = None

    try:
        with rasterio.open(path) as dataset:
            raster_open_ok = True

            driver = str(dataset.driver or "")
            width = int(dataset.width)
            height = int(dataset.height)
            band_count = int(dataset.count)
            band_dtypes = ",".join(dataset.dtypes)
            crs = "" if dataset.crs is None else str(dataset.crs)
            transform = str(dataset.transform)
            bounds = str(dataset.bounds)
            nodata_values = ",".join(
                "" if value is None else str(value)
                for value in dataset.nodatavals
            )

            if dataset.driver != "GTiff":
                issues.append(
                    f"unexpected_raster_driver:{dataset.driver}"
                )

            if dataset.width <= 0 or dataset.height <= 0:
                issues.append(
                    f"invalid_dimensions:{dataset.width}x{dataset.height}"
                )

            if dataset.count <= 0:
                issues.append("no_raster_bands")

            if dataset.crs is None:
                issues.append("missing_crs")

            if dataset.transform == Affine.identity():
                issues.append("identity_geotransform")

            raster_bounds = dataset.bounds

            if not all(
                math.isfinite(value)
                for value in (
                    raster_bounds.left,
                    raster_bounds.bottom,
                    raster_bounds.right,
                    raster_bounds.top,
                )
            ):
                issues.append("non_finite_bounds")

            elif (
                raster_bounds.left >= raster_bounds.right
                or raster_bounds.bottom >= raster_bounds.top
            ):
                issues.append("invalid_bounds")

            # Read every band and every raster block.
            for band_index in range(1, dataset.count + 1):
                for _, window in dataset.block_windows(band_index):
                    block = dataset.read(
                        band_index,
                        window=window,
                        masked=True,
                    )

                    total_values += int(block.size)

                    mask = np.ma.getmaskarray(block)
                    nodata_values_count += int(mask.sum())

                    valid = block.compressed()
                    valid_values += int(valid.size)

                    if valid.size == 0:
                        continue

                    if np.issubdtype(valid.dtype, np.floating):
                        block_nan_count = int(np.isnan(valid).sum())
                        block_inf_count = int(np.isinf(valid).sum())

                        nan_values += block_nan_count
                        infinite_values += block_inf_count

                        finite = valid[np.isfinite(valid)]

                    else:
                        finite = valid

                    if finite.size == 0:
                        continue

                    block_min = float(np.min(finite))
                    block_max = float(np.max(finite))

                    global_min = (
                        block_min
                        if global_min is None
                        else min(global_min, block_min)
                    )

                    global_max = (
                        block_max
                        if global_max is None
                        else max(global_max, block_max)
                    )

            raster_read_ok = True

    except Exception as exc:
        issues.append(
            f"raster_read_failed:{type(exc).__name__}:{exc}"
        )

    all_pixels_nodata = (
        total_values > 0
        and valid_values == 0
    )

    constant_raster = (
        global_min is not None
        and global_max is not None
        and global_min == global_max
    )

    nodata_fraction: float | None = (
        nodata_values_count / total_values
        if total_values > 0
        else None
    )

    if all_pixels_nodata:
        issues.append("all_pixels_nodata")

    if nan_values:
        issues.append(
            f"contains_nan_values:{nan_values}"
        )

    if infinite_values:
        issues.append(
            f"contains_infinite_values:{infinite_values}"
        )

    if constant_raster:
        issues.append(
            f"constant_raster:value={global_min}"
        )

    return {
        "raster_open_ok": raster_open_ok,
        "raster_read_ok": raster_read_ok,
        "driver": driver,
        "width": width,
        "height": height,
        "band_count": band_count,
        "band_dtypes": band_dtypes,
        "crs": crs,
        "transform": transform,
        "bounds": bounds,
        "nodata_values": nodata_values,
        "total_values": total_values,
        "valid_values": valid_values,
        "nodata_values_count": nodata_values_count,
        "nan_values": nan_values,
        "infinite_values": infinite_values,
        "nodata_fraction": nodata_fraction,
        "all_pixels_nodata": all_pixels_nodata,
        "constant_raster": constant_raster,
        "issues": issues,
    }


def validate_original_file(
    task: tuple[Path, Path],
) -> dict[str, Any]:
    """Validate one Sentinel-2 GeoTIFF directly at its source path."""
    source, source_root = task

    relative = source.relative_to(source_root)
    dawn_id = extract_dawn_chorus_id(source)
    issues: list[str] = []

    id_extraction_ok = bool(dawn_id)

    if not id_extraction_ok:
        issues.append(
            "filename_does_not_contain_id_before_tif_extension"
        )

    try:
        stat = source.stat()

    except OSError as exc:
        issues.append(
            f"source_stat_failed:{type(exc).__name__}:{exc}"
        )

        return {
            "dawn_chorus_id": dawn_id,
            "record_type": "tif",
            "source_relative_path": relative.as_posix(),
            "source_path": str(source),
            "filename": source.name,
            "extension": source.suffix.lower(),
            "size_bytes": "",
            "mtime_ns": "",
            "id_extraction_ok": id_extraction_ok,
            "raster_open_ok": False,
            "raster_read_ok": False,
            "driver": "",
            "width_px": "",
            "height_px": "",
            "band_count": "",
            "band_dtypes": "",
            "crs": "",
            "transform": "",
            "bounds": "",
            "nodata_values": "",
            "total_pixel_values": 0,
            "valid_pixel_values": 0,
            "nodata_pixel_values": 0,
            "nan_pixel_values": 0,
            "infinite_pixel_values": 0,
            "nodata_fraction": "",
            "all_pixels_nodata": False,
            "constant_raster": False,
            "sentinel_quality_score": "",
            "score_present": False,
            "score_valid": False,
            "score_row_count": 0,
            "has_issues": True,
            "issues": " | ".join(issues),
        }

    if stat.st_size == 0:
        issues.append("empty_file")

    inspection = inspect_raster(source)
    issues.extend(inspection["issues"])

    nodata_fraction = inspection["nodata_fraction"]

    return {
        "dawn_chorus_id": dawn_id,
        "record_type": "tif",
        "source_relative_path": relative.as_posix(),
        "source_path": str(source),
        "filename": source.name,
        "extension": source.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "id_extraction_ok": id_extraction_ok,
        "raster_open_ok": bool(
            inspection["raster_open_ok"]
        ),
        "raster_read_ok": bool(
            inspection["raster_read_ok"]
        ),
        "driver": inspection["driver"],
        "width_px": inspection["width"],
        "height_px": inspection["height"],
        "band_count": inspection["band_count"],
        "band_dtypes": inspection["band_dtypes"],
        "crs": inspection["crs"],
        "transform": inspection["transform"],
        "bounds": inspection["bounds"],
        "nodata_values": inspection["nodata_values"],
        "total_pixel_values": inspection["total_values"],
        "valid_pixel_values": inspection["valid_values"],
        "nodata_pixel_values": inspection["nodata_values_count"],
        "nan_pixel_values": inspection["nan_values"],
        "infinite_pixel_values": inspection["infinite_values"],
        "nodata_fraction": (
            ""
            if nodata_fraction is None
            else f"{nodata_fraction:.8f}"
        ),
        "all_pixels_nodata": bool(
            inspection["all_pixels_nodata"]
        ),
        "constant_raster": bool(
            inspection["constant_raster"]
        ),
        "sentinel_quality_score": "",
        "score_present": False,
        "score_valid": False,
        "score_row_count": 0,
        "has_issues": bool(issues),
        "issues": " | ".join(issues),
    }


def read_existing(
    path: Path,
) -> dict[str, dict[str, str]]:
    """Read the existing file-level inventory for incremental processing."""
    if not path.is_file():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return {
            row["source_relative_path"]: row
            for row in csv.DictReader(handle)
            if (
                row.get("record_type") == "tif"
                and row.get("source_relative_path")
            )
        }


def split_issues(value: Any) -> list[str]:
    """Convert the pipe-separated issue field back into a list."""
    text = str(value or "").strip()

    if not text:
        return []

    return [
        item.strip()
        for item in text.split("|")
        if item.strip()
    ]


def add_issue(row: dict[str, Any], issue: str) -> None:
    """Append an issue without creating duplicates."""
    issues = split_issues(row.get("issues", ""))

    if issue not in issues:
        issues.append(issue)

    row["issues"] = " | ".join(issues)
    row["has_issues"] = bool(issues)


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> None:
    """Write a CSV atomically through a temporary file."""
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inventory and validate Sentinel-2 GeoTIFF files."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "config.json"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Revalidate all GeoTIFF files.",
    )

    return parser.parse_args()


def main() -> int:
    """Run the Sentinel-2 inventory and sanity-check workflow."""
    args = parse_args()

    try:
        config, settings = load_config(args.config)

        processed_root = Path(
            settings.get(
                "processed_dir",
                DEFAULT_PROCESSED,
            )
        )

        source_dir = Path(
            settings.get(
                "source_dir",
                DEFAULT_SOURCE,
            )
        )

        score_csv = Path(
            settings.get(
                "score_csv",
                DEFAULT_SCORE_CSV,
            )
        )

        detailed_csv = Path(
            settings.get(
                "detailed_log",
                processed_root
                / "sentinel2_inventory_detailed.csv",
            )
        )

        compact_csv = Path(
            settings.get(
                "compact_log",
                processed_root
                / "sentinel2_inventory_compact.csv",
            )
        )

        status_dir = Path(
            config.get(
                "status_dir",
                processed_root / "_status",
            )
        )

        state_file = Path(
            settings.get(
                "state_file",
                status_dir
                / "step_4_0_sentinel2_inventory_state.json",
            )
        )

        recursive = bool(
            settings.get("recursive", True)
        )

        allocated = int(
            os.environ.get(
                "SLURM_CPUS_PER_TASK",
                "1",
            )
        )

        configured_workers = int(
            settings.get(
                "workers",
                allocated,
            )
        )

        workers = max(
            1,
            min(configured_workers, allocated),
        )

        tif_files = discover_tifs(
            source_dir,
            recursive,
        )

        score_info, score_global_issues = load_scores(
            score_csv,
            settings.get("score_id_column"),
        )

        existing = read_existing(detailed_csv)

        current_relative_paths = {
            path.relative_to(source_dir).as_posix()
            for path in tif_files
        }

        retained = {
            key: value
            for key, value in existing.items()
            if key in current_relative_paths
        }

        tasks: list[tuple[Path, Path]] = []
        unchanged_count = 0

        for path in tif_files:
            relative_path = (
                path.relative_to(source_dir).as_posix()
            )

            try:
                stat = path.stat()

            except OSError:
                tasks.append((path, source_dir))
                continue

            old = existing.get(relative_path)

            unchanged = (
                not args.force
                and old is not None
                and old.get("size_bytes")
                == str(stat.st_size)
                and old.get("mtime_ns")
                == str(stat.st_mtime_ns)
            )

            if unchanged:
                unchanged_count += 1

            else:
                tasks.append((path, source_dir))

        print(
            f"Sentinel-2 TIF files            : {len(tif_files):,}"
        )
        print(
            f"Unchanged inventory rows        : {unchanged_count:,}"
        )
        print(
            f"New/changed files to validate   : {len(tasks):,}"
        )
        print(
            f"IDs represented in score CSV    : {len(score_info):,}"
        )
        print(
            f"Worker threads                  : {workers}"
        )

        if tasks:
            with ThreadPoolExecutor(
                max_workers=workers
            ) as pool:

                futures = [
                    pool.submit(
                        validate_original_file,
                        task,
                    )
                    for task in tasks
                ]

                for index, future in enumerate(
                    as_completed(futures),
                    start=1,
                ):
                    row = future.result()

                    relative_path = str(
                        row["source_relative_path"]
                    )

                    retained[relative_path] = {
                        key: str(value)
                        for key, value in row.items()
                    }

                    if (
                        index % 100 == 0
                        or index == len(futures)
                    ):
                        print(
                            f"Validated {index:,}/{len(futures):,}"
                        )

        tif_rows: list[dict[str, Any]] = [
            dict(retained[key])
            for key in sorted(retained)
        ]

        # Build the ID-to-file mapping before adding score information.
        rows_by_id: dict[str, list[dict[str, Any]]] = {}

        for row in tif_rows:
            dawn_id = str(
                row.get("dawn_chorus_id", "")
            ).strip()

            if dawn_id:
                rows_by_id.setdefault(
                    dawn_id,
                    [],
                ).append(row)

        # Multiple GeoTIFFs for one ID are treated as an inventory issue.
        for dawn_id, id_rows in rows_by_id.items():
            if len(id_rows) > 1:
                for row in id_rows:
                    add_issue(
                        row,
                        f"duplicate_tif_files_for_id:{len(id_rows)}",
                    )

        # Attach score information to every GeoTIFF row.
        for row in tif_rows:
            dawn_id = str(
                row.get("dawn_chorus_id", "")
            ).strip()

            if not dawn_id:
                continue

            score = score_info.get(dawn_id)

            if score is None:
                row["sentinel_quality_score"] = ""
                row["score_present"] = False
                row["score_valid"] = False
                row["score_row_count"] = 0
                add_issue(row, "quality_score_missing")

            else:
                row["sentinel_quality_score"] = (
                    ""
                    if score["score"] is None
                    else score["score"]
                )
                row["score_present"] = score["score_present"]
                row["score_valid"] = score["score_valid"]
                row["score_row_count"] = score["score_row_count"]

                for issue in score["issues"]:
                    add_issue(row, issue)

        # Add one synthetic detailed row for each score without a GeoTIFF.
        score_only_rows: list[dict[str, Any]] = []

        for dawn_id, score in score_info.items():
            if dawn_id in rows_by_id:
                continue

            issues = ["score_without_tif"]
            issues.extend(score["issues"])

            score_only_rows.append({
                "dawn_chorus_id": dawn_id,
                "record_type": "score_without_tif",
                "source_relative_path": "",
                "source_path": "",
                "filename": "",
                "extension": "",
                "size_bytes": "",
                "mtime_ns": "",
                "id_extraction_ok": True,
                "raster_open_ok": False,
                "raster_read_ok": False,
                "driver": "",
                "width_px": "",
                "height_px": "",
                "band_count": "",
                "band_dtypes": "",
                "crs": "",
                "transform": "",
                "bounds": "",
                "nodata_values": "",
                "total_pixel_values": 0,
                "valid_pixel_values": 0,
                "nodata_pixel_values": 0,
                "nan_pixel_values": 0,
                "infinite_pixel_values": 0,
                "nodata_fraction": "",
                "all_pixels_nodata": False,
                "constant_raster": False,
                "sentinel_quality_score": (
                    ""
                    if score["score"] is None
                    else score["score"]
                ),
                "score_present": score["score_present"],
                "score_valid": score["score_valid"],
                "score_row_count": score["score_row_count"],
                "has_issues": True,
                "issues": " | ".join(dict.fromkeys(issues)),
            })

        detailed_rows = tif_rows + score_only_rows

        detailed_rows.sort(
            key=lambda row: (
                int(row["dawn_chorus_id"])
                if str(row.get("dawn_chorus_id", "")).isdigit()
                else sys.maxsize,
                str(row.get("record_type", "")),
                str(row.get("source_relative_path", "")),
            )
        )

        write_csv(
            detailed_csv,
            detailed_rows,
            DETAIL_COLUMNS,
        )

        # Create one compact row per ID from the union of TIF and score IDs.
        all_ids = set(rows_by_id) | set(score_info)

        compact_rows: list[dict[str, Any]] = []

        for dawn_id in sorted(
            all_ids,
            key=int,
        ):
            id_tif_rows = rows_by_id.get(
                dawn_id,
                [],
            )

            score = score_info.get(dawn_id)

            sentinel_exists = bool(id_tif_rows)

            sentinel_has_issues = (
                not sentinel_exists
                or any(
                    str(
                        row.get("has_issues", "")
                    ).lower()
                    == "true"
                    for row in id_tif_rows
                )
            )

            quality_score: float | str = ""

            if score is None:
                sentinel_has_issues = True

            else:
                if score["score"] is not None:
                    quality_score = score["score"]

                if score["issues"]:
                    sentinel_has_issues = True

            compact_rows.append({
                "dawn_chorus_id": dawn_id,
                "sentinel_exists": sentinel_exists,
                "sentinel_has_issues": sentinel_has_issues,
                "sentinel_quality_score": quality_score,
            })

        write_csv(
            compact_csv,
            compact_rows,
            [
                "dawn_chorus_id",
                "sentinel_exists",
                "sentinel_has_issues",
                "sentinel_quality_score",
            ],
        )

        tif_issue_count = sum(
            str(
                row.get("has_issues", "")
            ).lower()
            == "true"
            for row in tif_rows
        )

        compact_issue_count = sum(
            bool(row["sentinel_has_issues"])
            for row in compact_rows
        )

        open_failure_count = sum(
            str(
                row.get("raster_open_ok", "")
            ).lower()
            != "true"
            for row in tif_rows
        )

        read_failure_count = sum(
            str(
                row.get("raster_read_ok", "")
            ).lower()
            != "true"
            for row in tif_rows
        )

        score_without_tif_count = len(
            score_only_rows
        )

        tif_without_score_count = sum(
            1
            for dawn_id in rows_by_id
            if dawn_id not in score_info
        )

        state_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        state_data = {
            "source_dir": str(source_dir),
            "score_csv": str(score_csv),
            "detailed_log": str(detailed_csv),
            "compact_log": str(compact_csv),
            "source_tif_files": len(tif_files),
            "dawn_chorus_ids_in_compact_log": len(compact_rows),
            "unchanged_files_reused": unchanged_count,
            "files_validated_this_run": len(tasks),
            "tif_files_with_issues": tif_issue_count,
            "ids_with_issues": compact_issue_count,
            "raster_open_failures": open_failure_count,
            "raster_read_failures": read_failure_count,
            "scores_without_tif": score_without_tif_count,
            "tif_ids_without_score": tif_without_score_count,
            "score_csv_global_issues": score_global_issues,
            "workers": workers,
            "recursive": recursive,
            "force_run": bool(args.force),
            "copying_enabled": False,
        }

        temporary_state = state_file.with_suffix(
            state_file.suffix + ".tmp"
        )

        with temporary_state.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                state_data,
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.write("\n")

        temporary_state.replace(state_file)

        print()
        print("Step 4_0 completed.")
        print(
            f"Sentinel-2 TIF files         : {len(tif_files):,}"
        )
        print(
            f"Files checked this run       : {len(tasks):,}"
        )
        print(
            f"Unchanged files reused       : {unchanged_count:,}"
        )
        print(
            f"TIF files with issues        : {tif_issue_count:,}"
        )
        print(
            f"IDs with issues              : {compact_issue_count:,}"
        )
        print(
            f"Raster open failures         : {open_failure_count:,}"
        )
        print(
            f"Raster read failures         : {read_failure_count:,}"
        )
        print(
            f"Scores without TIF           : {score_without_tif_count:,}"
        )
        print(
            f"TIF IDs without score        : {tif_without_score_count:,}"
        )
        print(
            f"Detailed log                 : {detailed_csv}"
        )
        print(
            f"Compact log                  : {compact_csv}"
        )
        print(
            f"State file                   : {state_file}"
        )

        return 0

    except Exception as exc:
        print(
            f"ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Step 5_5: Quality-check Susi-compatible HOSTRADA raster tiles."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio

from common import atomic_write_csv, atomic_write_json, atomic_write_text, utc_now_iso


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "hostrada_raster_quality_check" not in config:
        raise KeyError("Missing hostrada_raster_quality_check section in config.")
    return config


def invalid_mask(data: np.ndarray, nodata: float | int | None) -> np.ndarray:
    mask = ~np.isfinite(data)
    if nodata is not None:
        mask |= data == nodata
    return mask


def count_constant_rows_cols(
    data: np.ndarray,
    mask: np.ndarray,
) -> tuple[int, int, int, int]:
    constant_rows = 0
    constant_cols = 0
    nodata_rows = 0
    nodata_cols = 0

    for row_index in range(data.shape[0]):
        row_mask = mask[row_index, :]
        if np.all(row_mask):
            nodata_rows += 1
            continue
        valid = data[row_index, ~row_mask]
        if valid.size and np.all(valid == valid[0]):
            constant_rows += 1

    for col_index in range(data.shape[1]):
        col_mask = mask[:, col_index]
        if np.all(col_mask):
            nodata_cols += 1
            continue
        valid = data[~col_mask, col_index]
        if valid.size and np.all(valid == valid[0]):
            constant_cols += 1

    return constant_rows, constant_cols, nodata_rows, nodata_cols


def check_file(path: Path, forced_nodata: float | int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stat = path.stat()
    with rasterio.open(path) as src:
        nodata = forced_nodata if forced_nodata is not None else src.nodata
        descriptions = src.descriptions
        for band_index in range(1, src.count + 1):
            data = src.read(band_index)
            mask = invalid_mask(data, nodata)
            valid = data[~mask]
            (
                constant_rows,
                constant_cols,
                nodata_rows,
                nodata_cols,
            ) = count_constant_rows_cols(data, mask)
            row: dict[str, Any] = {
                "file": path.name,
                "path": str(path),
                "file_size_bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "band": band_index,
                "band_name": descriptions[band_index - 1] or f"band_{band_index:02d}",
                "height": int(data.shape[0]),
                "width": int(data.shape[1]),
                "square": bool(data.shape[0] == data.shape[1]),
                "band_count": int(src.count),
                "crs": str(src.crs),
                "nodata_value": nodata,
                "valid_pixels": int(valid.size),
                "invalid_pixels": int(mask.sum()),
                "constant_rows": int(constant_rows),
                "constant_cols": int(constant_cols),
                "nodata_rows": int(nodata_rows),
                "nodata_cols": int(nodata_cols),
            }
            if valid.size == 0:
                row["status"] = "ONLY_NODATA"
            else:
                row.update(
                    {
                        "status": "OK",
                        "min": float(np.min(valid)),
                        "max": float(np.max(valid)),
                        "mean": float(np.mean(valid)),
                        "std": float(np.std(valid)),
                    }
                )
            rows.append(row)
    return rows


def write_report(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# HOSTRADA Raster Quality Check",
        "",
        f"- Files checked: `{summary['files_checked']:,}`",
        f"- Band rows: `{summary['band_rows']:,}`",
        f"- Non-square bands: `{summary['non_square_bands']:,}`",
        f"- Only-NoData bands: `{summary['only_nodata_bands']:,}`",
        f"- Bands with constant rows/cols: `{summary['bands_with_constant_lines']:,}`",
        f"- CSV: `{summary['csv']}`",
        f"- JSON: `{summary['json']}`",
        "",
    ]
    atomic_write_text(path, "\n".join(lines))


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    table = pd.DataFrame(rows)
    csv_path = output_dir / "hostrada_raster_quality.csv"
    json_path = output_dir / "hostrada_raster_quality.json"
    report_path = output_dir / "hostrada_raster_quality.md"
    atomic_write_csv(table, csv_path)
    summary = {
        "files_checked": int(table["file"].nunique()) if not table.empty else 0,
        "band_rows": int(len(table)),
        "non_square_bands": int((~table["square"]).sum()) if not table.empty else 0,
        "only_nodata_bands": int((table["status"] == "ONLY_NODATA").sum()) if not table.empty else 0,
        "bands_with_constant_lines": int(
            (
                (table["constant_rows"] > 0)
                | (table["constant_cols"] > 0)
                | (table["nodata_rows"] > 0)
                | (table["nodata_cols"] > 0)
            ).sum()
        ) if not table.empty else 0,
        "csv": str(csv_path),
        "json": str(json_path),
        "report": str(report_path),
    }
    atomic_write_json(json_path, summary)
    write_report(summary, report_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check HOSTRADA raster tile quality."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument("--variable")
    parser.add_argument("--input-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        settings = config["hostrada_raster_quality_check"]
        variable = args.variable or settings.get("variable")

        if args.input_dir is not None:
            input_dir = args.input_dir
        elif variable:
            input_dir = (
                Path(config["hostrada_raster_products"]["output_root"])
                / f"Hostrada_{variable}"
            )
        else:
            input_dir = Path(settings["input_dir"])

        output_dir = Path(settings["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        forced_nodata = settings.get("forced_nodata")
        workers = int(settings.get("workers", 4))
        recursive = bool(settings.get("recursive", False))

        iterator = input_dir.rglob if recursive else input_dir.glob
        tif_files = sorted(list(iterator("*.tif")) + list(iterator("*.tiff")))
        if not tif_files:
            raise FileNotFoundError(f"No TIFF files found in {input_dir}")

        previous_csv = output_dir / "hostrada_raster_quality.csv"
        previous = (
            pd.read_csv(previous_csv, low_memory=False)
            if previous_csv.is_file() and previous_csv.stat().st_size > 0
            else pd.DataFrame()
        )
        previous_by_path = {
            str(path): group.copy()
            for path, group in previous.groupby("path", sort=False)
        } if not previous.empty and "path" in previous.columns else {}
        rows: list[dict[str, Any]] = []
        files_to_check: list[Path] = []
        reused_files = 0
        for path in tif_files:
            old = previous_by_path.get(str(path))
            stat = path.stat()
            reusable = (
                old is not None
                and not old.empty
                and {
                    "file_size_bytes",
                    "mtime_ns",
                    "status",
                    "square",
                    "constant_rows",
                    "constant_cols",
                    "nodata_rows",
                    "nodata_cols",
                } <= set(old.columns)
            )
            if reusable:
                same_size = pd.to_numeric(
                    old.get("file_size_bytes"),
                    errors="coerce",
                ).eq(stat.st_size).all()
                same_mtime = pd.to_numeric(
                    old.get("mtime_ns"),
                    errors="coerce",
                ).eq(stat.st_mtime_ns).all()
                clean = (
                    old["status"].astype(str).eq("OK").all()
                    and old["square"].astype(str).str.lower().isin({"true", "1"}).all()
                    and pd.to_numeric(old["constant_rows"], errors="coerce").fillna(0).eq(0).all()
                    and pd.to_numeric(old["constant_cols"], errors="coerce").fillna(0).eq(0).all()
                    and pd.to_numeric(old["nodata_rows"], errors="coerce").fillna(0).eq(0).all()
                    and pd.to_numeric(old["nodata_cols"], errors="coerce").fillna(0).eq(0).all()
                )
                reusable = bool(same_size and same_mtime and clean)
            if reusable:
                rows.extend(old.to_dict("records"))
                reused_files += 1
            else:
                files_to_check.append(path)

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(check_file, path, forced_nodata): path
                for path in files_to_check
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                path = futures[future]
                rows.extend(future.result())
                elapsed = time.monotonic() - started
                rate = completed / elapsed if elapsed > 0 else 0.0
                eta = (len(files_to_check) - completed) / rate if rate > 0 else 0.0
                print(f"[{completed}/{len(files_to_check)}] {path.name} ETA {eta / 60:.1f} min")
                write_outputs(rows, output_dir)

        summary = write_outputs(rows, output_dir)
        summary["input_dir"] = str(input_dir)
        summary["files_reused"] = reused_files
        summary["files_revalidated"] = len(files_to_check)
        atomic_write_json(Path(summary["json"]), summary)
        state_file = Path(
            settings.get("state_file", output_dir / "state.json")
        )
        atomic_write_json(
            state_file,
            {
                "schema_version": "2026-07-23-hostrada-raster-qc-v2",
                "updated_utc": utc_now_iso(),
                **summary,
            },
        )

        print(f"CSV: {summary['csv']}")
        print(f"JSON: {summary['json']}")
        print(f"Report: {summary['report']}")
        print(f"Files reused: {reused_files:,}")
        print(f"Files revalidated: {len(files_to_check):,}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 5_5: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

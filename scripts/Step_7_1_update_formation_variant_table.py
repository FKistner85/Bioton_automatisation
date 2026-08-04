#!/usr/bin/env python3
"""Build the normalized Dawn Chorus x LRT-variant formation table."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from Step_7_0_update_master_table import (
    add_100m_formation,
    add_10m_formation,
    normalise_id_column,
    read_csv_optional,
)

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from step2_variants import prepare


VARIANT_COLUMNS = [
    "dawn_chorus_id",
    "lrt_variant",
    "lrt_variant_is_primary",
    "source_gpkg",
    "variant_100m_product_exists",
    "variant_10m_product_exists",
    "grid_100m_id",
    "grid_100m_assignment_exists",
    "grid_100m_has_majority_formation",
    "majority_formation_100m",
    "majority_formation_status_100m",
    "majority_value_100m",
    "second_value_100m",
    "majority_delta_100m",
    "majority_disputed_100m",
    "grid_10m_id",
    "grid_10m_assignment_exists",
    "grid_10m_has_majority_formation",
    "majority_formation_10m",
    "majority_formation_status_10m",
    "majority_value_10m",
    "second_value_10m",
    "majority_delta_10m",
    "majority_disputed_10m",
    "formation_100m_10m_agree",
    "formation_status_100m_10m_agree",
    "variant_record_status",
    "updated_utc",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, dir=path.parent, encoding="utf-8", newline=""
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temporary, path)


def load_metadata(config: dict[str, Any]) -> pd.DataFrame:
    path = Path(config["point_lrt_assignment"]["metadata_csv"])
    metadata = normalise_id_column(
        read_csv_optional(path),
        ["dawn_chorus_id", "id"],
    )
    required = {"dawn_chorus_id", "lat", "lon"}
    missing = required - set(metadata.columns)
    if missing:
        raise KeyError(f"Metadata missing columns: {sorted(missing)}")
    return metadata[["dawn_chorus_id", "lat", "lon"]].drop_duplicates(
        "dawn_chorus_id"
    )


def build_variant_rows(
    metadata: pd.DataFrame,
    config: dict[str, Any],
    suffix: str,
    primary: str,
    source_gpkg: Path,
) -> pd.DataFrame:
    assignment = Path(config["point_lrt_assignment"]["output_csv"])
    ten_m = Path(config["susi_10m_products"]["final_parquet"])
    table = add_100m_formation(metadata.copy(), config)
    table = add_10m_formation(table, config)
    table["lrt_variant"] = suffix
    table["lrt_variant_is_primary"] = suffix == primary
    table["source_gpkg"] = str(source_gpkg)
    table["variant_100m_product_exists"] = assignment.is_file()
    table["variant_10m_product_exists"] = ten_m.is_file()
    table["formation_100m_10m_agree"] = (
        table["majority_formation_100m"].notna()
        & table["majority_formation_10m"].notna()
        & (
            table["majority_formation_100m"].astype(str)
            == table["majority_formation_10m"].astype(str)
        )
    )
    table["formation_status_100m_10m_agree"] = (
        table["majority_formation_status_100m"].notna()
        & table["majority_formation_status_10m"].notna()
        & (
            table["majority_formation_status_100m"].astype(str)
            == table["majority_formation_status_10m"].astype(str)
        )
    )
    complete_products = assignment.is_file() and ten_m.is_file()
    table["variant_record_status"] = "complete" if complete_products else "partial"
    table["updated_utc"] = utc_now()
    for column in VARIANT_COLUMNS:
        if column not in table.columns:
            table[column] = pd.NA
    return table[VARIANT_COLUMNS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        base, variants = prepare(args.config)
        settings = base["lrt_variants"]
        primary = str(settings["primary_suffix"])
        output_csv = Path(settings["master_csv"])
        output_parquet = Path(settings["master_parquet"])
        summary_json = Path(settings["master_summary_json"])
        part_dir = Path(settings["output_root"]) / "_master_parts"
        metadata = load_metadata(base)
        parts: list[Path] = []
        rebuilt: list[str] = []

        for variant in variants:
            config = json.loads(variant.config_path.read_text(encoding="utf-8"))
            assignment = Path(config["point_lrt_assignment"]["output_csv"])
            ten_m = Path(config["susi_10m_products"]["final_parquet"])
            part = part_dir / f"{variant.suffix}.parquet"
            state_path = part_dir / f"{variant.suffix}.state.json"
            expected_state = {
                "source_gpkg": fingerprint(variant.source_gpkg),
                "assignment_100m": fingerprint(assignment),
                "formation_10m": fingerprint(ten_m),
                "metadata": fingerprint(Path(base["point_lrt_assignment"]["metadata_csv"])),
            }
            previous = {}
            if state_path.is_file():
                previous = json.loads(state_path.read_text(encoding="utf-8"))
            if args.force or not part.is_file() or previous != expected_state:
                rows = build_variant_rows(
                    metadata,
                    config,
                    variant.suffix,
                    primary,
                    variant.source_gpkg,
                )
                write_parquet_atomic(rows, part)
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(
                    json.dumps(expected_state, indent=2) + "\n",
                    encoding="utf-8",
                )
                rebuilt.append(variant.suffix)
            parts.append(part)

        if not rebuilt and output_csv.is_file() and output_parquet.is_file():
            print("Formation variant master table skipped: all parts are current.")
            return 0

        combined = pd.concat(
            [pd.read_parquet(path) for path in parts],
            ignore_index=True,
        )
        combined = combined.sort_values(
            ["dawn_chorus_id", "lrt_variant"],
            key=lambda values: (
                pd.to_numeric(values, errors="coerce")
                if values.name == "dawn_chorus_id"
                else values.astype(str)
            ),
        ).reset_index(drop=True)
        write_csv_atomic(combined, output_csv)
        write_parquet_atomic(combined, output_parquet)
        summary = {
            "created_utc": utc_now(),
            "primary_suffix": primary,
            "variant_count": len(variants),
            "row_count": len(combined),
            "recording_count": int(combined["dawn_chorus_id"].nunique()),
            "rebuilt_variants": rebuilt,
            "complete_variant_products": int(
                combined.groupby("lrt_variant")[[
                    "variant_100m_product_exists",
                    "variant_10m_product_exists",
                ]].all().all(axis=1).sum()
            ),
            "output_csv": str(output_csv),
            "output_parquet": str(output_parquet),
        }
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Formation variants : {len(variants)}")
        print(f"Rows               : {len(combined):,}")
        print(f"CSV                : {output_csv}")
        print(f"Parquet            : {output_parquet}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 7_1 formation variant table: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

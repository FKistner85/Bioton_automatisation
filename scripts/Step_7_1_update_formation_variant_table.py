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
from common import workflow_run_id

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from step2_variants import prepare


VARIANT_COLUMNS = [
    "dawn_chorus_id",
    "lrt_variant",
    "lrt_variant_is_primary",
    "source_gpkg",
    "step_2_0_status",
    "step_2_1_status",
    "step_2_2_status",
    "step_2_3_status",
    "step_2_4_status",
    "variant_100m_product_exists",
    "variant_10m_product_exists",
    "variant_products_complete",
    "variant_issue_codes",
    "variant_row_count",
    "variant_complete_recording_count",
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


def read_state(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, "missing_state"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}, "invalid_state"
    if not isinstance(payload, dict):
        return {}, "invalid_state"
    return payload, None


def file_ready(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def inspect_variant_stages(config: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    susi_100m = (
        Path(config["lrt_grid_merge"]["susi_compatible_outputs"]["output_dir"])
        / "Formation_Status_Grid_withLRTCode.parquet"
    )
    definitions: dict[str, tuple[Path, list[Path]]] = {
        "2_0": (
            Path(config["lrt_cleaning"]["state_file"]),
            [Path(config["lrt_cleaning"]["output_gpkg"])],
        ),
        "2_1": (
            Path(config["lrt_grid_merge"]["state_file"]),
            [Path(config["lrt_grid_merge"]["output_grid_parquet"]), susi_100m],
        ),
        "2_2": (
            Path(config["point_lrt_assignment"]["state_file"]),
            [Path(config["point_lrt_assignment"]["output_csv"])],
        ),
        "2_3": (
            Path(config["lrt_grid_aggregation"]["state_file"]),
            [],
        ),
        "2_4": (
            Path(config["susi_10m_products"]["state_file"]),
            [Path(config["susi_10m_products"]["final_parquet"])],
        ),
    }
    statuses: dict[str, str] = {}
    issues: list[str] = []
    for stage, (state_path, outputs) in definitions.items():
        state, state_issue = read_state(state_path)
        if state_issue:
            statuses[stage] = "not_started" if state_issue == "missing_state" else "invalid"
            issues.append(f"step_{stage}:{state_issue}")
            continue
        explicit = str(state.get("status", "")).strip().lower()
        if explicit and explicit != "complete":
            statuses[stage] = explicit
            issues.append(f"step_{stage}:state_{explicit}")
            continue
        if stage == "2_3":
            state_outputs = [Path(value) for value in state.get("outputs", []) if value]
            if not state_outputs:
                statuses[stage] = "partial"
                issues.append("step_2_3:missing_output_manifest")
                continue
            outputs.extend(state_outputs)
        missing = [str(path) for path in outputs if not file_ready(path)]
        if missing:
            statuses[stage] = "partial"
            issues.append(f"step_{stage}:missing_or_empty_output")
            continue
        statuses[stage] = "complete"
    return statuses, issues


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
    statuses, issues = inspect_variant_stages(config)
    for stage, status in statuses.items():
        table[f"step_{stage}_status"] = status
    table["variant_100m_product_exists"] = file_ready(assignment)
    table["variant_10m_product_exists"] = file_ready(ten_m)
    products_complete = all(status == "complete" for status in statuses.values())
    table["variant_products_complete"] = products_complete
    table["variant_issue_codes"] = ";".join(issues)
    row_count = len(table)
    table["variant_row_count"] = row_count
    complete_ids = int(table["dawn_chorus_id"].nunique()) if products_complete else 0
    table["variant_complete_recording_count"] = complete_ids
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
    if products_complete:
        record_status = "complete"
    elif any(status == "in_progress" for status in statuses.values()):
        record_status = "in_progress"
    elif any(status == "complete" for status in statuses.values()):
        record_status = "partial"
    else:
        record_status = "not_started"
    table["variant_record_status"] = record_status
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
        variant_summary_csv = Path(
            settings.get(
                "variant_summary_csv",
                output_csv.parent / "Bio_O_Ton_Variant_Summary.csv",
            )
        )
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
                "stage_states": {
                    stage: fingerprint(Path(config[section]["state_file"]))
                    for stage, section in {
                        "2_0": "lrt_cleaning",
                        "2_1": "lrt_grid_merge",
                        "2_2": "point_lrt_assignment",
                        "2_3": "lrt_grid_aggregation",
                        "2_4": "susi_10m_products",
                    }.items()
                },
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

        # Per-variant summary: one row per variant with key counts
        variant_stats = (
            combined.groupby("lrt_variant", sort=False)
            .agg(
                source_gpkg=("source_gpkg", "first"),
                is_primary=("lrt_variant_is_primary", "first"),
                row_count=("dawn_chorus_id", "count"),
                recording_count=("dawn_chorus_id", "nunique"),
                complete_recording_count=("variant_complete_recording_count", "first"),
                step_2_0_status=("step_2_0_status", "first"),
                step_2_1_status=("step_2_1_status", "first"),
                step_2_2_status=("step_2_2_status", "first"),
                step_2_3_status=("step_2_3_status", "first"),
                step_2_4_status=("step_2_4_status", "first"),
                product_100m_exists=("variant_100m_product_exists", "first"),
                product_10m_exists=("variant_10m_product_exists", "first"),
                products_complete=("variant_products_complete", "first"),
                issue_codes=("variant_issue_codes", "first"),
                record_status=("variant_record_status", "first"),
            )
            .reset_index()
            .rename(columns={"lrt_variant": "suffix"})
        )
        variant_stats["computed_at"] = utc_now()
        variant_stats["workflow_run_id"] = workflow_run_id()
        write_csv_atomic(variant_stats, variant_summary_csv)
        summary = {
            "created_utc": utc_now(),
            "primary_suffix": primary,
            "variant_count": len(variants),
            "row_count": len(combined),
            "recording_count": int(combined["dawn_chorus_id"].nunique()),
            "rebuilt_variants": rebuilt,
            "complete_variant_products": int(
                combined.groupby("lrt_variant")["variant_products_complete"].all().sum()
            ),
            "workflow_run_id": workflow_run_id(),
            "output_csv": str(output_csv),
            "output_parquet": str(output_parquet),
            "variant_summary_csv": str(variant_summary_csv),
        }
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Formation variants : {len(variants)}")
        print(f"Rows               : {len(combined):,}")
        print(f"CSV                : {output_csv}")
        print(f"Parquet            : {output_parquet}")
        print(f"Variant summary    : {variant_summary_csv}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 7_1 formation variant table: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

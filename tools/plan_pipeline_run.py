#!/usr/bin/env python3
"""Build a deterministic workflow plan from sources, state and master status."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_csv, atomic_write_json, file_fingerprint, load_config, processed_root_from_config, utc_now_iso
from bioacoustics_common import configured_models, model_fingerprint


FINGERPRINT_GROUPS = {
    "metadata_fingerprint": ["id", "lat", "lng", "datetime", "localtimes"],
    "audio_fingerprint": ["id", "audio"],
    "photo_fingerprint": ["id", "photo"],
    "weather_fingerprint": ["id", "lat", "lng", "datetime", "localtimes"],
    "sentinel_fingerprint": ["id", "lat", "lng"],
}
FULL_REBUILD_STEPS = [
    "step_1_metadata",
    "step_2_0_lrt_cleaning",
    "step_2_1_100m_formation",
    "step_2_2_point_assignment",
    "step_2_3_grid_aggregation",
    "step_2_4_10m_formation",
    "step_3_0_audio_inventory",
    "step_3_0_audio_inventory_post",
    "step_3_0_photo_inventory",
    "step_3_1_audio_download",
    "step_3_1_photo_download",
    "step_4_1_sentinel2_mirror",
    "step_4_0_sentinel2_inventory",
    "step_5_1_weather_inventory",
    "step_5_2_weather_download",
    "step_5_3_hostrada_monthly",
    "step_5_4_hostrada_rasters",
    "step_5_5_hostrada_raster_qc",
    "step_6_0_bioacoustic_model_preflight",
    "step_6_1_bioacoustic_worklist",
    "step_6_2_bioacoustic_embeddings",
    "step_6_3_species_predictions",
    "step_6_4_germany_taxonomy_filter",
    "step_6_5_bioacoustic_aggregation",
    "step_6_6_bioacoustic_qc",
    "step_7_0_master_table",
]


def normalise_id(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "" if pd.isna(numeric) else str(int(numeric))


def canonical(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value).strip()


def hash_values(row: pd.Series, columns: Iterable[str]) -> str:
    payload = "\x1f".join(f"{column}={canonical(row.get(column, ''))}" for column in columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    if len(frame.columns) == 1:
        alternate = pd.read_csv(path, sep=";", low_memory=False, encoding="utf-8-sig")
        if len(alternate.columns) > 1:
            frame = alternate
    if "id" not in frame.columns:
        raise KeyError(f"Missing id column in {path}")
    frame = frame.copy()
    frame["dawn_chorus_id"] = frame["id"].map(normalise_id)
    frame = frame[frame["dawn_chorus_id"] != ""]
    return frame.drop_duplicates("dawn_chorus_id", keep="first").reset_index(drop=True)


def build_fingerprints(
    source: pd.DataFrame,
    *,
    timezone: str = "Europe/Berlin",
) -> pd.DataFrame:
    result = pd.DataFrame({"dawn_chorus_id": source["dawn_chorus_id"].astype(str)})
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
            result[name] = source.apply(lambda row: hash_values(row, columns), axis=1)
    source_columns = sorted(set(column for columns in FINGERPRINT_GROUPS.values() for column in columns))
    result["source_fingerprint"] = source.apply(lambda row: hash_values(row, source_columns), axis=1)
    return result


def fingerprint_path(config: dict[str, Any]) -> Path:
    section = config.get("metadata_extraction", {})
    configured = section.get("fingerprint_csv")
    if configured:
        return Path(configured)
    return Path(config["status_dir"]) / "metadata_source_fingerprints.csv"


def read_previous_fingerprints(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["dawn_chorus_id", *FINGERPRINT_GROUPS, "source_fingerprint"])
    frame = pd.read_csv(path, dtype={"dawn_chorus_id": "string"}, low_memory=False)
    id_column = "dawn_chorus_id" if "dawn_chorus_id" in frame.columns else "id"
    frame["dawn_chorus_id"] = frame[id_column].map(normalise_id)
    return frame[frame["dawn_chorus_id"] != ""].drop_duplicates("dawn_chorus_id", keep="last")


def changed_ids(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    column: str,
) -> tuple[set[str], set[str], set[str]]:
    current_map = dict(zip(current["dawn_chorus_id"], current[column]))
    previous_map = dict(zip(previous["dawn_chorus_id"], previous.get(column, pd.Series(dtype=str))))
    new = set(current_map) - set(previous_map)
    deleted = set(previous_map) - set(current_map)
    changed = {
        dawn_id
        for dawn_id in set(current_map) & set(previous_map)
        if str(current_map[dawn_id]) != str(previous_map[dawn_id])
    }
    return new, changed, deleted


def read_master(config: dict[str, Any]) -> pd.DataFrame:
    path = Path(config.get("master_table", {}).get("output_csv", ""))
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False, dtype={"dawn_chorus_id": "string"})
    frame["dawn_chorus_id"] = frame["dawn_chorus_id"].map(normalise_id)
    return frame[frame["dawn_chorus_id"] != ""]


def truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def master_problem_ids(master: pd.DataFrame, prefix: str) -> set[str]:
    if master.empty:
        return set()
    status_column = f"{prefix}_status"
    if status_column in master.columns:
        problem = ~master[status_column].astype(str).isin({"complete", "validated", "approved", "not_applicable"})
        return set(master.loc[problem, "dawn_chorus_id"].astype(str))
    exists_column = f"{prefix}_exists"
    issue_column = f"{prefix}_has_issues"
    problem = pd.Series(False, index=master.index)
    if exists_column in master.columns:
        problem |= ~truthy(master[exists_column])
    if issue_column in master.columns:
        problem |= truthy(master[issue_column])
    return set(master.loc[problem, "dawn_chorus_id"].astype(str))


def inventory_problem_ids(path: Path) -> set[str]:
    """Read IDs marked missing/problematic by a compact inventory CSV."""
    if not path.is_file() or path.stat().st_size == 0:
        return set()
    try:
        frame = pd.read_csv(path, low_memory=False, dtype=str)
    except Exception:
        return set()
    id_column = next(
        (name for name in ("dawn_chorus_id", "id", "ID") if name in frame.columns),
        None,
    )
    if id_column is None:
        return set()
    exists_column = next(
        (name for name in ("weather_exists", "exists") if name in frame.columns),
        None,
    )
    issue_column = next(
        (
            name
            for name in ("weather_has_issues", "has_issues")
            if name in frame.columns
        ),
        None,
    )
    status_column = next(
        (name for name in ("weather_status", "status") if name in frame.columns),
        None,
    )
    problem = pd.Series(False, index=frame.index)
    if exists_column:
        problem |= ~truthy(frame[exists_column])
    if issue_column:
        problem |= truthy(frame[issue_column])
    if status_column:
        healthy = {"complete", "validated", "approved", "ok", "not_applicable"}
        problem |= ~frame[status_column].fillna("").str.strip().str.lower().isin(healthy)
    if not any((exists_column, issue_column, status_column)):
        return set()
    return {
        dawn_id
        for dawn_id in frame.loc[problem, id_column].map(normalise_id)
        if dawn_id
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def fingerprint_matches(current_path: Path, previous: dict[str, Any]) -> bool:
    current = file_fingerprint(current_path)
    if not current.get("exists") or not previous.get("exists", True):
        return False
    for key in ("size_bytes", "mtime_ns", "edge_sha256"):
        if key in previous and current.get(key) != previous.get(key):
            return False
    return True


def step20_needed(config: dict[str, Any]) -> tuple[bool, list[str]]:
    section = config["lrt_cleaning"]
    output = Path(section["output_gpkg"])
    state_path = Path(section["state_file"])
    reasons: list[str] = []
    if not output.is_file():
        reasons.append("missing_output")
    state = read_json(state_path)
    if not state:
        reasons.append("missing_or_invalid_state")
    else:
        old_inputs = state.get("inputs", {})
        for raw in section["source_gpkgs"]:
            path = Path(raw)
            if not fingerprint_matches(path, old_inputs.get(str(path), {})):
                reasons.append(f"changed_input:{path.name}")
        expected_processing = {
            "output_gpkg": str(output.resolve()),
            "output_layer": section.get("output_layer", "lrt"),
            "target_crs": int(section.get("target_crs", 3035)),
            "eps_area": float(section.get("eps_area", 1.0)),
            "formation_definition": "table_2026_08_03_coastal_v2",
        }
        if state.get("processing") != expected_processing:
            reasons.append("changed_processing_config")
    return bool(reasons), reasons


def step21_needed(config: dict[str, Any], upstream: bool) -> tuple[bool, list[str]]:
    section = config["lrt_grid_merge"]
    reasons = ["upstream_lrt_changed"] if upstream else []
    for key in ["output_csv", "output_grid_gpkg", "output_grid_parquet", "state_file"]:
        if not Path(section[key]).is_file():
            reasons.append(f"missing:{key}")
    state = read_json(Path(section["state_file"]))
    inputs = state.get("inputs", {})
    for key, label in [("grid_gpkg", "grid_gpkg"), ("lrt_gpkg", "lrt_gpkg")]:
        if not fingerprint_matches(Path(section[key]), inputs.get(label, {})):
            reasons.append(f"changed_input:{key}")
    processing = state.get("processing", {})
    compatible = section.get("susi_compatible_outputs", {})
    expected_processing = {
        "grid_layer": section.get("grid_layer", "grid"),
        "grid_id_column": section.get("grid_id_column", "grid_id"),
        "lrt_layer": section.get("lrt_layer", "lrt"),
        "chunk_size": int(section.get("chunk_size", 100000)),
        "cell_area_m2": float(section.get("cell_area_m2", 10000)),
        "disputed_threshold_pct": float(section.get("disputed_threshold_pct", 2.0)),
        "output_csv": str(Path(section["output_csv"]).resolve()),
        "output_grid_gpkg": str(Path(section["output_grid_gpkg"]).resolve()),
        "output_grid_parquet": str(Path(section["output_grid_parquet"]).resolve()),
        "output_grid_layer": section.get("output_grid_layer", "majority_formation_100m"),
        "susi_matrix_schema_version": "2026-08-03-centi-percent-abck-coastal-v3",
        "susi_compatible_outputs": {
            "enabled": bool(compatible.get("enabled", True)),
            "output_dir": str(Path(compatible["output_dir"]).resolve()),
            "write_intersections_csv": bool(compatible.get("write_intersections_csv", True)),
        },
    }
    output_parquet = section.get("output_parquet")
    expected_processing["output_parquet"] = (
        str(Path(output_parquet).resolve()) if output_parquet else None
    )
    for key, value in expected_processing.items():
        if processing.get(key) != value:
            reasons.append(f"changed_processing_config:{key}")
    return bool(reasons), list(dict.fromkeys(reasons))


def step23_needed(config: dict[str, Any], upstream: bool) -> tuple[bool, list[str]]:
    section = config["lrt_grid_aggregation"]
    source = Path(section["source_parquet"])
    state_path = Path(section["state_file"])
    output_dir = Path(section["output_dir"])
    resolutions = [int(value) for value in section.get("resolutions_m", [1000, 5000, 10000])]
    reasons = ["upstream_100m_changed"] if upstream else []
    expected_outputs: list[Path] = []
    for resolution in resolutions:
        label = f"{resolution // 1000}km"
        expected_outputs.extend(
            [
                output_dir / f"majority_formation_grid_{label}.csv",
                output_dir / f"majority_formation_grid_{label}_class_counts.csv",
            ]
        )
    if any(not path.is_file() or path.stat().st_size == 0 for path in expected_outputs):
        reasons.append("missing_output")
    state = read_json(state_path)
    if not state:
        reasons.append("missing_or_invalid_state")
    else:
        if not fingerprint_matches(source, state.get("input", {})):
            reasons.append("changed_input:source_parquet")
        expected_processing = {
            "resolutions_m": resolutions,
            "schema_version": "notebook_exact_v2",
        }
        if state.get("processing") != expected_processing:
            reasons.append("changed_processing_config")
    return bool(reasons), list(dict.fromkeys(reasons))


def step24_needed(config: dict[str, Any], upstream: bool) -> tuple[bool, list[str]]:
    section = config["susi_10m_products"]
    source = Path(section["source_100m_parquet"])
    lrt = Path(section["lrt_gpkg"])
    final = Path(section["final_parquet"])
    state_path = Path(section["state_file"])
    reasons = ["upstream_100m_changed"] if upstream else []
    if not final.is_file() or final.stat().st_size == 0:
        reasons.append("missing_output")
    state = read_json(state_path)
    if not state:
        reasons.append("missing_or_invalid_state")
    else:
        inputs = state.get("inputs", {})
        if not fingerprint_matches(source, inputs.get("source_100m_parquet", {})):
            reasons.append("changed_input:source_100m_parquet")
        if not fingerprint_matches(lrt, inputs.get("lrt_gpkg", {})):
            reasons.append("changed_input:lrt_gpkg")
        expected_processing = {
            "chunk_size_100m": int(section.get("chunk_size_100m", 1000)),
            "output_dir": str(Path(section["output_dir"]).resolve()),
            "final_parquet": str(final.resolve()),
            "susi_matrix_schema_version": "2026-08-03-centi-percent-abck-coastal-v3",
        }
        if state.get("processing") != expected_processing:
            reasons.append("changed_processing_config")
        if state.get("status") ÷Î-¢G§²ÚîÆ­yÙd = str(state["generation_id"])
        marker_dir = Path(state["marker_dir"])
        runs = [str(value) for value in state.get("workflow_runs", [])]
        if workflow_run_id not in runs:
            runs.append(workflow_run_id)
        state["workflow_runs"] = runs
        state["last_resumed_utc"] = utc_now_iso()

    marker_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_path, state)
    completed_steps = {
        step
        for step in expected_steps
        if (marker_dir / f"{step}.json").is_file()
    }
    return {
        "generation_id": generation_id,
        "resume": resume,
        "state_file": str(state_path),
        "marker_dir": str(marker_dir),
        "required_steps": expected_steps,
        "completed_steps": sorted(completed_steps),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=["add_new_ids", "from_scratch"], default="add_new_ids")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    source_path = Path(config["dawn_chorus_csv"])
    source = read_source(source_path)
    timezone = str(
        config.get("metadata_extraction", {}).get(
            "timezone",
            "Europe/Berlin",
        )
    )
    current = build_fingerprints(source, timezone=timezone)
    previous_path = fingerprint_path(config)
    previous = read_previous_fingerprints(previous_path)
    master = read_master(config)
    full_rebuild = (
        full_rebuild_context(config, args.run_id)
        if args.mode == "from_scratch"
        else {}
    )

    changes: dict[str, tuple[set[str], set[str], set[str]]] = {
        column: changed_ids(current, previous, column)
        for column in ["source_fingerprint", *FINGERPRINT_GROUPS]
    }
    all_current = set(current["dawn_chorus_id"].astype(str))
    all_previous = set(previous["dawn_chorus_id"].astype(str))
    deleted = all_previous - all_current

    id_reasons: dict[str, dict[str, set[str]]] = {
        name: {}
        for name in [
            "metadata",
            "point_assignment",
            "audio",
            "photo",
            "sentinel",
            "weather",
            "bioacoustic",
        ]
    }
    for group, target in [
        ("source_fingerprint", "metadata"),
        ("metadata_fingerprint", "metadata"),
        ("metadata_fingerprint", "point_assignment"),
        ("audio_fingerprint", "audio"),
        ("audio_fingerprint", "bioacoustic"),
        ("photo_fingerprint", "photo"),
        ("sentinel_fingerprint", "sentinel"),
        ("weather_fingerprint", "weather"),
    ]:
        new, changed, removed = changes[group]
        add_reason(id_reasons[target], new, "new_id")
        add_reason(id_reasons[target], changed, f"changed:{group}")
        add_reason(id_reasons[target], removed, "deleted_id")

    for prefix, target in [
        ("sound", "audio"),
        ("photo", "photo"),
        ("sentinel", "sentinel"),
        ("weather_point", "weather"),
        ("bioacoustic", "bioacoustic"),
    ]:
        add_reason(id_reasons[target], master_problem_ids(master, prefix), f"master:{prefix}_problem")

    weather_inventory_path = Path(
        str(config.get("weather_inventory", {}).get("compact_log", ""))
    )
    add_reason(
        id_reasons["weather"],
        inventory_problem_ids(weather_inventory_path) & all_current,
        "inventory:weather_problem",
    )

    bio_section = config.get("bioacoustics", {})
    bio_enabled = bool(bio_section.get("enabled", True))
    bio_qc_path = Path(str(bio_section.get("qc_compact_csv", "")))
    if bio_enabled and (
        master.empty
        or "bioacoustic_status" not in master.columns
        or not bio_qc_path.is_file()
        or bio_qc_path.stat().st_size == 0
    ):
        add_reason(
            id_reasons["bioacoustic"],
            all_current,
            "missing_bioacoustic_baseline",
        )

    registry_path = Path(str(bio_section.get("model_registry_json", "")))
    previous_model_fingerprints: dict[str, str] = {}
    registry_required_models_healthy = False
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            previous_model_fingerprints = {
                str(model.get("name")): str(model.get("model_fingerprint"))
                for model in registry.get("models", [])
                if model.get("name") and model.get("model_fingerprint")
            }
            registry_models = {
                str(model.get("name")): str(model.get("initialisation", ""))
                for model in registry.get("models", [])
                if model.get("name")
            }
            registry_required_models_healthy = all(
                registry_models.get(model["name"], "").lower() == "ok"
                for model in configured_models(config)
                if model["required"]
            )
        except (OSError, json.JSONDecodeError):
            previous_model_fingerprints = {}
    current_model_fingerprints = (
        {
            model["name"]: model_fingerprint(config, model)
            for model in configured_models(config)
        }
        if bio_enabled
        else {}
    )
    bio_model_changed = (
        bio_enabled
        and previous_model_fingerprints != current_model_fingerprints
    )
    bio_required_model_unavailable = bio_enabled and not registry_required_models_healthy
    if bio_model_changed:
        add_reason(
            id_reasons["bioacoustic"],
            all_current,
            "bioacoustic_model_or_runtime_changed",
        )

    taxonomy_path = Path(str(bio_section.get("taxonomy_allowlist_csv", "")))
    taxonomy_state_path = Path(str(bio_section.get("taxonomy_state_json", "")))
    previous_taxonomy_fingerprint: dict[str, Any] = {}
    if taxonomy_state_path.is_file():
        try:
            taxonomy_state = json.loads(taxonomy_state_path.read_text(encoding="utf-8"))
            previous_taxonomy_fingerprint = taxonomy_state.get(
                "allowlist_fingerprint",
                {},
            )
        except (OSError, json.JSONDecodeError):
            previous_taxonomy_fingerprint = {}
    current_taxonomy_fingerprint = (
        file_fingerprint(taxonomy_path) if taxonomy_path.is_file() else {}
    )
    bio_taxonomy_changed = (
        bio_enabled
        and previous_taxonomy_fingerprint != current_taxonomy_fingerprint
    )
    bio_metadata_changed = bio_enabled and bool(
        changes["metadata_fingerprint"][0]
        | changes["metadata_fingerprint"][1]
        | changes["metadata_fingerprint"][2]
    )
    bio_postprocess_needed = (
        bool(id_reasons["bioacoustic"])
        or bio_taxonomy_changed
        or bio_metadata_changed
    )

    step1_outputs = [
        Path(config["status_dir"]) / "dawnchorus_metadata_clean.csv",
        Path(config["status_dir"]) / "dawnchorus_metadata_log.csv",
        previous_path,
    ]
    if any(not path.is_file() or path.stat().st_size == 0 for path in step1_outputs):
        add_reason(
            id_reasons["metadata"],
            all_current | deleted,
            "missing_step1_output",
        )

    if args.mode == "from_scratch":
        for target in id_reasons:
            add_reason(id_reasons[target], all_current | deleted, "from_scratch")

    run_root_cfg = config.get("pipeline_control", {}).get("run_plan_dir")
    run_root = Path(run_root_cfg) if run_root_cfg else processed_root_from_config(config) / "step_0_control" / "run_plans"
    run_dir = run_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    id_files: dict[str, str] = {}
    for name, reasons in id_reasons.items():
        path = run_dir / f"{name}_ids.csv"
        write_id_file(path, reasons)
        id_files[name] = str(path)

    if args.mode == "from_scratch":
        run20, reasons20 = True, ["from_scratch"]
        run21, reasons21 = True, ["from_scratch"]
    else:
        run20, reasons20 = step20_needed(config)
        run21, reasons21 = step21_needed(config, run20)

    point_ids = set(id_reasons["point_assignment"])
    if run21:
        point_ids = all_current | deleted
        add_reason(id_reasons["point_assignment"], point_ids, "upstream_formation_changed")
        write_id_file(Path(id_files["point_assignment"]), id_reasons["point_assignment"])

    point_output = Path(config["point_lrt_assignment"]["output_csv"])
    run22 = bool(point_ids) or run21 or not point_output.is_file()
    if args.mode == "from_scratch":
        run23, reasons23 = True, ["from_scratch"]
        run24, reasons24 = True, ["from_scratch"]
    else:
        run23, reasons23 = step23_needed(config, run21)
        run24, reasons24 = step24_needed(config, run21)

    steps = {
        "step_1_metadata": {
            "run": bool(id_reasons["metadata"]),
            "reasons": ["source_rows_changed"] if id_reasons["metadata"] else [],
            "ids_file": id_files["metadata"],
        },
        "step_2_0_lrt_cleaning": {"run": run20, "reasons": reasons20},
        "step_2_1_100m_formation": {"run": run21, "reasons": reasons21},
        "step_2_2_point_assignment": {
            "run": run22,
            "reasons": ["affected_point_ids"] if point_ids else ["missing_output"],
            "ids_file": id_files["point_assignment"],
        },
        "step_2_3_grid_aggregation": {"run": run23, "reasons": reasons23},
        "step_2_4_10m_formation": {"run": run24, "reasons": reasons24},
        "step_3_0_audio_inventory": {"run": True, "reasons": ["filesystem_reconciliation"]},
        "step_3_0_photo_inventory": {"run": True, "reasons": ["filesystem_reconciliation"]},
        "step_3_1_audio_download": {
            "run": True,
            "reasons": ["fresh_inventory_selection"],
            "ids_file": id_files["audio"],
        },
        "step_3_0_audio_inventory_post": {
            "run": True,
            "reasons": ["post_download_filesystem_reconciliation"],
        },
        "step_3_1_photo_download": {
            "run": True,
            "reasons": ["fresh_inventory_selection"],
            "ids_file": id_files["photo"],
        },
        "step_4_1_sentinel2_mirror": {
            "run": True,
            "reasons": ["remote_drive_reconciliation"],
            "ids_file": id_files["sentinel"],
        },
        "step_4_0_sentinel2_inventory": {"run": True, "reasons": ["filesystem_reconciliation"]},
        "step_5_1_weather_inventory": {"run": True, "reasons": ["filesystem_reconciliation"]},
        "step_5_2_weather_download": {
            "run": True,
            "reasons": ["fresh_inventory_selection"],
            "ids_file": id_files["weather"],
        },
        "step_5_3_hostrada_monthly": {
            "run": True,
            "reasons": ["remote_monthly_reconciliation"],
        },
        "step_5_4_hostrada_rasters": {
            "run": True,
            "reasons": ["checkpointed_raster_reconciliation"],
        },
        "step_5_5_hostrada_raster_qc": {
            "run": True,
            "reasons": ["incremental_raster_quality_reconciliation"],
        },
        "step_6_0_bioacoustic_model_preflight": {
            "run": bio_enabled and (
                bio_model_changed
                or not registry_path.is_file()
                or bio_required_model_unavailable
            ),
            "reasons": (
                [
                    "bacpipe_environment_or_model_registry_changed"
                    if bio_model_changed or not registry_path.is_file()
                    else "required_bioacoustic_model_unavailable"
                ]
                if bio_model_changed or not registry_path.is_file() or bio_required_model_unavailable
                else []
            ),
        },
        "step_6_1_bioacoustic_worklist": {
            "run": bio_enabled and bool(id_reasons["bioacoustic"]),
            "reasons": ["affected_audio_ids"] if id_reasons["bioacoustic"] else [],
            "ids_file": id_files["bioacoustic"],
        },
        "step_6_2_bioacoustic_embeddings": {
            "run": bio_enabled and bool(id_reasons["bioacoustic"]),
            "reasons": ["affected_recording_model_rows"] if id_reasons["bioacoustic"] else [],
            "ids_file": id_files["bioacoustic"],
        },
        "step_6_3_species_predictions": {
            "run": bio_enabled and bool(id_reasons["bioacoustic"]),
            "reasons": ["new_native_predictions"] if id_reasons["bioacoustic"] else [],
        },
        "step_6_4_germany_taxonomy_filter": {
            "run": bio_enabled and bio_postprocess_needed,
            "reasons": (
                ["new_predictions_or_taxonomy_or_metadata"]
                if bio_postprocess_needed
                else []
            ),
        },
        "step_6_5_bioacoustic_aggregation": {
            "run": bio_enabled and bio_postprocess_needed,
            "reasons": ["new_filtered_predictions"] if bio_postprocess_needed else [],
        },
        "step_6_6_bioacoustic_qc": {
            "run": bio_enabled and bio_postprocess_needed,
            "reasons": ["bioacoustic_reconciliation"] if bio_postprocess_needed else [],
        },
        "step_7_0_master_table": {"run": True, "reasons": ["final_status_snapshot"]},
        "final_validation": {"run": True, "reasons": ["workflow_gate"]},
    }
    if full_rebuild:
        completed = set(full_rebuild["completed_steps"])
        for step in FULL_REBUILD_STEPS:
            if step == "step_7_0_master_table":
                continue
            if step in completed and step in steps:
                steps[step]["run"] = False
                steps[step]["reasons"] = ["completed_in_full_rebuild_generation"]
    plan = {
        "schema_version": "2026-07-23-run-plan-v1",
        "workflow_run_id": args.run_id,
        "created_utc": utc_now_iso(),
        "mode": args.mode,
        "config_path": str(args.config),
        "source": file_fingerprint(source_path),
        "previous_fingerprint_csv": str(previous_path),
        "source_id_count": len(all_current),
        "previous_id_count": len(all_previous),
        "deleted_ids": sorted(deleted, key=lambda value: int(value) if value.isdigit() else value),
        "id_files": id_files,
        "id_counts": {name: len(reasons) for name, reasons in id_reasons.items()},
        "full_rebuild": full_rebuild,
        "steps": steps,
    }
    plan_path = run_dir / "run_plan.json"
    atomic_write_json(plan_path, plan)
    print(f"Workflow run ID : {args.run_id}")
    print(f"Run plan        : {plan_path}")
    print(f"Source IDs      : {len(all_current):,}")
    print(f"Changed/new IDs : {len(id_reasons['metadata']):,}")
    print(str(plan_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

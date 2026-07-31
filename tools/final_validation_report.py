#!/usr/bin/env python3
"""Create a final validation report for the Bio-O-Ton pipeline run.

This report is intentionally lightweight: it does not rewrite data products and
does not run expensive geospatial checks. It verifies expected files/folders,
summarises central run manifests and writes a JSON plus Markdown report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_json, load_config, manifest_root, output_is_nonempty, processed_root_from_config


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def check_path(label: str, path: str | Path, required: bool = True) -> dict[str, Any]:
    p = Path(path)
    exists = p.exists()
    nonempty = output_is_nonempty(p) if exists else False
    status = "ok"
    if required and not exists:
        status = "missing"
    elif required and not nonempty:
        status = "empty"
    elif not required and not exists:
        status = "optional_missing"
    return {
        "label": label,
        "path": str(p),
        "required": required,
        "exists": exists,
        "is_file": p.is_file() if exists else False,
        "is_dir": p.is_dir() if exists else False,
        "size_bytes": int(p.stat().st_size) if exists and p.is_file() else None,
        "status": status,
    }


def expected_outputs(config: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    if config.get("status_dir"):
        checks.append(check_path("Step 1 metadata status/output directory", config["status_dir"]))
        checks.append(check_path("Step 1 clean metadata CSV", Path(config["status_dir"]) / "dawnchorus_metadata_clean.csv"))

    sections = {
        "lrt_cleaning": [
            ("Step 2_0 cleaned LRT GPKG", "output_gpkg"),
            ("Step 2_0 state", "state_file"),
        ],
        "lrt_grid_merge": [
            ("Step 2_1 majority CSV", "output_csv"),
            ("Step 2_1 majority grid GPKG", "output_grid_gpkg"),
            ("Step 2_1 majority grid parquet", "output_grid_parquet"),
            ("Step 2_1 state", "state_file"),
        ],
        "point_lrt_assignment": [
            ("Step 2_2 point assignment CSV", "output_csv"),
            ("Step 2_2 polygon matches CSV", "matches_csv"),
            ("Step 2_2 processing log CSV", "log_csv"),
            ("Step 2_2 state", "state_file"),
        ],
        "lrt_grid_aggregation": [
            ("Step 2_3 aggregation output directory", "output_dir"),
            ("Step 2_3 state", "state_file"),
        ],
        "susi_10m_products": [
            ("Step 2_4 final 10m parquet", "final_parquet"),
            ("Step 2_4 state", "state_file"),
            ("Step 2_4 parquet chunks", "parquet_chunk_dir"),
        ],
        "audio_inventory": [
            ("Step 3_0_a audio detailed inventory", "detailed_log"),
            ("Step 3_0_a audio compact inventory", "compact_log"),
            ("Step 3_0_a state", "state_file"),
        ],
        "photo_inventory": [
            ("Step 3_0_b photo detailed inventory", "detailed_log"),
            ("Step 3_0_b photo compact inventory", "compact_log"),
            ("Step 3_0_b state", "state_file"),
        ],
        "weather_inventory": [
            ("Step 5_1 weather detailed inventory", "detailed_log"),
            ("Step 5_1 weather compact inventory", "compact_log"),
            ("Step 5_1 state", "state_file"),
        ],
        "weather_download": [
            ("Step 5_2 weather output directory", "output_dir"),
            ("Step 5_2 HOSTRADA cache directory", "cache_dir"),
            ("Step 5_2 run log", "log_file"),
        ],
        "hostrada_monthly_download": [
            ("Step 5_3 NetCDF directory", "output_dir"),
            ("Step 5_3 download log", "log_csv"),
        ],
        "hostrada_raster_products": [
            ("Step 5_4 raster output root", "output_root"),
        ],
        "hostrada_raster_quality_check": [
            ("Step 5_5 raster QC output directory", "output_dir"),
        ],
        "bioacoustics": [
            ("Step 6_0 model registry", "model_registry_json"),
            ("Step 6_1 worklist parquet", "worklist_parquet"),
            ("Step 6_2 embedding directory", "embedding_dir"),
            ("Step 6_3 raw prediction directory", "raw_prediction_dir"),
            ("Step 6_4 Germany-filtered predictions", "filtered_prediction_dir"),
            ("Step 6_5 recording summary", "recording_summary_csv"),
            ("Step 6_6 compact QC", "qc_compact_csv"),
            ("Step 6_6 detailed QC", "qc_detailed_csv"),
        ],
        "master_table": [
            ("Step 7_0 master table CSV", "output_csv"),
            ("Step 7_0 master table parquet", "output_parquet"),
            ("Step 7_0 master table summary", "summary_json"),
        ],
    }
    for section_name, fields in sections.items():
        section = config.get(section_name, {})
        required = True
        if section_name in {
            "hostrada_monthly_download",
            "hostrada_raster_products",
            "hostrada_raster_quality_check",
        }:
            required = bool(
                config.get("final_validation", {}).get(
                    "require_weather_raster_100m",
                    False,
                )
            )
        elif section_name == "bioacoustics":
            required = bool(section.get("enabled", True))
        for label, key in fields:
            if key in section:
                checks.append(check_path(label, section[key], required=required))

    susi_outputs = config.get("lrt_grid_merge", {}).get("susi_compatible_outputs", {})
    if susi_outputs.get("enabled") and susi_outputs.get("output_dir"):
        out_dir = Path(susi_outputs["output_dir"])
        checks.append(check_path("Step 2_1 Susi-compatible output directory", out_dir))
        checks.append(check_path("Step 2_1 Susi-compatible 100m parquet", out_dir / "Formation_Status_Grid_withLRTCode.parquet"))

    for section_name, key, label in [
        ("audio_download", "retry_log", "Step 3_1_a audio download retry log"),
        ("photo_download", "retry_log", "Step 3_1_b photo download retry log"),
        ("sentinel2_inventory", "detailed_log", "Step 4_0 Sentinel2 detailed inventory"),
        ("sentinel2_inventory", "compact_log", "Step 4_0 Sentinel2 compact inventory"),
        ("sentinel2_download", "log_csv", "Step 4_1 Sentinel2 download log"),
        ("sentinel2_cleaning", "log_csv", "Step 4_2 Sentinel2 cleaning log"),
    ]:
        section = config.get(section_name, {})
        if key in section:
            checks.append(check_path(label, section[key], required=False))

    return checks


def manifest_summary(
    config: dict[str, Any],
    workflow_run_id: str = "",
) -> dict[str, Any]:
    root = manifest_root(config)
    summary: dict[str, Any] = {
        "root": str(root),
        "exists": root.exists(),
        "workflow_run_id": workflow_run_id,
        "steps": {},
    }
    if not root.exists():
        return summary
    for manifest_file in sorted(root.glob("*/*.json")):
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if workflow_run_id and str(payload.get("workflow_run_id", "")) != workflow_run_id:
            continue
        step = payload.get("step_name") or manifest_file.parent.name
        step_summary = summary["steps"].setdefault(
            step,
            {
                "runs": 0,
                "latest_status": "",
                "latest_finished_utc": "",
                "statuses": {},
                "latest_manifest": "",
            },
        )
        step_summary["runs"] += 1
        status = str(payload.get("status", "unknown"))
        step_summary["statuses"][status] = step_summary["statuses"].get(status, 0) + 1
        finished = str(payload.get("finished_utc") or payload.get("started_utc") or "")
        if finished >= step_summary["latest_finished_utc"]:
            step_summary["latest_finished_utc"] = finished
            step_summary["latest_status"] = status
            step_summary["latest_manifest"] = str(manifest_file)
    return summary


def read_run_plan() -> dict[str, Any]:
    path = os.environ.get("BIOOTON_RUN_PLAN", "").strip()
    if not path or not Path(path).is_file():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def master_readiness(config: dict[str, Any]) -> dict[str, Any]:
    path = Path(config.get("master_table", {}).get("output_csv", ""))
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file() and path.stat().st_size > 0,
        "rows": 0,
        "requirements": {},
        "critical": [],
        "policy": str(
            config.get("final_validation", {}).get(
                "readiness_policy",
                "strict",
            )
        ).strip().lower(),
    }
    if not result["exists"]:
        result["critical"].append("master_table_missing_or_empty")
        return result
    try:
        import pandas as pd

        table = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        result["critical"].append(f"master_table_read_error:{type(exc).__name__}")
        return result

    result["rows"] = int(len(table))
    settings = config.get("final_validation", {})
    strict_readiness = result["policy"] == "strict"
    requirements = [
        (
            "require_all_general_ready",
            "ready_for_general_analysis",
        ),
        (
            "require_100m_formation",
            "ready_for_formation_analysis_100m",
        ),
        (
            "require_10m_formation",
            "ready_for_formation_analysis_10m",
        ),
        (
            "require_bioacoustic_analysis",
            "ready_for_bioacoustic_analysis",
        ),
    ]
    for setting, column in requirements:
        if not settings.get(setting, False):
            continue
        if column not in table.columns:
            result["requirements"][setting] = {
                "column": column,
                "status": "missing_column",
                "not_ready": len(table),
            }
            if strict_readiness:
                result["critical"].append(f"master_missing_column:{column}")
            continue
        ready = table[column].astype(str).str.strip().str.lower().isin(
            {"true", "1", "yes", "y"}
        )
        not_ready = int((~ready).sum())
        result["requirements"][setting] = {
            "column": column,
            "status": "ok" if not_ready == 0 else "not_ready",
            "not_ready": not_ready,
        }
        if not_ready and strict_readiness:
            result["critical"].append(f"{column}_not_ready:{not_ready}")
    return result


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Bio-O-Ton Pipeline Final Validation",
        "",
        f"- Erstellt UTC: `{report['created_utc']}`",
        f"- Ergebnis: `{report['overall_status']}`",
        f"- Technischer Status: `{report['technical_status']}`",
        f"- Daten-Readiness: `{report['data_readiness_status']}`",
        f"- Freigabestatus: `{report['release_status']}`",
        f"- Workflow-Run: `{report['workflow_run_id']}`",
        f"- Kritische Probleme: `{report['critical_count']}`",
        f"- Warnungen: `{report['warning_count']}`",
        "",
        "## Erwartete Dateien und Ordner",
        "",
        "| Status | Artefakt | Pfad |",
        "|---|---|---|",
    ]
    for item in report["checks"]:
        lines.append(f"| `{item['status']}` | {item['label']} | `{item['path']}` |")

    lines.extend(["", "## Run-Manifeste", ""])
    manifests = report["manifests"]
    if not manifests["exists"]:
        lines.append(f"Keine Manifeste gefunden unter `{manifests['root']}`.")
    else:
        lines.extend(["| Step | Runs | Neuester Status | Neueste Manifestdatei |", "|---|---:|---|---|"])
        for step, item in sorted(manifests["steps"].items()):
            lines.append(
                f"| `{step}` | {item['runs']} | `{item['latest_status']}` | `{item['latest_manifest']}` |"
            )

    lines.extend(["", "## Mastertable-Readiness", ""])
    readiness = report["master_readiness"]
    lines.append(f"- Zeilen: `{readiness['rows']}`")
    lines.append(f"- Readiness-Policy: `{readiness['policy']}`")
    for setting, item in readiness["requirements"].items():
        lines.append(
            f"- `{setting}`: `{item['status']}`; nicht bereit: `{item['not_ready']}`"
        )

    if report["recommendations"]:
        lines.extend(["", "## Naechste Pruefpunkte", ""])
        for recommendation in report["recommendations"]:
            lines.append(f"- {recommendation}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create final pipeline validation report.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    validation_dir = processed_root_from_config(config) / "step_9_validation"
    stamp = now_stamp()
    run_plan = read_run_plan()
    workflow_run_id = (
        os.environ.get("BIOOTON_RUN_ID", "").strip()
        or str(run_plan.get("workflow_run_id", ""))
    )
    checks = expected_outputs(config)
    manifests = manifest_summary(config, workflow_run_id)
    readiness = master_readiness(config)
    readiness_issue_count = sum(
        1
        for item in readiness.get("requirements", {}).values()
        if item.get("status") != "ok"
    )

    critical = [
        item
        for item in checks
        if item["required"] and item["status"] in {"missing", "empty"}
    ]
    warnings = [
        item
        for item in checks
        if not item["required"] and item["status"] in {"empty", "optional_missing"}
    ]
    failed_manifest_steps = [
        step
        for step, item in manifests.get("steps", {}).items()
        if item.get("latest_status") in {"failed", "partial"}
    ]
    planned_steps = {
        step
        for step, item in run_plan.get("steps", {}).items()
        if bool(item.get("run"))
    }
    missing_planned_manifests = sorted(
        step
        for step in planned_steps
        if step not in manifests.get("steps", {})
        and step != "final_validation"
    )
    recommendations: list[str] = []
    if critical:
        recommendations.append("Kritisch fehlende/leere Pflicht-Artefakte oben zuerst klaeren.")
    if failed_manifest_steps:
        recommendations.append(
            "Neueste Manifeste mit `failed` oder `partial` pruefen: "
            + ", ".join(sorted(failed_manifest_steps))
        )
    if missing_planned_manifests:
        recommendations.append(
            "Geplante Steps ohne Manifest im aktuellen Run pruefen: "
            + ", ".join(missing_planned_manifests)
        )
    if readiness["critical"]:
        recommendations.append(
            "Mastertable-Readiness pruefen: " + ", ".join(readiness["critical"])
        )
    if not manifests["exists"]:
        recommendations.append("Einmal einen Lauf mit den neuen Manifest-Helfern starten, damit Run-Historie entsteht.")

    technical_status = "validated"
    if (
        critical
        or failed_manifest_steps
        or missing_planned_manifests
        or readiness["critical"]
    ):
        technical_status = "has_issues"
    automatic_release = bool(
        config.get("final_validation", {}).get("automatic_release", False)
    )
    data_readiness_status = (
        "ready" if readiness_issue_count == 0 else "manual_review_required"
    )
    release_status = (
        "approved"
        if (
            technical_status == "validated"
            and automatic_release
            and readiness_issue_count == 0
        )
        else (
            "manual_review_required"
            if technical_status == "validated"
            else "not_started"
        )
    )
    overall_status = technical_status

    report = {
        "schema_version": "2026-07-31-final-validation-v3",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workflow_run_id": workflow_run_id,
        "config_path": str(args.config),
        "overall_status": overall_status,
        "technical_status": technical_status,
        "data_readiness_status": data_readiness_status,
        "release_status": release_status,
        "critical_count": (
            len(critical)
            + len(failed_manifest_steps)
            + len(missing_planned_manifests)
            + len(readiness["critical"])
        ),
        "warning_count": len(warnings) + readiness_issue_count,
        "checks": checks,
        "manifests": manifests,
        "master_readiness": readiness,
        "planned_steps_without_manifest": missing_planned_manifests,
        "recommendations": recommendations,
    }
    json_path = validation_dir / f"final_validation_{stamp}.json"
    md_path = validation_dir / f"final_validation_{stamp}.md"
    atomic_write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Validation status: {overall_status}")
    print(f"JSON report       : {json_path}")
    print(f"Markdown report   : {md_path}")
    return 0 if technical_status == "validated" else 2


if __name__ == "__main__":
    raise SystemExit(main())

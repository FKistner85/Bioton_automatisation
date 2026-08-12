#!/usr/bin/env python3
"""Generate compact, static visual QA reports from pipeline outputs.

The reports deliberately use only HTML/CSS. They are fast to create on Horeka,
need no browser service or plotting package, and remain useful for partial runs.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from common import atomic_write_json, atomic_write_text, load_config


STYLE = """
<style>
:root { color-scheme: light; --ink:#17212b; --muted:#62707d; --line:#d7dde3;
  --blue:#1b6ca8; --green:#197c5b; --amber:#bb7600; --red:#b23b3b; --paper:#f6f8fa; }
* { box-sizing:border-box; } body { margin:0; font-family:Arial,sans-serif; color:var(--ink); background:var(--paper); }
header { background:#123047; color:white; padding:24px max(24px,calc((100vw - 1240px)/2)); }
header h1 { margin:0 0 6px; font-size:28px; } header p { margin:0; color:#d5e4ee; }
nav { margin-top:16px; display:flex; flex-wrap:wrap; gap:7px; } nav a { color:white; border:1px solid #7793a6; padding:5px 8px; text-decoration:none; font-size:13px; }
main { max-width:1240px; margin:0 auto; padding:22px; } section { margin:0 0 22px; }
h2 { font-size:22px; margin:0 0 10px; } h3 { font-size:15px; margin:0 0 8px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }
.card { background:white; border:1px solid var(--line); padding:13px; min-height:90px; }
.number { font-size:28px; font-weight:700; margin:7px 0 0; } .label { color:var(--muted); font-size:12px; }
.panel { background:white; border:1px solid var(--line); padding:15px; margin-top:10px; }
.bar-row { display:grid; grid-template-columns:minmax(110px,230px) 1fr 80px; gap:9px; align-items:center; margin:7px 0; font-size:13px; }
.bar { height:16px; background:#e9eef2; } .fill { height:100%; background:var(--blue); } .fill.warn { background:var(--amber); } .fill.bad { background:var(--red); } .fill.good { background:var(--green); }
table { width:100%; border-collapse:collapse; font-size:12px; } th,td { border-bottom:1px solid var(--line); padding:6px; text-align:left; } th { color:var(--muted); }
.note { color:var(--muted); font-size:13px; } .missing { color:var(--amber); font-weight:600; }
.meter { min-width:90px; background:#e9eef2; height:13px; display:inline-block; vertical-align:middle; margin-right:6px; }
.meter > span { display:block; height:100%; background:var(--blue); }
footer { color:var(--muted); font-size:12px; padding:15px 0; }
</style>
"""


def path_value(config: dict[str, Any], *keys: str) -> Path | None:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return Path(value) if value else None


def read_table(path: Path | None) -> pd.DataFrame:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def child_path(path: Path | None, name: str) -> Path | None:
    return path / name if path is not None else None


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype("string").str.lower().isin({"true", "1", "yes", "y"})


def count_values(frame: pd.DataFrame, column: str, limit: int = 10) -> dict[str, int]:
    if frame.empty or column not in frame.columns:
        return {}
    values = frame[column].fillna("missing").astype(str).value_counts(dropna=False)
    return {str(key): int(value) for key, value in values.head(limit).items()}


def card(label: str, value: int | str) -> str:
    return (
        '<div class="card"><div class="label">'
        + html.escape(label)
        + '</div><div class="number">'
        + html.escape(f"{value:,}" if isinstance(value, int) else str(value))
        + "</div></div>"
    )


def bars(counts: dict[str, int]) -> str:
    if not counts:
        return '<p class="note missing">Keine auswertbaren Daten vorhanden.</p>'
    maximum = max(counts.values()) or 1
    rows = []
    for label, value in counts.items():
        lowered = label.lower()
        color = "bad" if any(token in lowered for token in ("fail", "issue", "missing", "false")) else "good" if any(token in lowered for token in ("ok", "complete", "true", "validated")) else "warn"
        width = max(1, round(value / maximum * 100))
        rows.append(
            '<div class="bar-row"><span>' + html.escape(label) + "</span>"
            + f'<div class="bar"><div class="fill {color}" style="width:{width}%"></div></div>'
            + f"<strong>{value:,}</strong></div>"
        )
    return "".join(rows)


def preview(frame: pd.DataFrame, columns: list[str], limit: int = 8) -> str:
    selected = [column for column in columns if column in frame.columns]
    if frame.empty or not selected:
        return ""
    rows = ["<table><thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in selected) + "</tr></thead><tbody>"]
    for _, item in frame[selected].head(limit).iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(item[c]))}</td>" for c in selected) + "</tr>")
    return "".join(rows) + "</tbody></table>"


def comparison_table(frame: pd.DataFrame, label: str, metrics: list[tuple[str, str]]) -> str:
    if frame.empty or label not in frame.columns:
        return '<p class="note missing">Keine Variantensummary vorhanden.</p>'
    available = [(column, title) for column, title in metrics if column in frame.columns]
    if not available:
        return preview(frame, [label])
    maxima = {column: max(1, int(pd.to_numeric(frame[column], errors="coerce").max() or 1)) for column, _ in available}
    output = ["<table><thead><tr><th>Variante</th>" + "".join(f"<th>{html.escape(title)}</th>" for _, title in available) + "</tr></thead><tbody>"]
    for _, row in frame.iterrows():
        output.append("<tr><td>" + html.escape(str(row[label])) + "</td>")
        for column, _title in available:
            value = int(pd.to_numeric(pd.Series([row[column]]), errors="coerce").fillna(0).iloc[0])
            width = round(value / maxima[column] * 100)
            output.append(f'<td><span class="meter"><span style="width:{width}%"></span></span>{value:,}</td>')
        output.append("</tr>")
    return "".join(output) + "</tbody></table>"


def boolean_summary(frame: pd.DataFrame, exists_column: str, issue_column: str) -> tuple[dict[str, int], list[str]]:
    cards: dict[str, int] = {"rows": int(len(frame))}
    notes: list[str] = []
    resolved_exists = exists_column if exists_column in frame.columns else "exists"
    resolved_issue = issue_column if issue_column in frame.columns else "has_issues"
    if resolved_exists in frame.columns:
        exists = as_bool(frame[resolved_exists])
        cards["present"] = int(exists.sum())
        cards["missing"] = int((~exists).sum())
    if resolved_issue in frame.columns:
        issues = as_bool(frame[resolved_issue])
        cards["has issues"] = int(issues.sum())
        cards["clean"] = int((~issues).sum())
    if len(cards) == 1:
        notes.append("Erwartete Existenz-/Issue-Spalten fehlen in diesem Report.")
    return cards, notes


def section(title: str, subtitle: str, cards: dict[str, int], chart_title: str, chart: dict[str, int], table_html: str = "", notes: list[str] | None = None) -> str:
    note_html = "".join(f'<p class="note">{html.escape(note)}</p>' for note in notes or [])
    return (
        f'<section id="{title.lower().replace(" ", "_")}"><h2>{html.escape(title)}</h2>'
        f'<p class="note">{html.escape(subtitle)}</p><div class="grid">'
        + "".join(card(label, value) for label, value in cards.items())
        + f'</div><div class="panel"><h3>{html.escape(chart_title)}</h3>{bars(chart)}{table_html}{note_html}</div></section>'
    )


def page(title: str, body: str, links: list[tuple[str, str]]) -> str:
    nav = "".join(f'<a href="{html.escape(href)}">{html.escape(label)}</a>' for label, href in links)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>{STYLE}</head><body><header><h1>{html.escape(title)}</h1><p>Bio-O-Ton Pipeline: kompakte Ergebnis- und Qualitaetskontrolle</p><nav>{nav}</nav></header><main>{body}<footer>Generiert: {generated}</footer></main></body></html>"


def build_sections(config: dict[str, Any]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    metadata = read_table(path_value(config, "status_dir") / "dawnchorus_metadata_clean.csv")
    sections.append(("Step 1 Metadata", section("Step 1 Metadata", "Bereinigte Dawn-Chorus-Metadaten.", {"IDs": int(len(metadata)), "Spalten": int(len(metadata.columns))}, "Timestamp status", count_values(metadata, "timestamp_status") or count_values(metadata, "datetime_status"), preview(metadata, ["dawn_chorus_id", "datetime", "latitude", "longitude", "timestamp_status"]))))

    lrt = read_table(path_value(config, "lrt_grid_merge", "output_csv"))
    disputed = int(as_bool(lrt["majority_disputed"]).sum()) if "majority_disputed" in lrt.columns else 0
    sections.append(("Step 2 Formation", section("Step 2 Formation", "100m LRT-/Formation-Zuordnung und Majority-Entscheidungen.", {"Grid cells": int(len(lrt)), "disputed": disputed}, "Majority formations", count_values(lrt, "Majority_formation") or count_values(lrt, "majority_formation"), preview(lrt, ["grid_id", "Majority_formation", "majority_formation_status", "majority_delta", "majority_disputed"]))))

    variant_cfg = config.get("lrt_variants", {})
    variant_summary = read_table(Path(variant_cfg.get("variant_summary_csv", ""))) if variant_cfg.get("variant_summary_csv") else pd.DataFrame()
    temporal_summary = read_table(Path(variant_cfg.get("temporal_summary_csv", ""))) if variant_cfg.get("temporal_summary_csv") else pd.DataFrame()
    variant_metrics = [
        ("majority_grid_100m_count", "Majority-Grids 100m"),
        ("majority_grid_10m_count", "Majority-Grids 10m"),
        ("recordings_in_majority_grid_100m", "Recordings in 100m"),
        ("recordings_in_majority_grid_10m", "Recordings in 10m"),
        ("recordings_directly_in_lrt_polygon", "Direkt im LRT-Polygon"),
    ]
    temporal_preview = preview(
        temporal_summary.sort_values([column for column in ["recording_year", "lrt_variant"] if column in temporal_summary.columns]).tail(36),
        ["recording_year", "lrt_variant", "recording_count", "recordings_in_majority_grid_100m", "recordings_in_majority_grid_10m", "recordings_directly_in_lrt_polygon"],
        limit=36,
    )
    variant_body = comparison_table(variant_summary, "suffix", variant_metrics)
    if temporal_preview:
        variant_body += "<h3 style=\"margin-top:18px\">Zeitlicher Verlauf (letzte 36 Variante/Jahr-Zeilen)</h3>" + temporal_preview
    variant_analysis = ("Step 2 Variantenanalyse", section(
        "Step 2 Variantenanalyse",
        "Vergleich der LRT-Datensätze: verfügbare Majority-Grids und zugeordnete Recordings, inklusive direkter Polygon-Treffer.",
        {"Varianten": int(len(variant_summary)), "Jahr-Variante-Zeilen": int(len(temporal_summary))},
        "Datensatzvergleich",
        {},
        variant_body,
        ["Die Detailbasis ist die normalisierte Tabelle Recording × LRT-Variante."],
    ))

    audio = read_table(path_value(config, "audio_inventory", "compact_log"))
    photos = read_table(path_value(config, "photo_inventory", "compact_log"))
    audio_cards, audio_notes = boolean_summary(audio, "audio_exists", "audio_has_issues")
    photo_cards, photo_notes = boolean_summary(photos, "photo_exists", "photo_has_issues")
    sections.append(("Step 3 Media", section("Step 3 Media", "Audio- und Bildinventar nach Download und Sanity Checks.", {"audio rows": int(len(audio)), "photo rows": int(len(photos)), "audio issues": audio_cards.get("has issues", 0), "photo issues": photo_cards.get("has issues", 0)}, "Audio status", audio_cards, preview(audio, ["dawn_chorus_id", "audio_exists", "audio_has_issues", "issues"]), audio_notes + photo_notes + ["Bildstatus: " + ", ".join(f"{key}={value}" for key, value in photo_cards.items())])))

    sentinel = read_table(path_value(config, "sentinel2_inventory", "compact_log"))
    sentinel_cards, sentinel_notes = boolean_summary(sentinel, "sentinel_exists", "sentinel_has_issues")
    sections.append(("Step 4 Sentinel-2", section("Step 4 Sentinel-2", "Inventar der TIFs aus PointData/S2 mit S2_Scores.csv.", sentinel_cards, "Sentinel status", sentinel_cards, preview(sentinel, ["dawn_chorus_id", "sentinel_exists", "sentinel_has_issues", "sentinel_quality_score", "issues"]), sentinel_notes)))

    weather = read_table(path_value(config, "weather_inventory", "compact_log"))
    weather_cards, weather_notes = boolean_summary(weather, "weather_exists", "weather_has_issues")
    raster_qc = read_table(child_path(path_value(config, "hostrada_raster_quality_check", "output_dir"), "hostrada_raster_quality.csv"))
    raster_chart = count_values(raster_qc, "status")
    sections.append(("Step 5 Weather", section("Step 5 Weather", "Punktwetter pro Recording; die jährliche HOSTRADA-Rasterstrecke ist optional und standardmäßig deaktiviert.", {"weather rows": int(len(weather)), "weather issues": weather_cards.get("has issues", 0), "optional raster bands": int(len(raster_qc))}, "Weather status", weather_cards, preview(weather, ["dawn_chorus_id", "weather_exists", "weather_has_issues", "issues"]), weather_notes + (["Optionales Raster-QC: " + ", ".join(f"{key}={value}" for key, value in raster_chart.items())] if raster_chart else []))))

    bio = read_table(path_value(config, "bioacoustics", "qc_compact_csv"))
    sections.append(("Step 6 Bioacoustics", section("Step 6 Bioacoustics", "Modellabdeckung, Inferenz- und Ergebnis-QC.", {"recordings": int(len(bio)), "models incomplete": int((bio.get("required_models_complete", pd.Series(dtype=bool)).astype(str).str.lower() == "false").sum()) if "required_models_complete" in bio.columns else 0}, "QC status", count_values(bio, "status") or count_values(bio, "bioacoustic_status"), preview(bio, ["dawn_chorus_id", "status", "required_models_complete", "bioacoustic_species_count", "issue_codes"]))))

    master = read_table(path_value(config, "master_table", "output_csv"))
    readiness_columns = [column for column in master.columns if column.startswith("ready_for_")]
    readiness = {column.replace("ready_for_", ""): int(as_bool(master[column]).sum()) for column in readiness_columns}
    sections.append(("Step 7 Mastertable", section("Step 7 Mastertable", "Finale ID-Tabelle und Analyse-Readiness.", {"IDs": int(len(master)), "Spalten": int(len(master.columns))}, "Ready for analysis", readiness, preview(master, ["dawn_chorus_id", "ready_for_general_analysis", "ready_for_formation_analysis_100m", "ready_for_direct_lrt_analysis", "sound_has_issues", "weather_point_has_issues", "sentinel_has_issues"]))))
    # Append the new page after the established Step 1..7 pages so their
    # filenames remain stable for bookmarks and downstream checks.
    sections.append(variant_analysis)
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    output_dir = path_value(config, "visual_reporting", "output_dir")
    if output_dir is None:
        output_dir = Path(config["processed_root"]) / "step_9_visual_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    sections = build_sections(config)
    links = [("Overview", "index.html")] + [(title, f"{index:02d}_{title.lower().replace(' ', '_')}.html") for index, (title, _body) in enumerate(sections, start=1)]
    index_body = "".join(body for _title, body in sections)
    atomic_write_text(output_dir / "index.html", page("Bio-O-Ton Pipeline Report", index_body, links))
    for index, (title, body) in enumerate(sections, start=1):
        atomic_write_text(output_dir / links[index][1], page(f"Bio-O-Ton: {title}", body, links))
    atomic_write_json(output_dir / "report_manifest.json", {"generated_utc": datetime.now(timezone.utc).isoformat(), "pages": [href for _label, href in links], "output_dir": str(output_dir)})
    print(f"Visual reports: {output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

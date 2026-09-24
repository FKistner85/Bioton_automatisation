"""Maintain source-linked diagnostic references without replacing editorial READMEs.

Only explicit in-repository codes/messages are enumerated. Third-party exceptions
and parameterised runtime values are intentionally represented as templates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
from documentation_error_meanings import meaning

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "pipeline_control": ["tools/plan_pipeline_run.py", "tools/pipeline_lock.py", "tools/run_with_manifest.py", "tools/horeka_controller.py", "tools/run_array_worker.py", "scripts/pipeline_phase.py"],
    "step_1_metadata": ["scripts/Step_1_metadata_extraction.py", "scripts/recording_time.py"],
    "step_2_0_lrt_cleaning": ["scripts/Step_2_0_clean_lrts.py"],
    "step_2_1_100m_formation_status": ["scripts/Step_2_1_merge_lrts_and_grid.py"],
    "step_2_2_point_assignment": ["scripts/Step_2_2_assign_points_to_lrt_grid.py"],
    "step_2_3_grid_aggregation": ["scripts/Step_2_3_generate_remaining_grid_products.py"],
    "step_2_4_10m_formation_status": ["scripts/Step_2_4_generate_10m_formation_status_products.py"],
    "step_2_variants": ["tools/step2_variants.py", "scripts/Step_2_5_clean_public_lrts.py", "scripts/Step_2_6_merge_public_lrts_and_grid.py", "scripts/Step_7_1_update_formation_variant_table.py"],
    "step_3_media": ["scripts/Step_3_0_a_audio_inventory.py", "scripts/Step_3_0_b_photo_inventory.py", "scripts/Step_3_1_a_audio_download.py", "scripts/Step_3_1_b_photo_download.py", "tools/step3_path_preflight.py"],
    "step_4_sentinel2": ["scripts/Step_4_0_Sentinel2_inventory.py", "scripts/Step_4_1_Sentinel2_download.py", "scripts/Step_4_2_clean_sentinel2.py", "scripts/sentinel2_gee.py", "tools/sentinel_credentials_preflight.py"],
    "step_5_2_weather": ["scripts/Step_5_1_Weather_inventory.py", "scripts/Step_5_2_download_weather_data.py"],
    "step_5_3_hostrada_monthly": ["scripts/Step_5_3_download_hostrada_monthly.py"],
    "step_5_4_hostrada_rasters": ["scripts/Step_5_4_prepare_hostrada_rasters.py", "tools/run_hostrada_raster_all.py"],
    "step_5_5_hostrada_raster_qc": ["scripts/Step_5_5_check_hostrada_raster_products.py"],
    "step_6_bioacoustics": [f"scripts/{p.name}" for p in sorted((ROOT / "scripts").glob("Step_6_*.py"))] + ["scripts/bioacoustics_common.py"],
    "step_7_0_master_table": ["scripts/Step_7_0_update_master_table.py", "scripts/spatiotemporal_duplicates.py"],
    "validation_and_comparison": ["tools/final_validation_report.py", "tools/compare_formation_status_products.py"],
    "step_9_visual_reports": ["tools/generate_pipeline_visual_reports.py"],
}
BEGIN = "<!-- BEGIN SOURCE DIAGNOSTICS -->"
END = "<!-- END SOURCE DIAGNOSTICS -->"


for _group in ('pipeline_control', 'step_1_metadata', 'step_2_2_point_assignment', 'step_7_0_master_table'):
    GROUPS[_group].append('scripts/input_consistency.py')
GROUPS['pipeline_control'] += ['tools/run_spatial_stage.py', 'tools/finalize_master.py']


def literals(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(part.value if isinstance(part, ast.Constant) else "{" + ast.unparse(part.value) + "}" for part in node.values)]
    if isinstance(node, ast.IfExp):
        return literals(node.body) + literals(node.orelse)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [value for part in node.elts for value in literals(part)]
    return []


def diagnostics(path):
    source = (ROOT / path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    records = []

    def add(kind, value, node, fn, context):
        if not value.strip() or value.strip() in {"|", ",", ";"}:
            return
        if kind == "code" and (value == "issue_codes" or value.endswith("_detail_issue_codes")):
            return  # Column selectors, not emitted diagnostic values.
        records.append({"kind": kind, "value": value, "source": path, "line": node.lineno,
                        "function": fn, "condition": context[-1] if context else ""})

    def diagnostic_target(target):
        if isinstance(target, ast.Name):
            return target.id in {"issues", "issue_codes", "error", "status", "technical_status", "release_status", "data_readiness_status"}
        if isinstance(target, ast.Subscript):
            keys = literals(target.slice)
            return any(re.search(r"(^|_)(issues|issue_codes|error|status|coordinate_check)$", key) and not key.endswith("has_issues") for key in keys)
        return False

    def visit(node, fn="module", context=()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.If):
            condition = ast.unparse(node.test)
            visit(node.test, fn, context)
            for item in node.body:
                visit(item, fn, (*context, condition))
            for item in node.orelse:
                visit(item, fn, (*context, "not (" + condition + ")"))
            return
        if isinstance(node, ast.ExceptHandler):
            context = (*context, "except " + (ast.unparse(node.type) if node.type else "BaseException"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = ast.unparse(node.func.value)
            if node.func.attr in {"append", "extend", "add"} and re.search(r"issue|problem|critical|codes|blocking", owner, re.I):
                for arg in node.args:
                    for value in literals(arg):
                        add("code", value, node, fn, context)
            if node.func.attr == "fillna" and "issue_codes" in owner:
                for arg in node.args:
                    for value in literals(arg):
                        add("code", value, node, fn, context)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"add_issue", "issue_join", "join_codes"}:
            for arg in node.args:
                for part in ast.walk(arg):
                    if isinstance(part, ast.List):
                        for value in literals(part):
                            add("code", value, node, fn, context)
                if node.func.id == "add_issue":
                    for value in literals(arg):
                        add("code", value, node, fn, context)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target = " ".join(ast.unparse(t) for t in targets)
            if target in {"NETWORK_ERROR_CODES", "NETWORK_ERROR_MARKERS"}:
                for part in ast.walk(node.value):
                    if isinstance(part, ast.Constant) and type(part.value) is int:
                        add("code", f"WinError {part.value}", node, fn, context)
            if any(diagnostic_target(t) for t in targets) and not isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                for value in literals(node.value):
                    add("status" if "status" in target or "coordinate_check" in target else "code", value, node, fn, context)
        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and re.search(r"(^|_)(issues|issue_codes|error|status|coordinate_check)$", key.value) and not key.value.endswith("has_issues"):
                    for value in literals(val):
                        add("status" if "status" in key.value or "coordinate_check" in key.value else "code", value, node, fn, context)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and fn in {"process_recording", "process_one_recording", "download_recording"}:
            add("status", node.value.value, node, fn, context)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and fn == "download_atomic":
            for value in literals(node.value):
                add("code", value, node, fn, context)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            for arg in node.exc.args[:1]:
                for value in literals(arg):
                    add("exception", ast.unparse(node.exc.func) + ": " + value, node, fn, context)
        if isinstance(node, ast.Return) and fn in {"main", "acquire", "release", "verify_shards", "run_worker"} and node.value is not None:
            if any(isinstance(item, ast.Constant) and type(item.value) is int for item in ast.walk(node.value)):
                add("exit", ast.unparse(node.value), node, fn, context)
        for child in ast.iter_child_nodes(node):
            visit(child, fn, context)
    visit(tree)
    seen = set()
    return [record for record in records if not ((key := (record["kind"], record["value"], record["function"], record["condition"])) in seen or seen.add(key))]


def cell(value):
    return str(value).replace("|", "&#124;").replace("\n", " ").replace("`", "'")


def render(group, language, records):
    de = language == "DE"
    lines = [BEGIN, "## Fehlercodes, Status und Exit-Codes" if de else "## Error Codes, Status And Exit Codes", "",
             ("Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten."
              if de else "Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together."), "",
             ("`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log."
              if de else "`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs."), ""]
    for kind, title_de, title_en in [("code", "Daten- und QC-Codes", "Data And QC Codes"), ("status", "Statuswerte (nicht alle sind Fehler)", "Status Values (Not All Are Errors)"), ("exception", "Explizite Fehlermeldungen", "Explicit Failure Messages"), ("exit", "Explizite Prozessrueckgaben", "Explicit Process Returns")]:
        values = [r for r in records if r["kind"] == kind]
        lines += ["### " + (title_de if de else title_en), ""]
        if not values:
            lines += ["Keine festen Werte dieser Kategorie im zugeordneten Quellcode." if de else "No fixed values in this category in the associated source.", ""]
            continue
        lines += ["| Code / Meldung | Bedeutung / Ausloeser | Quelle |" if de else "| Code / Message | Meaning / Trigger | Source |", "|---|---|---|"]
        for r in values:
            context = meaning(r["value"], language) if kind == "code" else (r["condition"] or ("Ausgabe in " if de else "Emitted by ") + r["function"])
            rendered_context = cell(context) if kind == "code" else f"`{cell(context)}`"
            lines.append(f"| `{cell(r['value'])}` | {rendered_context} | [{Path(r['source']).name}:{r['line']}](../../{r['source']}) |")
        lines.append("")
    lines += [("**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben."
               if de else "**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs."), "", END]
    return "\n".join(lines)


def update(check=False):
    problems = []
    catalog = {}
    for group, sources in GROUPS.items():
        records = []
        for source in sources:
            if not (ROOT / source).is_file():
                raise FileNotFoundError(source)
            records.extend(diagnostics(source))
        catalog[group] = records
        for language in ("DE", "EN"):
            path = ROOT / "Readmes" / group / f"README_{language}.md"
            text = path.read_text(encoding="utf-8")
            block = render(group, language, records)
            updated = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda m: block, text, flags=re.S) if BEGIN in text else text.rstrip() + "\n\n" + block + "\n"
            if updated != text:
                problems.append(str(path.relative_to(ROOT)))
                if not check:
                    path.write_text(updated, encoding="utf-8", newline="\n")
    if not check:
        (ROOT / "Readmes" / "diagnostic_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = update(args.check)
    print(json.dumps({"readmes_outdated" if args.check else "readmes_updated": changed}, indent=2))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())

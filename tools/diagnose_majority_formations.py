"""Diagnose majority-formation outputs against the table-based LRT definition.

This script does not change pipeline products. It reads existing local
processed outputs, compares their formation labels with the formation expected
from their LRT code, and writes CSV/Markdown diagnostics.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


FORMATION_COLUMNS = [
    "majority_formation",
    "Majority_formation",
    "Formation",
    "lrt_formation",
]

CODE_COLUMNS = [
    "majority_formation_lrt_code",
    "LRT_code",
    "lrt_code",
    "LRT_CODE",
    "code",
]

CRITICAL_PREFIXES = ("2180", "2330", "2310", "2320", "1340", "8340")


def normalise_lrt_code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""

    text = str(value).strip()
    if not text or text.lower() in {"nan", "<na>", "none"}:
        return ""

    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = str(int(float(text)))
    return text


def current_script_formation(code: Any) -> str:
    """Formation definition currently used in Step_2_0_clean_lrts.py."""
    code = normalise_lrt_code(code)

    if code.startswith(("1", "2")):
        if code.startswith("1340"):
            return "Bogs"
        if code.startswith("2180") or code.startswith("23"):
            return "Temperate heath"
        return "Costal"
    if code.startswith("3"):
        return "Freshwater"
    if code.startswith(("4", "5")):
        return "Temperate heath"
    if code.startswith("6"):
        return "Grassland"
    if code.startswith("7"):
        return "Bogs"
    if code.startswith("8"):
        if code.startswith("8340"):
            return "Permanent Glaciers"
        return "Rocky habitats"
    if code.startswith("9"):
        return "Forests"
    return "Other"


def table_formation(code: Any) -> str:
    """Formation definition from the table supplied by the user."""
    code = normalise_lrt_code(code)

    if code.startswith("1340") or code.startswith("7"):
        return "Bogs"
    if code.startswith("8340"):
        return "Permanent Glaciers"
    if code.startswith("2180") or code.startswith("9"):
        return "Forests"
    if code.startswith(("2310", "2320", "4", "5")):
        return "Temperate heath"
    if code.startswith("2330") or code.startswith("6"):
        return "Grassland"
    if code.startswith("3"):
        return "Freshwater"
    if code.startswith("8"):
        return "Rocky habitats"
    if code.startswith(("1", "2")):
        return "Costal"
    return "Other"


def is_critical_code(code: str) -> bool:
    return code.startswith(CRITICAL_PREFIXES)


def find_candidate_files(processed_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("*.csv", "*.parquet"):
        candidates.extend(processed_root.rglob(pattern))

    return sorted(
        path
        for path in candidates
        if (
            "majority" in path.name.lower()
            or "lrt_grid" in path.name.lower()
            or "lrt_polygon" in path.name.lower()
        )
    )


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError(f"Unsupported file type: {path}")


def compact_examples(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if len(df) <= max_rows:
        return df
    return df.head(max_rows).copy()


def analyse_pair(
    df: pd.DataFrame,
    source_path: Path,
    formation_column: str,
    code_column: str,
    output_dir: Path,
    max_examples: int,
) -> dict[str, Any]:
    work = pd.DataFrame(
        {
            "source_file": str(source_path),
            "row_number": range(len(df)),
            "output_formation": df[formation_column].astype("string"),
            "lrt_code_raw": df[code_column],
        }
    )

    if "grid_id" in df.columns:
        work["grid_id"] = df["grid_id"]
    if "id" in df.columns:
        work["id"] = df["id"]

    work["lrt_code"] = work["lrt_code_raw"].map(normalise_lrt_code)
    work["expected_table_formation"] = work["lrt_code"].map(table_formation)
    work["current_script_formation"] = work["lrt_code"].map(
        current_script_formation
    )
    work["definition_changed_for_code"] = (
        work["expected_table_formation"] != work["current_script_formation"]
    )
    work["output_matches_table_from_code"] = (
        work["output_formation"] == work["expected_table_formation"]
    )
    work["output_matches_current_script_from_code"] = (
        work["output_formation"] == work["current_script_formation"]
    )
    work["critical_lrt_code"] = work["lrt_code"].map(is_critical_code)

    mismatches = work[~work["output_matches_table_from_code"]].copy()
    changed_def = work[work["definition_changed_for_code"]].copy()
    critical = work[work["critical_lrt_code"]].copy()

    safe_stem = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        f"{source_path.parent.name}_{source_path.stem}_{formation_column}_{code_column}",
    )

    mismatch_path = output_dir / f"{safe_stem}_mismatches.csv"
    changed_path = output_dir / f"{safe_stem}_definition_changed_codes.csv"
    critical_path = output_dir / f"{safe_stem}_critical_codes.csv"
    crosstab_path = output_dir / f"{safe_stem}_crosstab.csv"
    by_code_path = output_dir / f"{safe_stem}_by_lrt_code.csv"

    compact_examples(mismatches, max_examples).to_csv(
        mismatch_path, index=False
    )
    compact_examples(changed_def, max_examples).to_csv(
        changed_path, index=False
    )
    compact_examples(critical, max_examples).to_csv(
        critical_path, index=False
    )

    crosstab = (
        work.groupby(
            [
                "output_formation",
                "expected_table_formation",
                "current_script_formation",
            ],
            dropna=False,
        )
        .size()
        .rename("rows")
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    crosstab.to_csv(crosstab_path, index=False)

    by_code = (
        work.groupby(
            [
                "lrt_code",
                "output_formation",
                "expected_table_formation",
                "current_script_formation",
            ],
            dropna=False,
        )
        .size()
        .rename("rows")
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    by_code.to_csv(by_code_path, index=False)

    return {
        "source_file": str(source_path),
        "rows": int(len(work)),
        "formation_column": formation_column,
        "code_column": code_column,
        "mismatch_rows": int(len(mismatches)),
        "mismatch_share": float(len(mismatches) / len(work)) if len(work) else 0.0,
        "definition_changed_code_rows": int(len(changed_def)),
        "critical_lrt_code_rows": int(len(critical)),
        "mismatch_csv": str(mismatch_path),
        "definition_changed_codes_csv": str(changed_path),
        "critical_codes_csv": str(critical_path),
        "crosstab_csv": str(crosstab_path),
        "by_lrt_code_csv": str(by_code_path),
    }


def analyse_file(
    path: Path,
    output_dir: Path,
    max_examples: int,
) -> list[dict[str, Any]]:
    df = read_table(path)
    formation_cols = [column for column in FORMATION_COLUMNS if column in df.columns]
    code_cols = [column for column in CODE_COLUMNS if column in df.columns]

    if not formation_cols or not code_cols:
        return []

    results = []
    for formation_col in formation_cols:
        for code_col in code_cols:
            results.append(
                analyse_pair(
                    df=df,
                    source_path=path,
                    formation_column=formation_col,
                    code_column=code_col,
                    output_dir=output_dir,
                    max_examples=max_examples,
                )
            )
    return results


def write_markdown_report(
    summaries: list[dict[str, Any]],
    output_dir: Path,
    processed_root: Path,
) -> Path:
    report = output_dir / "majority_formation_definition_diff_report.md"
    lines = [
        "# Majority Formation Definition Diagnostics",
        "",
        f"Processed root: `{processed_root}`",
        "",
        "Definition checked against the table supplied by the user.",
        "",
        "Important interpretation notes:",
        "",
        "- `2180` is expected as `Forests`, not `Temperate heath`.",
        "- `2330` is expected as `Grassland`, not `Temperate heath`.",
        "- `2310` and `2320` stay `Temperate heath`.",
        "- For 1km/5km/10km products, a mismatch can also mean the exported "
        "`LRT_code` was chosen independently of the exported "
        "`Majority_formation`.",
        "- This diagnostic does not recompute spatial overlays; it checks the "
        "existing output rows against their exported LRT code.",
        "",
        "## Summary",
        "",
        "| Source | Formation column | LRT code column | Rows | Mismatches | Share | Changed-code rows |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]

    for item in summaries:
        source = Path(item["source_file"]).name
        lines.append(
            "| "
            + " | ".join(
                [
                    source,
                    item["formation_column"],
                    item["code_column"],
                    f"{item['rows']:,}",
                    f"{item['mismatch_rows']:,}",
                    f"{item['mismatch_share']:.2%}",
                    f"{item['definition_changed_code_rows']:,}",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Output Files",
            "",
        ]
    )
    for item in summaries:
        lines.extend(
            [
                f"### {Path(item['source_file']).name} / "
                f"{item['formation_column']} vs {item['code_column']}",
                "",
                f"- Mismatches: `{item['mismatch_csv']}`",
                f"- Rows where old and table definition differ: "
                f"`{item['definition_changed_codes_csv']}`",
                f"- Critical-code rows: `{item['critical_codes_csv']}`",
                f"- Crosstab: `{item['crosstab_csv']}`",
                f"- Grouped by LRT code: `{item['by_lrt_code_csv']}`",
                "",
            ]
        )

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    default_outputs = Path(
        "/lsdf/kit/ipf/projects/Bio-O-Ton"
        "/Data_automatisation_skripts/outputs"
    )

    parser = argparse.ArgumentParser(
        description=(
            "Compare existing majority-formation outputs with the "
            "table-based LRT formation definition."
        )
    )
    parser.add_argument(
        "--output-root",
        "--processed-root",
        dest="output_root",
        type=Path,
        default=default_outputs,
        help="Root folder containing local pipeline outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Diagnostic output folder.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=20000,
        help="Maximum rows written to each example mismatch CSV.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    processed_root = args.output_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else processed_root
        / "diagnostics"
        / "majority_formation_definition_diff"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    if not processed_root.exists():
        raise FileNotFoundError(f"Processed root not found: {processed_root}")

    candidate_files = find_candidate_files(processed_root)
    summaries: list[dict[str, Any]] = []
    skipped: list[str] = []

    for path in candidate_files:
        try:
            results = analyse_file(path, output_dir, args.max_examples)
        except Exception as exc:
            skipped.append(f"{path}: {exc}")
            continue
        if results:
            summaries.extend(results)
        else:
            skipped.append(f"{path}: no formation/LRT-code column pair")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "processed_root": str(processed_root),
                "output_dir": str(output_dir),
                "analyses": summaries,
                "skipped": skipped,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    report_path = write_markdown_report(summaries, output_dir, processed_root)

    print(f"Analysed column pairs: {len(summaries)}")
    for item in summaries:
        print(
            f"{Path(item['source_file']).name}: "
            f"{item['formation_column']} vs {item['code_column']} -> "
            f"{item['mismatch_rows']:,}/{item['rows']:,} mismatches "
            f"({item['mismatch_share']:.2%})"
        )
    print(f"Report: {report_path}")
    print(f"Summary JSON: {summary_path}")
    if skipped:
        print(f"Skipped files: {len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


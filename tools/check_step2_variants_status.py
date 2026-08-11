#!/usr/bin/env python3
"""Check completion status of all Step-2 LRT variants and report disk usage.

For each discovered variant the script shows which stages are finished,
which have intermediate chunks that can be safely removed, and how much
disk space could be freed.  The check is entirely read-only and fast –
it only reads state.json files and measures directory sizes.

Usage
-----
python tools/check_step2_variants_status.py --config path/to/config.json
python tools/check_step2_variants_status.py --config path/to/config.json --cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dir_size_bytes(path: Path) -> int:
    """Return total size of all files under *path* (0 if absent)."""
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def tick(ok: bool, partial: bool = False) -> str:
    if partial:
        return "[~]"
    return "[✓]" if ok else "[ ]"


# ---------------------------------------------------------------------------
# per-stage status
# ---------------------------------------------------------------------------

STAGE_ORDER = ("2_0", "2_1", "2_2", "2_3", "2_4")


def _check_state(state_path: Path, output_file: Path) -> str:
    """Return a concise state/output status."""
    if not output_file.is_file() or output_file.stat().st_size == 0:
        return "missing"
    if not state_path.is_file():
        return "stale"
    try:
        state = load_json(state_path)
    except (OSError, json.JSONDecodeError):
        return "invalid"
    explicit = str(state.get("status", "")).strip().lower()
    if explicit and explicit != "complete":
        return explicit
    return "ok"


def check_variant(variant_config: dict[str, Any], variant_suffix: str) -> dict[str, Any]:
    """Inspect one variant's output directories and return a status dict."""

    root20 = Path(variant_config["lrt_cleaning"]["state_file"]).parent
    root21 = Path(variant_config["lrt_grid_merge"]["state_file"]).parent
    root22 = Path(variant_config["point_lrt_assignment"]["state_file"]).parent
    root23 = Path(variant_config["lrt_grid_aggregation"]["state_file"]).parent
    root24 = Path(variant_config["susi_10m_products"]["state_file"]).parent

    def stage_result(state_file: Path, output_file: Path) -> str:
        return _check_state(state_file, output_file)

    s = {
        "2_0": stage_result(root20 / "state.json", Path(variant_config["lrt_cleaning"]["output_gpkg"])),
        "2_1": stage_result(root21 / "state.json", Path(variant_config["lrt_grid_merge"]["output_grid_parquet"])),
        "2_2": stage_result(root22 / "state.json", Path(variant_config["point_lrt_assignment"]["output_csv"])),
        "2_3": stage_result(root23 / "state.json", root23 / "state.json"),  # aggregation writes state
        "2_4": stage_result(root24 / "state.json", Path(variant_config["susi_10m_products"]["final_parquet"])),
    }

    # chunk dirs that are safe to remove once 2_4 final_parquet exists
    chunk_dirs: dict[str, Path] = {
        "grid10m_chunks": Path(variant_config["susi_10m_products"]["grid_chunk_dir"]),
        "ix_chunks": Path(variant_config["susi_10m_products"]["ix_chunk_dir"]),
        "parquet_10": Path(variant_config["susi_10m_products"]["parquet_chunk_dir"]),
        "_chunk_checkpoints": Path(variant_config["lrt_grid_merge"]["chunk_checkpoint_dir"]),
    }
    final_parquet = Path(variant_config["susi_10m_products"]["final_parquet"])
    can_cleanup = s["2_4"] == "ok" and final_parquet.is_file()
    cleanable: dict[str, int] = {}
    for name, path in chunk_dirs.items():
        sz = dir_size_bytes(path)
        if sz > 0:
            cleanable[str(path)] = sz

    return {
        "stages": s,
        "can_cleanup": can_cleanup,
        "cleanable_dirs": cleanable,
        "total_cleanable_bytes": sum(cleanable.values()),
    }


def cleanup_variant(result: dict[str, Any]) -> int:
    """Delete cleanable chunk directories. Returns bytes freed."""
    if not result["can_cleanup"]:
        return 0
    freed = 0
    for path_str, sz in result["cleanable_dirs"].items():
        path = Path(path_str)
        if path.is_dir():
            try:
                shutil.rmtree(path)
                freed += sz
                print(f"  REMOVED {path}  ({human(sz)})")
            except OSError as exc:
                print(f"  ERROR removing {path}: {exc}", file=sys.stderr)
    return freed


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _load_variants(config_path: Path) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Use step2_variants.prepare() to discover variants and load their configs."""
    tools = Path(__file__).resolve().parent
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from step2_variants import prepare  # type: ignore[import]

    base, variants = prepare(config_path)
    loaded = []
    for variant in variants:
        vcfg = json.loads(variant.config_path.read_text(encoding="utf-8"))
        loaded.append((variant.suffix, vcfg))
    return base, loaded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check completion status of all Step-2 LRT variants and report "
            "how much disk space can be reclaimed by removing chunk directories."
        ),
    )
    parser.add_argument("--config", type=Path, required=True, help="Config JSON (local or horeka)")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help=(
            "Remove chunk directories for variants where the final parquet already "
            "exists (safe to run at any time; will not delete final outputs)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON summary instead of human text.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.config.is_file():
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 2

    try:
        _base, variants = _load_variants(args.config)
    except Exception as exc:
        print(f"ERROR loading variants: {exc}", file=sys.stderr)
        return 1

    results: dict[str, dict[str, Any]] = {}
    for suffix, vcfg in variants:
        results[suffix] = check_variant(vcfg, suffix)

    if args.json_output:
        print(json.dumps(results, indent=2))
        return 0

    # Human-readable output
    total_cleanable = 0
    all_complete = True
    for suffix, r in results.items():
        stages = r["stages"]
        complete = all(v == "ok" for v in stages.values())
        if not complete:
            all_complete = False

        stage_symbols = {
            "ok": "✓",
            "stale": "~",
            "missing": " ",
            "invalid": "!",
            "in_progress": "~",
            "failed": "!",
            "partial": "~",
        }
        stage_line = "  ".join(
            f"[{stage_symbols.get(stages[s], '!')}] {s}:{stages[s]}"
            for s in STAGE_ORDER
        )

        print(f"\nVariant: {suffix}")
        print(f"  Stages : {stage_line}")

        if r["cleanable_dirs"]:
            if r["can_cleanup"]:
                label = "✓ safe to clean"
            else:
                label = "⚠ wait for 2_4 to finish"
            print(f"  Chunks : {label}")
            for path_str, sz in r["cleanable_dirs"].items():
                print(f"    {human(sz):>10}  {path_str}")
            print(f"  Disk to recover: {human(r['total_cleanable_bytes'])}")
            total_cleanable += r["total_cleanable_bytes"]
        else:
            print("  Chunks : none (already clean)")

        if args.cleanup and r["cleanable_dirs"]:
            freed = cleanup_variant(r)
            if freed:
                print(f"  Freed  : {human(freed)}")

    print()
    status_line = "ALL COMPLETE" if all_complete else "INCOMPLETE – see variants above"
    print(f"Summary : {len(results)} variant(s) | {status_line}")
    if total_cleanable > 0:
        action = "freed" if args.cleanup else "reclaimable with --cleanup"
        print(f"Disk    : {human(total_cleanable)} {action}")
    else:
        print("Disk    : nothing to clean")

    return 0 if all_complete else 3


if __name__ == "__main__":
    raise SystemExit(main())

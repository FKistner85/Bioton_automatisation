#!/usr/bin/env python3
"""Delete generated outputs for a clean Step 1-3 rebuild."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/"
    "Data_automatisation_skripts/outputs"
)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def add_parent(targets: set[Path], value: str | None) -> None:
    if value:
        targets.add(Path(value).parent)


def add_path(targets: set[Path], value: str | None) -> None:
    if value:
        targets.add(Path(value))


def collect_targets(config: dict[str, Any]) -> set[Path]:
    targets: set[Path] = set()
    add_path(targets, config.get("status_dir"))

    for section_name, keys in {
        "lrt_cleaning": ["output_gpkg", "state_file"],
        "lrt_grid_merge": [
            "output_csv",
            "output_parquet",
            "output_grid_gpkg",
            "output_grid_parquet",
            "chunk_checkpoint_dir",
            "state_file",
        ],
        "point_lrt_assignment": [
            "output_csv",
            "matches_csv",
            "log_csv",
            "state_file",
        ],
        "lrt_grid_aggregation": ["output_dir", "state_file"],
        "susi_10m_products": [
            "output_dir",
            "grid_chunk_dir",
            "ix_chunk_dir",
            "parquet_chunk_dir",
            "final_parquet",
            "state_file",
        ],
        "public_lrt_cleaning": ["output_gpkg", "state_file"],
        "public_lrt_grid_merge": [
            "output_dir",
            "chunk_checkpoint_dir",
            "state_file",
        ],
        "audio_inventory": ["detailed_log", "compact_log", "state_file"],
        "photo_inventory": ["detailed_log", "compact_log", "state_file"],
        "audio_download": ["retry_log"],
        "photo_download": ["retry_log"],
    }.items():
        section = config.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for key in keys:
            value = section.get(key)
            if key.endswith("_dir") or key in {"output_dir", "chunk_checkpoint_dir"}:
                add_path(targets, value)
            else:
                add_parent(targets, value)

        if section_name == "lrt_grid_merge":
            susi = section.get("susi_compatible_outputs", {})
            if isinstance(susi, dict):
                add_path(targets, susi.get("output_dir"))

    return targets


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean generated outputs through Step 3."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        "--processed-root",
        dest="output_root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--marker-file",
        type=Path,
        help="If present, cleanup is skipped unless --force-clean is used.",
    )
    parser.add_argument("--force-clean", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        if args.marker_file and args.marker_file.exists() and not args.force_clean:
            print(f"Cleanup marker exists; skipping cleanup: {args.marker_file}")
            return 0

        config = load_config(args.config)
        root = args.output_root
        targets = sorted(
            {
                target
                for target in collect_targets(config)
                if is_inside(target, root)
            },
            key=lambda item: (len(str(item)), str(item)),
            reverse=True,
        )
        print(f"Output root:    {root}")
        print(f"Targets       : {len(targets)}")
        for target in targets:
            if not target.exists():
                print(f"missing: {target}")
                continue
            print(f"delete : {target}")
            if args.dry_run:
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if args.marker_file and not args.dry_run:
            args.marker_file.parent.mkdir(parents=True, exist_ok=True)
            args.marker_file.write_text(
                "outputs through Step 3 cleaned\n",
                encoding="utf-8",
            )
            print(f"Marker written: {args.marker_file}")
        return 0
    except Exception as exc:
        print(f"ERROR in cleanup: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


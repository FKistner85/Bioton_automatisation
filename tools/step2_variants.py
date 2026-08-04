#!/usr/bin/env python3
"""Discover, configure and execute isolated Step-2 dataset variants."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STAGE_SCRIPTS = {
    "2_0": "scripts/Step_2_0_clean_lrts.py",
    "2_1": "scripts/Step_2_1_merge_lrts_and_grid.py",
    "2_2": "scripts/Step_2_2_assign_points_to_lrt_grid.py",
    "2_3": "scripts/Step_2_3_generate_remaining_grid_products.py",
    "2_4": "scripts/Step_2_4_generate_10m_formation_status_products.py",
}
STAGE_ORDER = tuple(STAGE_SCRIPTS)


@dataclass(frozen=True)
class Variant:
    index: int
    suffix: str
    source_gpkg: Path
    output_root: Path
    config_path: Path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, dir=path.parent, encoding="utf-8"
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, path)


def variant_suffix(path: Path, prefix: str = "All_Bundeslander_") -> str:
    stem = path.stem
    if stem.casefold().startswith(prefix.casefold()):
        stem = stem[len(prefix):]
    suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not suffix:
        raise ValueError(f"Cannot derive a variant suffix from {path.name}")
    return suffix


def discover_variants(config: dict[str, Any]) -> list[Variant]:
    settings = config.get("lrt_variants", {})
    if not isinstance(settings, dict):
        raise TypeError("'lrt_variants' must be a JSON object.")
    input_dir = Path(settings["input_dir"])
    output_root = Path(settings["output_root"])
    pattern = str(settings.get("input_glob", "All_Bundeslander_*.gpkg"))
    config_dir = output_root / "_configs"
    if not input_dir.is_dir():
        raise NotADirectoryError(f"LRT variant input directory not found: {input_dir}")
    sources = sorted(
        (path for path in input_dir.glob(pattern) if path.is_file()),
        key=lambda path: path.name.casefold(),
    )
    if not sources:
        raise FileNotFoundError(f"No LRT variant GeoPackages match {input_dir / pattern}")
    variants: list[Variant] = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        suffix = variant_suffix(source)
        key = suffix.casefold()
        if key in seen:
            raise ValueError(f"Duplicate LRT variant suffix: {suffix}")
        seen.add(key)
        root = output_root / suffix
        variants.append(
            Variant(
                index=index,
                suffix=suffix,
                source_gpkg=source,
                output_root=root,
                config_path=config_dir / f"config.step2.{suffix}.json",
            )
        )
    return variants


def configure_variant(base: dict[str, Any], variant: Variant) -> dict[str, Any]:
    config = copy.deepcopy(base)
    suffix = variant.suffix
    root = variant.output_root
    step20 = root / "step_2_0"
    step21 = root / "step_2_1"
    step21_susi = root / "step_2_1_susi_compatible"
    step22 = root / "step_2_2"
    step23 = root / "step_2_3"
    step24 = root / "step_2_4_susi_10m"

    config["step2_variant"] = {
        "suffix": suffix,
        "source_gpkg": str(variant.source_gpkg),
        "output_root": str(root),
    }
    config["manifest_dir"] = str(root / "_manifests")
    config["status_dir"] = str(root / "_status")

    config["lrt_cleaning"].update({
        "source_gpkgs": [str(variant.source_gpkg)],
        "output_gpkg": str(step20 / f"lrt_{suffix}.gpkg"),
        "state_file": str(step20 / "state.json"),
    })
    config["lrt_grid_merge"].update({
        "lrt_gpkg": str(step20 / f"lrt_{suffix}.gpkg"),
        "output_csv": str(step21 / f"LRT_Grid_Majority_{suffix}.csv"),
        "output_grid_gpkg": str(step21 / f"majority_formation_grid_{suffix}.gpkg"),
        "output_grid_parquet": str(step21 / f"majority_formation_grid_{suffix}.parquet"),
        "chunk_checkpoint_dir": str(step21 / "_chunk_checkpoints"),
        "state_file": str(step21 / "state.json"),
    })
    config["lrt_grid_merge"]["susi_compatible_outputs"].update({
        "output_dir": str(step21_susi),
    })
    config["point_lrt_assignment"].update({
        "grid_majority_csv": str(step21 / f"LRT_Grid_Majority_{suffix}.csv"),
        "lrt_gpkg": str(step20 / f"lrt_{suffix}.gpkg"),
        "output_csv": str(step22 / f"DawnChorus_LRT_Grid_Assignment_{suffix}.csv"),
        "matches_csv": str(step22 / f"DawnChorus_LRT_Polygon_Matches_{suffix}.csv"),
        "log_csv": str(step22 / f"point_processing_log_{suffix}.csv"),
        "state_file": str(step22 / "state.json"),
    })
    config["lrt_grid_aggregation"].update({
        "source_parquet": str(step21 / f"majority_formation_grid_{suffix}.parquet"),
        "output_dir": str(step23),
        "state_file": str(step23 / "state.json"),
    })
    config["susi_10m_products"].update({
        "source_100m_parquet": str(step21_susi / "Formation_Status_Grid_withLRTCode.parquet"),
        "lrt_gpkg": str(step20 / f"lrt_{suffix}.gpkg"),
        "output_dir": str(step24),
        "grid_chunk_dir": str(step24 / "grid10m_chunks"),
        "ix_chunk_dir": str(step24 / "ix_chunks"),
        "parquet_chunk_dir": str(step24 / "parquet_10"),
        "final_parquet": str(step24 / f"Formation_Status_10m_Grid_withLRTCode_{suffix}.parquet"),
        "state_file": str(step24 / "state.json"),
    })
    return config


def prepare(config_path: Path) -> tuple[dict[str, Any], list[Variant]]:
    config = load_json(config_path)
    variants = discover_variants(config)
    settings = config["lrt_variants"]
    primary = str(settings.get("primary_suffix", "")).strip()
    available = {variant.suffix for variant in variants}
    if not primary:
        raise ValueError("'lrt_variants.primary_suffix' must not be empty.")
    if primary not in available:
        raise ValueError(
            "Configured primary LRT variant is missing: "
            f"{primary}. Available: {', '.join(sorted(available))}"
        )
    for variant in variants:
        atomic_write_json(variant.config_path, configure_variant(config, variant))
    index_path = Path(settings.get("index_json", Path(settings["output_root"]) / "variant_index.json"))
    atomic_write_json(index_path, {
        "schema_version": "2026-08-04-step2-variants-v1",
        "primary_suffix": primary,
        "variant_count": len(variants),
        "variants": [
            {
                "index": variant.index,
                "suffix": variant.suffix,
                "is_primary": variant.suffix == primary,
                "source_gpkg": str(variant.source_gpkg),
                "output_root": str(variant.output_root),
                "config_path": str(variant.config_path),
            }
            for variant in variants
        ],
    })
    return config, variants


def command_for_stage(
    repo_root: Path,
    python: Path,
    variant: Variant,
    stage: str,
    *,
    force: bool,
    ids_file: Path | None,
) -> list[str]:
    command = [
        str(python),
        str(repo_root / STAGE_SCRIPTS[stage]),
        "--config",
        str(variant.config_path),
    ]
    if force:
        command.append("--force")
    if stage == "2_2" and ids_file is not None:
        command.extend(["--ids-file", str(ids_file)])
    return command


def run_stage(
    repo_root: Path,
    python: Path,
    variant: Variant,
    stage: str,
    *,
    force: bool,
    ids_file: Path | None,
) -> int:
    print(f"\n===== Step {stage} variant {variant.suffix} =====", flush=True)
    result = subprocess.run(
        command_for_stage(
            repo_root,
            python,
            variant,
            stage,
            force=force,
            ids_file=ids_file,
        ),
        cwd=repo_root,
        check=False,
    )
    return int(result.returncode)


def run_stage_all(
    repo_root: Path,
    python: Path,
    variants: list[Variant],
    stage: str,
    *,
    force: bool,
    ids_file: Path | None,
    max_workers: int,
) -> int:
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = {
            executor.submit(
                run_stage,
                repo_root,
                python,
                variant,
                stage,
                force=force,
                ids_file=ids_file,
            ): variant
            for variant in variants
        }
        for future in as_completed(futures):
            variant = futures[future]
            try:
                code = future.result()
            except Exception as exc:
                print(f"ERROR variant {variant.suffix}: {exc}", file=sys.stderr)
                code = 1
            if code != 0:
                failures.append(variant.suffix)
    if failures:
        print(
            f"Step {stage} failed for variants: {', '.join(sorted(failures))}",
            file=sys.stderr,
        )
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--task-count", action="store_true")
    parser.add_argument("--task-index", type=int)
    parser.add_argument("--stage", choices=STAGE_ORDER)
    parser.add_argument("--all-stages", action="store_true")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, variants = prepare(args.config)
    print(f"Step-2 variants discovered: {len(variants)}")
    for variant in variants:
        print(f"[{variant.index:02d}] {variant.suffix}: {variant.source_gpkg.name}")
    if args.task_count:
        print(len(variants))
        return 0
    if args.prepare_only:
        return 0

    repo_root = Path(__file__).resolve().parents[1]
    if args.task_index is not None:
        if not 0 <= args.task_index < len(variants):
            raise ValueError(f"--task-index must be between 0 and {len(variants) - 1}")
        if args.stage is None:
            raise ValueError("--stage is required with --task-index")
        return run_stage(
            repo_root,
            args.python,
            variants[args.task_index],
            args.stage,
            force=args.force,
            ids_file=args.ids_file,
        )

    stages = STAGE_ORDER if args.all_stages else ((args.stage,) if args.stage else ())
    if not stages:
        raise ValueError("Select --stage, --all-stages, --prepare-only or --task-count")
    for stage in stages:
        code = run_stage_all(
            repo_root,
            args.python,
            variants,
            stage,
            force=args.force,
            ids_file=args.ids_file,
            max_workers=args.max_workers,
        )
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

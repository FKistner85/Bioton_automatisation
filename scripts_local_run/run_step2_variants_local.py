#!/usr/bin/env python3
"""Run all Step-2 LRT variants locally, reusing already-computed results.

Analog to submit_step2_variants_horeka.sh but for local execution.
Each stage is run as a subprocess so no intermediate data is held in memory.
Already-finished stages are skipped automatically via each script's state file
(no --force by default).

Usage
-----
python scripts_local_run/run_step2_variants_local.py \\
    --config path/to/config.local.json \\
    [--python path/to/python]          \\
    [--max-parallel 2]                 \\
    [--stages 2_0 2_1 2_2 2_3 2_4]    \\
    [--force]                          \\
    [--ids-file path/to/ids.csv]       \\
    [--cleanup-chunks]                 \\
    [--dry-run]                        \\
    [--status]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Keep in sync with tools/step2_variants.py STAGE_ORDER
STAGE_ORDER = ("2_0", "2_1", "2_2", "2_3", "2_4")
# Stages that may run in parallel with each other (after 2_1 finishes)
PARALLEL_STAGES = frozenset({"2_2", "2_3", "2_4"})


def prepare_variants(config: Path, python: Path) -> int:
    """Run tools/step2_variants.py --prepare-only to write per-variant configs."""
    result = subprocess.run(
        [
            str(python),
            str(Path(__file__).resolve().parents[1] / "tools" / "step2_variants.py"),
            "--config",
            str(config),
            "--python",
            str(python),
            "--prepare-only",
        ],
        check=False,
    )
    return result.returncode


def get_variant_count(config: Path, python: Path) -> int:
    result = subprocess.run(
        [
            str(python),
            str(Path(__file__).resolve().parents[1] / "tools" / "step2_variants.py"),
            "--config",
            str(config),
            "--python",
            str(python),
            "--task-count",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not read variant count:\n{result.stderr}")
    last = result.stdout.strip().splitlines()[-1]
    if not last.isdigit():
        raise RuntimeError(f"Unexpected variant count output: {last!r}")
    return int(last)


def run_one(
    python: Path,
    config: Path,
    stage: str,
    task_index: int,
    *,
    force: bool,
    ids_file: Path | None,
    dry_run: bool,
) -> tuple[int, int]:
    """Run a single stage/variant combination. Returns (task_index, returncode)."""
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        str(python),
        str(repo_root / "tools" / "step2_variants.py"),
        "--config",
        str(config),
        "--python",
        str(python),
        "--stage",
        stage,
        "--task-index",
        str(task_index),
    ]
    if force:
        cmd.append("--force")
    if ids_file is not None:
        cmd.extend(["--ids-file", str(ids_file)])

    print(f"  START  stage={stage} variant_index={task_index}", flush=True)
    if dry_run:
        print(f"  DRY-RUN (would run): {' '.join(cmd)}", flush=True)
        return task_index, 0

    result = subprocess.run(cmd, check=False)
    code = result.returncode
    status = "OK" if code == 0 else f"FAILED exit={code}"
    print(f"  END    stage={stage} variant_index={task_index}: {status}", flush=True)
    return task_index, code


def run_stage_all(
    python: Path,
    config: Path,
    stage: str,
    variant_count: int,
    *,
    force: bool,
    ids_file: Path | None,
    max_parallel: int,
    dry_run: bool,
) -> int:
    """Run one stage across all variants, up to max_parallel at a time."""
    print(f"\n=== Stage {stage}: {variant_count} variant(s), max_parallel={max_parallel} ===", flush=True)
    failures: list[int] = []
    with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as executor:
        futures = {
            executor.submit(
                run_one,
                python,
                config,
                stage,
                index,
                force=force,
                ids_file=ids_file,
                dry_run=dry_run,
            ): index
            for index in range(variant_count)
        }
        for future in as_completed(futures):
            _, code = future.result()
            if code != 0:
                failures.append(futures[future])
    if failures:
        print(
            f"Stage {stage} FAILED for variant indices: {sorted(failures)}",
            file=sys.stderr,
        )
        return 1
    return 0


def _run_checker(config: Path, python: Path, *, cleanup: bool = False) -> int:
    """Delegate to tools/check_step2_variants_status.py."""
    checker = Path(__file__).resolve().parents[1] / "tools" / "check_step2_variants_status.py"
    cmd = [str(python), str(checker), "--config", str(config)]
    if cleanup:
        cmd.append("--cleanup")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def parse_args() -> argparse.Namespace:
    default_python = Path(sys.executable)
    parser = argparse.ArgumentParser(
        description="Run all Step-2 LRT variants locally, skipping already-computed stages.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the local config JSON (e.g. config.local.json)",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=default_python,
        help=f"Python interpreter to use (default: {default_python})",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=None,
        help=(
            "Maximum number of variants to process in parallel within each stage. "
            "Reads 'lrt_variants.local_max_parallel_variants' from config if not given."
        ),
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=list(STAGE_ORDER),
        default=list(STAGE_ORDER),
        metavar="STAGE",
        help=f"Which stages to run (default: all). Choices: {', '.join(STAGE_ORDER)}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Pass --force to each stage script, recomputing even if state files exist.",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="IDs file forwarded to stage 2_2 (point assignment).",
    )
    parser.add_argument(
        "--cleanup-chunks",
        action="store_true",
        help=(
            "After all stages finish, remove intermediate chunk directories "
            "(grid10m_chunks, ix_chunks, parquet_10, _chunk_checkpoints) for "
            "each variant whose final parquet already exists. "
            "Safe to use: only deletes data that can be recomputed."
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Only print a completion-status and disk-usage report "
            "(delegates to tools/check_step2_variants_status.py) then exit. "
            "Does not run any pipeline stages."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.config.is_file():
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 2
    if not args.python.is_file():
        print(f"Python not found: {args.python}", file=sys.stderr)
        return 2

    # --status: just show the status report and exit
    if args.status:
        return _run_checker(args.config, args.python)

    # Resolve max_parallel from config if not given on CLI
    max_parallel = args.max_parallel
    if max_parallel is None:
        import json
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
        max_parallel = max(1, int(cfg.get("lrt_variants", {}).get("local_max_parallel_variants", 1)))

    # Sort requested stages to preserve pipeline order
    requested = [s for s in STAGE_ORDER if s in set(args.stages)]

    print(f"Config         : {args.config}")
    print(f"Python         : {args.python}")
    print(f"Stages         : {', '.join(requested)}")
    print(f"Max parallel   : {max_parallel}")
    print(f"Force          : {args.force}")
    print(f"Cleanup chunks : {args.cleanup_chunks}")
    print(f"Dry-run        : {args.dry_run}")

    # Step 1: write per-variant config files (lightweight, always needed)
    print("\n--- Preparing variant configs ---", flush=True)
    if not args.dry_run:
        code = prepare_variants(args.config, args.python)
        if code != 0:
            print("Variant preparation failed.", file=sys.stderr)
            return code
    else:
        print("DRY-RUN: skipping variant config preparation", flush=True)

    # Step 2: count variants
    if args.dry_run:
        variant_count = 0
        print("DRY-RUN: variant count unknown, stages will be listed but not run", flush=True)
    else:
        variant_count = get_variant_count(args.config, args.python)
    print(f"\nVariants found: {variant_count}", flush=True)
    if variant_count == 0 and not args.dry_run:
        print("No variants found – check lrt_variants.input_dir and input_glob in config.", file=sys.stderr)
        return 1

    # Step 3: run stages in order
    # Stages 2_2, 2_3, 2_4 are independent of each other (all depend only on 2_1),
    # so we run them with full parallelism across variants.
    # Stage 2_0 and 2_1 are run serially between themselves (2_1 depends on 2_0).
    for stage in requested:
        code = run_stage_all(
            args.python,
            args.config,
            stage,
            variant_count,
            force=args.force,
            ids_file=args.ids_file if stage == "2_2" else None,
            max_parallel=max_parallel,
            dry_run=args.dry_run,
        )
        if code != 0:
            print(f"\nAborting: stage {stage} had failures.", file=sys.stderr)
            return code

    print("\nAll requested stages completed successfully.", flush=True)

    # Step 4: optional chunk cleanup
    if args.cleanup_chunks and not args.dry_run:
        print("\n--- Cleaning up intermediate chunk directories ---", flush=True)
        _run_checker(args.config, args.python, cleanup=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Process logical array tasks sequentially inside a bounded Slurm worker pool."""
from __future__ import annotations

import argparse
import os
import signal
import subprocess


def task_indices(worker_index: int, worker_count: int, task_count: int) -> range:
    if worker_count < 1 or task_count < 1 or not 0 <= worker_index < worker_count:
        raise ValueError("Require positive counts and 0 <= worker-index < worker-count")
    return range(worker_index, task_count, worker_count)


def run_worker(worker_index: int, worker_count: int, task_count: int, command: list[str]) -> int:
    indices = task_indices(worker_index, worker_count, task_count)
    if not command:
        raise ValueError("A child command is required")
    child = None
    interrupted = 0
    failed = []

    def stop(signum, _frame):
        nonlocal interrupted
        interrupted = signum
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGUSR1"):
        signals.append(signal.SIGUSR1)
    previous = {sig: signal.signal(sig, stop) for sig in signals}
    try:
        for index in indices:
            if interrupted:
                break
            print(f"Worker {worker_index + 1}/{worker_count}: logical task {index}/{task_count - 1}", flush=True)
            child = subprocess.Popen([*command, "--task-index", str(index)])
            # A signal may arrive between the pre-launch check and Popen.
            if interrupted and child.poll() is None:
                child.send_signal(interrupted)
            code = child.wait()
            child = None
            if code:
                failed.append(index)
                print(f"Logical task {index} failed: exit {code}", flush=True)
        if interrupted:
            print("Worker interrupted; no further tasks started. Resume using existing checkpoints.", flush=True)
            return 128 + interrupted
        if failed:
            print(f"Failed logical tasks: {failed}", flush=True)
            return 1
        return 0
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-index", type=int, default=os.environ.get("SLURM_ARRAY_TASK_ID", "0"))
    parser.add_argument("--worker-count", type=int, required=True)
    parser.add_argument("--task-count", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run_worker(args.worker_index, args.worker_count, args.task_count, command)


if __name__ == "__main__":
    raise SystemExit(main())

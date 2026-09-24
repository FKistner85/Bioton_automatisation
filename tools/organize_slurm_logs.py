#!/usr/bin/env python3
"""Build archive/current hard-link views without moving Slurm/manifest paths.

Only files recorded in our index may be removed from current. Archive links
remain permanently. Array tasks and stdout/stderr are grouped by submission.
Run once after jobs finish; concurrent organizers are rejected by a lock.
"""
import argparse
import json
import os
from pathlib import Path
import re

PATTERN = re.compile(r"^(\d{8}T\d{6}Z)_(bio_.+?)_(\d+)(?:_(\d+))?\.(out|err)$")


def link_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not os.path.samefile(source, target):
            raise FileExistsError(f"Refusing to replace unrelated log: {target}")
    else:
        os.link(source, target)


def organize(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".organize.lock"
    lock.mkdir()
    try:
        groups = {}
        for source in sorted(root.iterdir()):
            match = PATTERN.fullmatch(source.name)
            if not match or not source.is_file():
                continue
            stamp, step, job, task, extension = match.groups()
            key = (step, stamp, int(job))
            groups.setdefault(key, []).append(source)
        latest = {}
        for step, stamp, job in groups:
            latest[step] = max(latest.get(step, ("", 0)), (stamp, job))
        index = root / ".log_views.json"
        previous = json.loads(index.read_text(encoding="utf-8")) if index.exists() else {"current": []}
        current = []
        for (step, stamp, job), files in groups.items():
            for source in files:
                link_file(source, root / "archive" / stamp / step / source.name)
                if latest[step] == (stamp, job):
                    destination = root / "current" / step / source.name
                    link_file(source, destination)
                    current.append(destination.relative_to(root).as_posix())
        for relative in set(previous["current"]) - set(current):
            old = root / relative
            # Never trust an edited index to delete outside the managed view.
            if not old.resolve().is_relative_to(root / "current"):
                raise ValueError(f"Unsafe managed log path: {relative}")
            original = root / old.name
            if old.exists() and original.exists() and os.path.samefile(old, original):
                old.unlink()
        payload = {"current": sorted(current), "steps": len(latest), "submissions": len(groups)}
        temporary = index.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(index)
        return payload
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(organize(args.log_dir), indent=2))


if __name__ == "__main__":
    main()

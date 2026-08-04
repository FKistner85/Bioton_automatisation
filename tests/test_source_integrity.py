#!/usr/bin/env python3
"""Verify that all maintained Python sources are valid UTF-8 and compile."""

from __future__ import annotations

from pathlib import Path
import tokenize


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("scripts", "tools", "scripts_local_run", "tests")


def test_python_sources_are_valid() -> None:
    checked = 0
    for directory in SOURCE_DIRS:
        for path in sorted((ROOT / directory).rglob("*.py")):
            with tokenize.open(path) as source_file:
                source = source_file.read()
            compile(source, str(path), "exec")
            checked += 1
    assert checked > 0


if __name__ == "__main__":
    test_python_sources_are_valid()
    print("test_source_integrity.py: OK")

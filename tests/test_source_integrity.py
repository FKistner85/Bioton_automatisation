#!/usr/bin/env python3
"""Verify that maintained source and documentation files are valid UTF-8."""

from __future__ import annotations

from pathlib import Path
import tokenize


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("scripts", "tools", "scripts_local_run", "tests")
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".sh", ".txt", ".yaml", ".yml"}
EXCLUDED_DIRS = {".git", ".venv", ".venv_bacpipe", "__pycache__"}


def test_python_sources_are_valid() -> None:
    checked = 0
    for directory in SOURCE_DIRS:
        for path in sorted((ROOT / directory).rglob("*.py")):
            with tokenize.open(path) as source_file:
                source = source_file.read()
            compile(source, str(path), "exec")
            checked += 1
    assert checked > 0


def test_maintained_text_files_are_valid_utf8() -> None:
    checked = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        content = path.read_bytes()
        assert b"\x00" not in content, f"NUL byte in maintained text file: {path}"
        content.decode("utf-8")
        checked += 1
    assert checked > 0


if __name__ == "__main__":
    test_python_sources_are_valid()
    test_maintained_text_files_are_valid_utf8()
    print("test_source_integrity.py: OK")

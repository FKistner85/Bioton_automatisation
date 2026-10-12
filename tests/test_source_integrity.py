#!/usr/bin/env python3
"""Verify that maintained source and documentation files are valid UTF-8."""

from __future__ import annotations

from pathlib import Path
import os
import tokenize


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("scripts", "tools", "scripts_local_run", "tests")
MAINTAINED_DIRS = (*SOURCE_DIRS, "schemas", "Readmes")
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".sh", ".txt", ".yaml", ".yml"}
EXCLUDED_DIRS = {".git", ".venv", ".venv_bacpipe", "__pycache__"}


def maintained_files():
    yield from (p for p in ROOT.iterdir() if p.is_file())
    for directory in MAINTAINED_DIRS:
        for base, dirs, files in os.walk(ROOT / directory):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".venv")]
            yield from (Path(base) / name for name in files)


def test_python_sources_are_valid() -> None:
    checked = 0
    for path in sorted(maintained_files()):
        if path.suffix != ".py" or path.relative_to(ROOT).parts[0] not in SOURCE_DIRS:
            continue
        with tokenize.open(path) as source_file:
            source = source_file.read()
        compile(source, str(path), "exec")
        checked += 1
    assert checked > 0


def test_maintained_text_files_are_valid_utf8() -> None:
    checked = 0
    # Data snapshots, logs and temporary exports are not maintained sources;
    # walking them also makes this check depend on the size of the LSDF cache.
    for path in sorted(maintained_files()):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        content = path.read_bytes()
        assert b"\x00" not in content, f"NUL byte in maintained text file: {path}"
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AssertionError(f"Non-UTF-8 maintained text file: {path}") from exc
        checked += 1
    assert checked > 0


if __name__ == "__main__":
    test_python_sources_are_valid()
    test_maintained_text_files_are_valid_utf8()
    print("test_source_integrity.py: OK")

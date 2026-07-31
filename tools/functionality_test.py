#!/usr/bin/env python3
"""Fast functionality test for the HoreKa pipeline package.

The test checks environment imports, config structure, Python syntax and small
helper tests. It intentionally does not scan LSDF media folders or run expensive
geospatial overlays.
"""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
from pathlib import Path


REQUIRED_CONFIG_SECTIONS = [
    "lrt_cleaning",
    "lrt_grid_merge",
    "point_lrt_assignment",
    "susi_10m_products",
    "audio_inventory",
    "photo_inventory",
    "audio_download",
    "photo_download",
    "sentinel2_inventory",
    "sentinel2_download",
    "weather_inventory",
    "weather_download",
    "master_table",
    "bioacoustics",
]

REQUIRED_IMPORTS = [
    "pandas",
    "geopandas",
    "pyogrio",
    "shapely",
    "pyarrow",
    "PIL",
    "av",
    "rasterio",
    "requests",
    "xarray",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fast pipeline functionality checks.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    return parser.parse_args()


def check_imports() -> list[str]:
    failures = []
    for module in REQUIRED_IMPORTS:
        try:
            __import__(module)
        except Exception as exc:
            failures.append(f"{module}: {type(exc).__name__}: {exc}")
    return failures


def check_config(config_path: Path) -> list[str]:
    failures = []
    if not config_path.is_file():
        return [f"Config file missing: {config_path}"]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for section in REQUIRED_CONFIG_SECTIONS:
        if section not in config:
            failures.append(f"Missing config section: {section}")
    return failures


def check_schemas(root: Path) -> list[str]:
    failures = []
    schema_dir = root / "schemas"
    expected = [
        "step_manifest.schema.json",
        "formation_status_grid.schema.json",
        "media_inventory.schema.json",
        "weather_recording.schema.json",
        "sentinel2_inventory.schema.json",
        "master_table.schema.json",
        "bioacoustic_worklist.schema.json",
        "bioacoustic_prediction.schema.json",
        "bioacoustic_qc.schema.json",
        "status_model.json",
        "run_plan.schema.json",
    ]
    for name in expected:
        path = schema_dir / name
        if not path.is_file():
            failures.append(f"Missing schema: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"Invalid JSON schema {path}: {exc}")
            continue
        if not data.get("schema_name") or not data.get("schema_version"):
            failures.append(f"Schema lacks schema_name/schema_version: {path}")
        if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            failures.append(f"Schema is not JSON Schema Draft 2020-12: {path}")
        if data.get("type") != "object":
            failures.append(f"Schema root type is not object: {path}")
    return failures


def check_step_registry(root: Path) -> list[str]:
    path = root / "pipeline_steps.json"
    if not path.is_file():
        return [f"Missing pipeline step registry: {path}"]
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Invalid pipeline step registry: {exc}"]
    failures = []
    steps = registry.get("steps", {})
    if not steps:
        failures.append("Pipeline step registry has no steps.")
    for step, item in steps.items():
        script = item.get("script")
        if script and not (root / script).is_file():
            failures.append(f"Registered script missing for {step}: {script}")
        for dependency in item.get("depends_on", []):
            if dependency not in steps:
                failures.append(f"Unknown dependency for {step}: {dependency}")
    return failures


def check_step_readmes(root: Path) -> list[str]:
    failures = []
    readme_root = root / "Readmes"
    index = readme_root / "README_INDEX.md"
    if not index.is_file():
        return [f"Missing README index: {index}"]
    for directory in readme_root.iterdir():
        if not directory.is_dir():
            continue
        for name in ["README_DE.md", "README_EN.md"]:
            path = directory / name
            if not path.is_file() or path.stat().st_size == 0:
                failures.append(f"Missing or empty step README: {path}")
    return failures


def compile_python_files(root: Path) -> list[str]:
    failures = []
    for path in sorted((root / "scripts").glob("*.py")) + sorted((root / "tools").glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(f"{path}: {exc.msg}")
    return failures


def run_helper_tests(root: Path) -> list[str]:
    failures = []
    tests = sorted((root / "tests").glob("test_*.py"))
    if not tests:
        return [f"No regression tests found under {root / 'tests'}"]
    for test in tests:
        completed = subprocess.run(
            [sys.executable, str(test)],
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"{test.name}:\n{completed.stdout}")
        else:
            print(completed.stdout.strip())
    return failures


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    checks = {
        "imports": check_imports(),
        "config": check_config(args.config),
        "schemas": check_schemas(root),
        "step_registry": check_step_registry(root),
        "step_readmes": check_step_readmes(root),
        "syntax": compile_python_files(root),
        "helper_tests": run_helper_tests(root),
    }
    failed = {name: errors for name, errors in checks.items() if errors}
    if failed:
        print("Functionality test failed:")
        for name, errors in failed.items():
            print(f"\n[{name}]")
            for error in errors:
                print(f"- {error}")
        return 1
    print("Functionality test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

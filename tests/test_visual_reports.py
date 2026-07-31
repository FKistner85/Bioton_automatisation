#!/usr/bin/env python3
"""Regression test for static visual reports with partial pipeline outputs."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1] / "tools"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import generate_pipeline_visual_reports as reports


def test_partial_run_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = {
            "processed_root": str(root / "outputs"),
            "status_dir": str(root / "metadata"),
            "visual_reporting": {"output_dir": str(root / "report")},
            "lrt_grid_merge": {},
            "audio_inventory": {},
            "photo_inventory": {},
            "sentinel2_inventory": {},
            "weather_inventory": {},
            "hostrada_raster_quality_check": {},
            "bioacoustics": {},
            "master_table": {},
        }
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        previous_argv = sys.argv
        try:
            sys.argv = ["generate_pipeline_visual_reports.py", "--config", str(config_path)]
            assert reports.main() == 0
        finally:
            sys.argv = previous_argv
        output_dir = root / "report"
        assert (output_dir / "index.html").is_file()
        assert (output_dir / "07_step_7_mastertable.html").is_file()
        assert (output_dir / "report_manifest.json").is_file()


if __name__ == "__main__":
    test_partial_run_report()
    print("test_visual_reports.py: OK")

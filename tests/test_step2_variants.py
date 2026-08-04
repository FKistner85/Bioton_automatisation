#!/usr/bin/env python3
"""Synthetic tests for isolated Step-2 input variants."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import step2_variants as variants


def base_config(root: Path) -> dict:
    source = root / "All_Bundeslander"
    output = root / "outputs" / "step_2_variants"
    source.mkdir(parents=True)
    for name in [
        "All_Bundeslander_base_v2.gpkg",
        "All_Bundeslander_no_K_post2017_threshold_50.gpkg",
    ]:
        (source / name).write_bytes(b"synthetic")
    return {
        "manifest_dir": str(root / "manifests"),
        "status_dir": str(root / "status"),
        "lrt_variants": {
            "input_dir": str(source),
            "input_glob": "All_Bundeslander_*.gpkg",
            "primary_suffix": "no_K_post2017_threshold_50",
            "output_root": str(output),
            "index_json": str(output / "variant_index.json"),
        },
        "lrt_cleaning": {"source_gpkgs": [], "output_gpkg": "", "state_file": ""},
        "lrt_grid_merge": {
            "lrt_gpkg": "", "output_csv": "", "output_grid_gpkg": "",
            "output_grid_parquet": "", "chunk_checkpoint_dir": "", "state_file": "",
            "susi_compatible_outputs": {"output_dir": ""},
        },
        "point_lrt_assignment": {
            "grid_majority_csv": "", "lrt_gpkg": "", "output_csv": "",
            "matches_csv": "", "log_csv": "", "state_file": "",
        },
        "lrt_grid_aggregation": {"source_parquet": "", "output_dir": "", "state_file": ""},
        "susi_10m_products": {
            "source_100m_parquet": "", "lrt_gpkg": "", "output_dir": "",
            "grid_chunk_dir": "", "ix_chunk_dir": "", "parquet_chunk_dir": "",
            "final_parquet": "", "state_file": "",
        },
    }


def test_prepare_creates_isolated_configs() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = base_config(root)
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        _, discovered = variants.prepare(config_path)
        assert [item.suffix for item in discovered] == [
            "base_v2", "no_K_post2017_threshold_50",
        ]
        primary = discovered[1]
        generated = json.loads(primary.config_path.read_text(encoding="utf-8"))
        root_path = Path(config["lrt_variants"]["output_root"]) / primary.suffix
        assert Path(generated["lrt_cleaning"]["output_gpkg"]) == (
            root_path / "step_2_0" / f"lrt_{primary.suffix}.gpkg"
        )
        assert Path(generated["point_lrt_assignment"]["output_csv"]).parent == root_path / "step_2_2"
        assert Path(generated["susi_10m_products"]["final_parquet"]).name.endswith(
            f"_{primary.suffix}.parquet"
        )
        index = json.loads(Path(config["lrt_variants"]["index_json"]).read_text(encoding="utf-8"))
        assert index["variant_count"] == 2
        assert sum(bool(item["is_primary"]) for item in index["variants"]) == 1


def test_missing_primary_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = base_config(root)
        config["lrt_variants"]["primary_suffix"] = "does_not_exist"
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        try:
            variants.prepare(config_path)
        except ValueError as exc:
            assert "primary LRT variant is missing" in str(exc)
        else:
            raise AssertionError("A missing primary variant must stop preparation.")


if __name__ == "__main__":
    test_prepare_creates_isolated_configs()
    test_missing_primary_is_rejected()
    print("test_step2_variants.py: OK")

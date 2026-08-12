#!/usr/bin/env python3
"""Synthetic end-to-end test for the normalized formation variant table."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Step_7_1_update_formation_variant_table.py"
SPEC = importlib.util.spec_from_file_location("formation_variant_table", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_normalized_variant_table() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        for suffix in ["primary", "alternative"]:
            (inputs / f"All_Bundeslander_{suffix}.gpkg").write_bytes(b"source")
        metadata = root / "metadata.csv"
        pd.DataFrame({"id": [1, 2], "lat": [49.0, 50.0], "lon": [8.0, 9.0]}).to_csv(
            metadata, index=False
        )
        config = {
            "manifest_dir": str(outputs / "manifests"),
            "status_dir": str(outputs / "status"),
            "lrt_variants": {
                "input_dir": str(inputs),
                "input_glob": "All_Bundeslander_*.gpkg",
                "primary_suffix": "primary",
                "output_root": str(outputs / "step_2_variants"),
                "index_json": str(outputs / "step_2_variants/variant_index.json"),
                "master_csv": str(outputs / "Bio_O_Ton_Formation_Variants.csv"),
                "master_parquet": str(outputs / "Bio_O_Ton_Formation_Variants.parquet"),
                "master_summary_json": str(outputs / "Bio_O_Ton_Formation_Variants_summary.json"),
            },
            "lrt_cleaning": {"source_gpkgs": [], "output_gpkg": "", "state_file": ""},
            "lrt_grid_merge": {
                "lrt_gpkg": "", "output_csv": "", "output_grid_gpkg": "",
                "output_grid_parquet": "", "chunk_checkpoint_dir": "", "state_file": "",
                "susi_compatible_outputs": {"output_dir": ""},
            },
            "point_lrt_assignment": {
                "metadata_csv": str(metadata), "grid_id_column": "grid_id",
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
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        _, discovered = MODULE.prepare(config_path)
        for variant in discovered:
            generated = json.loads(variant.config_path.read_text(encoding="utf-8"))
            assignment = Path(generated["point_lrt_assignment"]["output_csv"])
            assignment.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "id": [1, 2],
                    "grid_id": ["g1", "g2"],
                    "inside_lrt_polygon": [True, False],
                    "lrt_polygon_count": [1, 0],
                    "lrt_codes": ["9110", ""],
                    "majority_formation": ["Forests", "Grassland"],
                    "majority_formation_status": ["A", "B"],
                    "majority_value": [7000, 6000],
                    "second_value": [2000, 3000],
                    "majority_delta": [5000, 3000],
                    "majority_disputed": [False, False],
                }
            ).to_csv(assignment, index=False)

        old_argv = sys.argv
        try:
            sys.argv = [SCRIPT.name, "--config", str(config_path)]
            assert MODULE.main() == 0
        finally:
            sys.argv = old_argv

        table = pd.read_parquet(config["lrt_variants"]["master_parquet"])
        assert len(table) == 4
        assert set(table["lrt_variant"]) == {"primary", "alternative"}
        assert table.groupby("dawn_chorus_id").size().eq(2).all()
        assert table["grid_100m_has_majority_formation"].all()
        assert int(table["inside_lrt_polygon"].sum()) == 2
        summary = pd.read_csv(outputs / "Bio_O_Ton_Variant_Summary.csv")
        assert summary["recordings_directly_in_lrt_polygon"].eq(1).all()
        assert not table["variant_10m_product_exists"].any()


if __name__ == "__main__":
    test_normalized_variant_table()
    print("test_formation_variant_table.py: OK")

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
        assert not table["variant_10m_product_exists"].any()
        assert table["variant_record_status"].eq("not_started").all()
        assert table["step_2_0_status"].eq("not_started").all()
        assert not table["variant_products_complete"].any()


def test_stage_status_requires_states_and_nonempty_outputs() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        (inputs / "All_Bundeslander_primary.gpkg").write_bytes(b"source")
        metadata = root / "metadata.csv"
        metadata.write_text("id,lat,lon\n1,49,8\n", encoding="utf-8")
        config = {
            "manifest_dir": str(outputs / "manifests"),
            "status_dir": str(outputs / "status"),
            "lrt_variants": {
                "input_dir": str(inputs),
                "input_glob": "All_Bundeslander_*.gpkg",
                "primary_suffix": "primary",
                "output_root": str(outputs / "step_2_variants"),
                "index_json": str(outputs / "variant_index.json"),
            },
            "lrt_cleaning": {"source_gpkgs": [], "output_gpkg": "", "state_file": ""},
            "lrt_grid_merge": {
                "lrt_gpkg": "", "output_csv": "", "output_grid_gpkg": "",
                "output_grid_parquet": "", "chunk_checkpoint_dir": "", "state_file": "",
                "susi_compatible_outputs": {"output_dir": ""},
            },
            "point_lrt_assignment": {
                "metadata_csv": str(metadata), "grid_majority_csv": "", "lrt_gpkg": "",
                "output_csv": "", "matches_csv": "", "log_csv": "", "state_file": "",
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
        generated = json.loads(discovered[0].config_path.read_text(encoding="utf-8"))

        paths = [
            Path(generated["lrt_cleaning"]["output_gpkg"]),
            Path(generated["lrt_grid_merge"]["output_grid_parquet"]),
            Path(generated["lrt_grid_merge"]["susi_compatible_outputs"]["output_dir"])
            / "Formation_Status_Grid_withLRTCode.parquet",
            Path(generated["point_lrt_assignment"]["output_csv"]),
            Path(generated["susi_10m_products"]["final_parquet"]),
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"output")
        stage23_output = Path(generated["lrt_grid_aggregation"]["output_dir"]) / "1km.csv"
        stage23_output.parent.mkdir(parents=True, exist_ok=True)
        stage23_output.write_bytes(b"output")
        for section in ["lrt_cleaning", "lrt_grid_merge", "point_lrt_assignment"]:
            state = Path(generated[section]["state_file"])
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text("{}", encoding="utf-8")
        Path(generated["lrt_grid_aggregation"]["state_file"]).write_text(
            json.dumps({"outputs": [str(stage23_output)]}), encoding="utf-8"
        )
        Path(generated["susi_10m_products"]["state_file"]).write_text(
            json.dumps({"status": "complete"}), encoding="utf-8"
        )

        statuses, issues = MODULE.inspect_variant_stages(generated)
        assert set(statuses.values()) == {"complete"}
        assert issues == []

        paths[-1].unlink()
        statuses, issues = MODULE.inspect_variant_stages(generated)
        assert statuses["2_4"] == "partial"
        assert "step_2_4:missing_or_empty_output" in issues


if __name__ == "__main__":
    test_normalized_variant_table()
    test_stage_status_requires_states_and_nonempty_outputs()
    print("test_formation_variant_table.py: OK")

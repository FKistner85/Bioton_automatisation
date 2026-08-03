#!/usr/bin/env python3
"""Step 2_5: Build Susi-compatible public LRT polygons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from Step_2_0_clean_lrts import (  # noqa: E402
    FORMATION_DEFINITION_VERSION,
    STATUS_RANK,
    file_fingerprint,
    lrt_formation,
    norm_lrt_code,
    read_all_lrt_layers,
    repair_polygons,
    resolve_within_formation,
)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if "public_lrt_cleaning" not in config:
        raise KeyError("Missing public_lrt_cleaning section in config.")
    return config


def normalise_state(state: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(state)
    cleaned.pop("result", None)
    return cleaned


def should_skip(
    output_gpkg: Path,
    state_file: Path,
    expected_state: dict[str, Any],
    force: bool,
) -> bool:
    if force or not output_gpkg.is_file() or not state_file.is_file():
        return False
    try:
        previous = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return normalise_state(previous) == expected_state


def write_state(
    state_file: Path,
    expected_state: dict[str, Any],
    output_rows: int,
) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {**expected_state, "result": {"output_rows": output_rows}},
            indent=2,
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean public LRT polygons with the table-based formation definition."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.horeka.json",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        settings = config["public_lrt_cleaning"]
        target_crs = int(settings.get("target_crs", 3035))
        eps_area = float(settings.get("eps_area", 1.0))
        output_gpkg = Path(settings["output_gpkg"])
        output_layer = settings.get("output_layer", "lrt")
        state_file = Path(
            settings.get(
                "state_file",
                output_gpkg.parent / "state.json",
            )
        )
        source_paths = [Path(path) for path in settings["source_gpkgs"]]

        expected_state = {
            "inputs": {
                "source_gpkgs": [
                    file_fingerprint(path) for path in source_paths
                ]
            },
            "processing": {
                "target_crs": target_crs,
                "eps_area": eps_area,
                "output_gpkg": str(output_gpkg.resolve()),
                "output_layer": output_layer,
                "formation_definition": FORMATION_DEFINITION_VERSION,
            },
        }

        if should_skip(
            output_gpkg,
            state_file,
            expected_state,
            args.force,
        ):
            print("Step 2_5 skipped: output exists and inputs are unchanged.")
            print(f"Output: {output_gpkg}")
            return 0

        parts = [
            read_all_lrt_layers(path, target_crs=target_crs)
            for path in source_paths
        ]
        lrt = gpd.GeoDataFrame(
            pd.concat(parts, ignore_index=True),
            geometry="geometry",
            crs=f"EPSG:{target_crs}",
        )
        lrt["LRT_code"] = norm_lrt_code(lrt["LRT_code"])
        lrt["Formation"] = lrt["LRT_code"].apply(lrt_formation)
        lrt = repair_polygons(lrt).explode(ignore_index=True)
        lrt["src_id"] = np.arange(len(lrt))
        lrt["status_rank"] = (
            lrt["conservation_status"].map(STATUS_RANK).fillna(0).astype(int)
        )
        lrt["mapping_year_num"] = pd.to_numeric(
            lrt["mapping_year"],
            errors="coerce",
        ).astype("Int64")

        results = []
        groups = list(lrt.groupby("Formation", dropna=False))
        for formation, df_form in tqdm(groups, desc="Public formations"):
            result = resolve_within_formation(df_form, eps_area=eps_area)
            if not result.empty:
                results.append(result)
            print(f"{formation}: {len(result):,} cleaned polygons")

        if not results:
            raise RuntimeError("No public LRT polygons remained after cleaning.")

        out = gpd.GeoDataFrame(
            pd.concat(results, ignore_index=True),
            geometry="geometry",
            crs=f"EPSG:{target_crs}",
        )
        drop_columns = [
            column
            for column in ["status_rank", "mapping_year_num"]
            if column in out.columns
        ]
        out = out.drop(columns=drop_columns)

        output_gpkg.parent.mkdir(parents=True, exist_ok=True)
        if output_gpkg.exists():
            output_gpkg.unlink()
        out.to_file(
            output_gpkg,
            layer=output_layer,
            driver="GPKG",
            engine="pyogrio",
        )
        write_state(state_file, expected_state, len(out))

        print("Step 2_5 completed.")
        print(f"Output rows: {len(out):,}")
        print(f"Output GPKG: {output_gpkg}")
        print(f"State file : {state_file}")
        return 0
    except Exception as exc:
        print(f"ERROR in Step 2_5: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

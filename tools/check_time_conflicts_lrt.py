"""Cross-check time-conflict recordings against primary 100 m LRT geometry."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--conflicts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    assignment_cfg = config["point_lrt_assignment"]
    conflicts = pd.read_csv(args.conflicts, dtype={"id": str})
    master = pd.read_csv(config["master_table"]["output_csv"], dtype={"dawn_chorus_id": str}, low_memory=False)
    master_columns = ["dawn_chorus_id", "grid_100m_id", "lat", "lon", "datetime_local",
                      "grid_100m_has_majority_formation", "inside_lrt_polygon"]
    selected = conflicts.drop(columns=["datetime_local"], errors="ignore").merge(
        master[master_columns], left_on="id", right_on="dawn_chorus_id", how="left", validate="one_to_one")
    assert len(selected) == len(conflicts) and selected.grid_100m_id.notna().all()
    majority = pd.read_csv(assignment_cfg["grid_majority_csv"], usecols=["grid_id", "majority_formation"])
    majority_ids = set(majority.loc[majority.majority_formation.notna(), "grid_id"])
    assignments = pd.read_csv(assignment_cfg["output_csv"], dtype={"id": str}, usecols=["id", "grid_id", "inside_lrt_polygon"])
    assignment_by_id = assignments.set_index("id")
    transformer = Transformer.from_crs(4326, 3035, always_xy=True)
    cell_results = []
    for grid_id, rows in selected.groupby("grid_100m_id", sort=True):
        match = re.fullmatch(r"100mN(\d+)E(\d+)", grid_id)
        if not match:
            raise ValueError(f"Unexpected grid identifier: {grid_id}")
        north, east = [int(v) * 100 for v in match.groups()]
        bounds = (east, north, east + 100, north + 100)
        # Read the actual stored cell, using its spatial index and ID together.
        cells = gpd.read_file(assignment_cfg["grid_gpkg"], layer=assignment_cfg["grid_layer"],
                              bbox=bounds, where=f"grid_id = '{grid_id}'")
        assert len(cells) == 1 and cells.crs.to_epsg() == 3035
        cell = cells.geometry.iloc[0]
        assert abs(cell.area - 10000) < 0.01
        polygons = gpd.read_file(assignment_cfg["lrt_gpkg"], layer=assignment_cfg["lrt_layer"], bbox=cell.bounds)
        assert polygons.crs.to_epsg() == 3035
        areas = polygons.geometry.intersection(cell).area
        overlaps = int(areas.gt(0).sum())
        boundary_contacts = int((polygons.geometry.intersects(cell) & areas.eq(0)).sum())
        cell_results.append({"grid_100m_id": grid_id, "conflict_recordings": len(rows),
                             "lrt_polygons_with_positive_area": overlaps,
                             "lrt_boundary_contacts_only": boundary_contacts,
                             "has_majority_table_entry": grid_id in majority_ids})
        for idx, row in rows.iterrows():
            point = Point(*transformer.transform(row.lon, row.lat))
            assert cell.covers(point), f"Point outside assigned grid: {row.id}"
            assert assignment_by_id.loc[row.id, "grid_id"] == grid_id
            inside = bool(polygons.geometry.contains(point).any())
            touches_or_inside = bool(polygons.geometry.covers(point).any())
            assert inside == bool(row.inside_lrt_polygon) == bool(assignment_by_id.loc[row.id, "inside_lrt_polygon"])
            assert bool(row.grid_100m_has_majority_formation) == (grid_id in majority_ids)
            selected.loc[idx, "cell_has_lrt_geometry"] = overlaps > 0
            selected.loc[idx, "point_inside_lrt_geometry"] = inside
            selected.loc[idx, "point_covered_by_lrt_geometry"] = touches_or_inside
        print(f"Checked {grid_id}: {len(rows)} recordings; {overlaps} LRT overlaps", flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output_dir / "time_conflicts_lrt.csv", index=False)
    pd.DataFrame(cell_results).to_csv(args.output_dir / "time_conflict_grid_cells.csv", index=False)
    summary = {"variant": config["lrt_variants"]["primary_suffix"], "conflict_recordings": len(selected),
               "unique_100m_cells": len(cell_results),
               "recordings_in_cells_with_lrt_geometry": int(selected.cell_has_lrt_geometry.sum()),
               "recordings_in_cells_with_majority_formation": int(selected.grid_100m_has_majority_formation.sum()),
               "recordings_inside_lrt_polygons": int(selected.point_inside_lrt_geometry.sum()),
               "recordings_covered_by_lrt_polygons": int(selected.point_covered_by_lrt_geometry.sum()),
               "source_conflicts": str(args.conflicts), "master": config["master_table"]["output_csv"],
               "grid": assignment_cfg["grid_gpkg"], "lrt": assignment_cfg["lrt_gpkg"],
               "majority_table": assignment_cfg["grid_majority_csv"],
               "checks": "actual grid geometries, point containment, LRT polygon overlap, majority table, point assignment and master flags"}
    (args.output_dir / "time_conflicts_lrt_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

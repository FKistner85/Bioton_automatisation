#!/usr/bin/env python3
"""Fill missing master grid IDs using the pipeline's original spatial logic.

Writes a separate CSV; existing IDs and unrelated cell values are preserved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from Step_7_0_update_master_table import complete_100m_grid_ids, compute_10m_grid_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--grid-gpkg", type=Path, required=True)
    parser.add_argument("--grid-layer", default="grid")
    parser.add_argument("--grid-id-column", default="grid_id")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Use a separate output path; verify before replacing the original.")
    original = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    result = original.copy()
    spatial = original[["lat", "lon", "grid_100m_id"]].replace("", pd.NA)
    print(f"Rows: {len(original)}; resolving missing 100 m IDs", flush=True)
    spatial = complete_100m_grid_ids(spatial, {"point_lrt_assignment": {
        "grid_gpkg": str(args.grid_gpkg), "grid_layer": args.grid_layer,
        "grid_id_column": args.grid_id_column,
    }})
    print("Deriving 10 m IDs with the unchanged pipeline function", flush=True)
    spatial["grid_10m_id"] = compute_10m_grid_ids(spatial)
    report = {"rows": len(original)}
    allowed = set()
    for size in ("100m", "10m"):
        column = f"grid_{size}_id"
        existing = original[column].ne("")
        mismatch = existing & spatial[column].fillna("").ne(original[column])
        if mismatch.any():
            raise ValueError(f"{int(mismatch.sum())} existing {column} values disagree; no output written")
        result.loc[~existing, column] = spatial.loc[~existing, column].fillna("")
        exists = result[column].ne("")
        flag = f"grid_{size}_assignment_exists"
        result[flag] = exists.map({True: "True", False: "False"})
        status = f"formation_{size}_status"
        majority = original[f"grid_{size}_has_majority_formation"].str.lower().eq("true")
        result[status] = "missing"
        result.loc[exists, status] = "has_issues"
        result.loc[exists & majority, status] = "validated"
        allowed.update((column, flag, status))
        report[f"{size}_filled"] = int((~existing & exists).sum())
        report[f"{size}_remaining_missing"] = int((~exists).sum())
    untouched = [c for c in original.columns if c not in allowed]
    pd.testing.assert_frame_equal(original[untouched], result[untouched])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    saved = pd.read_csv(args.output, dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(result, saved)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

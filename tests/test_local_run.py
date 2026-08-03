Exit code: 0
Wall time: 3 seconds
Output:
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts_local_run" / "prepare_local_config.py"
SPEC = importlib.util.spec_from_file_location("prepare_local_config", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_local_path_mapping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    mount = tmp_path / "mount"
    cache = workspace / "lsdf_cache"
    sources: dict[Path, Path] = {}

    result = MODULE.transform_value(
        {
            "output": "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_1/a.csv",
            "audio": "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/SoundRecordings",
            "grid": "/lsdf/kit/ipf/projects/Bio-O-Ton/InspireGrid/Vector_Data/grid.gpkg",
            "reference": "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/bio_o_ton_pipeline/scripts_horeka/reference_data/germany_species_allowlist.csv",
        },
        repo_root=repo,
        workspace=workspace,
        mounted_project=mount,
        cache_root=cache,
        cache_sources=sources,
    )

    assert Path(result["output"]) == (workspace / "outputs/step_1/a.csv").resolve()
    assert Path(result["audio"]) == (mount / "PointData/SoundRecordings").resolve()
    assert Path(result["grid"]) == (cache / "InspireGrid/Vector_Data/grid.gpkg").resolve()
    assert Path(result["reference"]) == (repo / "reference_data/germany_species_allowlist.csv").resolve()
    assert sources == {
        mount / "InspireGrid/Vector_Data/grid.gpkg": cache / "InspireGrid/Vector_Data/grid.gpkg"
    }


def test_copy_if_changed_reuses_identical_file(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "cache" / "source.bin"
    source.write_bytes(b"abc")
    MODULE.copy_if_changed(source, destination)
    first_mtime = destination.stat().st_mtime_ns
    MODULE.copy_if_changed(source, destination)
    assert destination.read_bytes() == b"abc"
    assert destination.stat().st_mtime_ns == first_mtime


if __name__ == "__main__":
    for test in (test_local_path_mapping, test_copy_if_changed_reuses_identical_file):
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    print("test_local_run.py: OK")


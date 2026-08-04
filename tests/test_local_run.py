from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts_local_run" / "prepare_local_config.py"
SPEC = importlib.util.spec_from_file_location("prepare_local_config", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SYNC_MODULE_PATH = ROOT / "scripts_local_run" / "sync_horeka_outputs.py"
SYNC_SPEC = importlib.util.spec_from_file_location("sync_horeka_outputs", SYNC_MODULE_PATH)
assert SYNC_SPEC and SYNC_SPEC.loader
SYNC_MODULE = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(SYNC_MODULE)

PUBLISH_MODULE_PATH = ROOT / "scripts_local_run" / "publish_local_outputs.py"
PUBLISH_SPEC = importlib.util.spec_from_file_location("publish_local_outputs", PUBLISH_MODULE_PATH)
assert PUBLISH_SPEC and PUBLISH_SPEC.loader
PUBLISH_MODULE = importlib.util.module_from_spec(PUBLISH_SPEC)
PUBLISH_SPEC.loader.exec_module(PUBLISH_MODULE)

MOUNT_MODULE_PATH = ROOT / "scripts_local_run" / "mount_lsdf.py"
MOUNT_SPEC = importlib.util.spec_from_file_location("mount_lsdf", MOUNT_MODULE_PATH)
assert MOUNT_SPEC and MOUNT_SPEC.loader
MOUNT_MODULE = importlib.util.module_from_spec(MOUNT_SPEC)
MOUNT_SPEC.loader.exec_module(MOUNT_MODULE)

ORCHESTRATOR_PATH = ROOT / "scripts_local_run" / "local_orchestrator.py"
ORCHESTRATOR_SPEC = importlib.util.spec_from_file_location("local_orchestrator", ORCHESTRATOR_PATH)
assert ORCHESTRATOR_SPEC and ORCHESTRATOR_SPEC.loader
ORCHESTRATOR_MODULE = importlib.util.module_from_spec(ORCHESTRATOR_SPEC)
sys.modules[ORCHESTRATOR_SPEC.name] = ORCHESTRATOR_MODULE
ORCHESTRATOR_SPEC.loader.exec_module(ORCHESTRATOR_MODULE)


def test_local_path_mapping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    mount = tmp_path / "mount"
    cache = workspace / "lsdf_cache"
    sources: dict[Path, Path] = {}

    result = MODULE.transform_value(
        {
            "output": "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_1/a.csv",
            "weather_cache": "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_5_2_weather_download/hostrada_cache/a.nc",
            "monthly_cache": "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_5_3_hostrada_monthly_download/netcdf/a.nc",
            "audio": "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/SoundRecordings",
            "lrt_variants": "/lsdf/kit/ipf/projects/Bio-O-Ton/Biodiversity_data/Bundeslander/All_Bundeslander",
            "lrt_variant": "/lsdf/kit/ipf/projects/Bio-O-Ton/Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_base_v2.gpkg",
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
    assert Path(result["weather_cache"]) == (
        mount
        / "Data_automatisation_skripts/outputs/step_5_2_weather_download/hostrada_cache/a.nc"
    ).resolve()
    assert Path(result["monthly_cache"]) == (
        mount
        / "Data_automatisation_skripts/outputs/step_5_3_hostrada_monthly_download/netcdf/a.nc"
    ).resolve()
    assert Path(result["audio"]) == (mount / "PointData/SoundRecordings").resolve()
    assert Path(result["lrt_variants"]) == (
        mount / "Biodiversity_data/Bundeslander/All_Bundeslander"
    ).resolve()
    assert Path(result["lrt_variant"]) == (
        mount / "Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_base_v2.gpkg"
    ).resolve()
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


def test_optional_config_input_does_not_block_cache(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    required = mount / "InspireGrid/Vector_Data/grid.gpkg"
    optional_grid = mount / "InspireGrid/Vector_Data/grid_public.gpkg"
    optional_lrt = mount / "Biodiversity_data/Bundeslander/LRT_Germany_Clean.gpkg"
    required.parent.mkdir(parents=True)
    required.write_bytes(b"required")
    required_destination = tmp_path / "cache/grid.gpkg"
    optional_grid_destination = tmp_path / "cache/grid_public.gpkg"
    optional_lrt_destination = tmp_path / "cache/LRT_Germany_Clean.gpkg"

    MODULE.copy_config_inputs(
        {
            required: required_destination,
            optional_grid: optional_grid_destination,
            optional_lrt: optional_lrt_destination,
        },
        mounted_project=mount,
        optional_inputs=MODULE.optional_input_paths(
            {"optional_lsdf_inputs": ["InspireGrid/Vector_Data/grid_public.gpkg"]}
        ),
    )

    assert required_destination.read_bytes() == b"required"
    assert not optional_grid_destination.exists()
    assert not optional_lrt_destination.exists()


def test_horeka_output_bootstrap_excludes_runtime_files(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    remote = mount / "Data_automatisation_skripts" / "outputs"
    workspace = tmp_path / "workspace"
    (remote / "step_1_metadata").mkdir(parents=True)
    (remote / "step_0_slurm_logs").mkdir(parents=True)
    (remote / "step_0_control" / "run_plans").mkdir(parents=True)
    (remote / "step_0_control" / "pipeline.lock").mkdir(parents=True)
    (remote / "step_2_4_susi_10m" / "grid10m_chunks").mkdir(parents=True)
    (remote / "step_5_2_weather_download" / "hostrada_cache").mkdir(parents=True)
    (remote / "step_5_3_hostrada_monthly_download" / "netcdf").mkdir(parents=True)
    (remote / "step_1_metadata" / "metadata_source_fingerprints.csv").write_text(
        "dawn_chorus_id\n1\n", encoding="utf-8"
    )
    (remote / "step_0_slurm_logs" / "old.out").write_text("old", encoding="utf-8")
    (remote / "step_0_control" / "run_plans" / "old.json").write_text("{}", encoding="utf-8")
    (remote / "step_0_control" / "pipeline.lock" / "owner.json").write_text(
        "{}", encoding="utf-8"
    )
    (remote / "step_2_4_susi_10m" / "grid10m_chunks" / "part.gpkg").write_text(
        "intermediate", encoding="utf-8"
    )
    (remote / "step_5_2_weather_download" / "hostrada_cache" / "month.nc").write_text(
        "shared cache", encoding="utf-8"
    )
    (remote / "step_5_3_hostrada_monthly_download" / "netcdf" / "month.nc").write_text(
        "shared cache", encoding="utf-8"
    )

    settings = {
        "mount_drive": str(mount),
        "workspace_dir": str(workspace),
        "horeka_outputs_relative": "Data_automatisation_skripts/outputs",
    }
    result = SYNC_MODULE.sync_outputs(settings)

    assert result["status"] == "complete"
    assert (workspace / "outputs/step_1_metadata/metadata_source_fingerprints.csv").is_file()
    assert not (workspace / "outputs/step_0_slurm_logs/old.out").exists()
    assert not (workspace / "outputs/step_0_control/run_plans/old.json").exists()
    assert not (workspace / "outputs/step_0_control/pipeline.lock/owner.json").exists()
    assert not (
        workspace / "outputs/step_2_4_susi_10m/grid10m_chunks/part.gpkg"
    ).exists()
    assert not (
        workspace / "outputs/step_5_2_weather_download/hostrada_cache/month.nc"
    ).exists()
    assert not (
        workspace / "outputs/step_5_3_hostrada_monthly_download/netcdf/month.nc"
    ).exists()
    assert result["excluded_directories"] >= 1


def test_local_publish_translates_paths_and_excludes_runtime(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    remote = mount / "Data_automatisation_skripts" / "outputs"
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    remote.mkdir(parents=True)
    local_outputs = workspace / "outputs"
    (local_outputs / "step_3_0_a_audio_inventory").mkdir(parents=True)
    (local_outputs / "step_0_local_logs").mkdir(parents=True)
    local_audio = mount / "PointData" / "SoundRecordings" / "1_audio.wav"
    (local_outputs / "step_3_0_a_audio_inventory" / "state.json").write_text(
        json.dumps({"output": str(local_outputs / "x.csv"), "audio": str(local_audio)}),
        encoding="utf-8",
    )
    (local_outputs / "step_0_local_logs" / "local.log").write_text("local", encoding="utf-8")

    settings = {
        "mount_drive": str(mount),
        "workspace_dir": str(workspace),
        "horeka_outputs_relative": "Data_automatisation_skripts/outputs",
        "cluster_project_root": "/lsdf/kit/ipf/projects/Bio-O-Ton",
    }
    result = PUBLISH_MODULE.publish_outputs(settings, repo)

    assert result["status"] == "complete"
    published = json.loads(
        (remote / "step_3_0_a_audio_inventory/state.json").read_text(encoding="utf-8")
    )
    assert published["output"].startswith(
        "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs"
    )
    assert published["audio"].startswith(
        "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/SoundRecordings"
    )
    assert not (remote / "step_0_local_logs/local.log").exists()


def test_sshfs_root_unc(_tmp_path: Path) -> None:
    assert MOUNT_MODULE.sshfs_unc(
        "jk3038",
        "os-login.lsdf.kit.edu",
        "/lsdf01/lsdf/kit/ipf/projects/Bio-O-Ton",
    ) == (
        r"\\sshfs.r\jk3038@os-login.lsdf.kit.edu"
        r"\lsdf01\lsdf\kit\ipf\projects\Bio-O-Ton"
    )


def test_stale_sshfs_mapping_is_cleared(_tmp_path: Path) -> None:
    expected = MOUNT_MODULE.sshfs_unc(
        "jk3038",
        "os-login.lsdf.kit.edu",
        "/lsdf01/lsdf/kit/ipf/projects/Bio-O-Ton",
    )
    with (
        patch.object(MOUNT_MODULE, "current_mapping", return_value=expected),
        patch.object(MOUNT_MODULE, "cancel_mapping") as cancel,
    ):
        MOUNT_MODULE.clear_stale_mapping("L:", expected)
        cancel.assert_called_once_with("L:", ignore_missing=True)

    with patch.object(
        MOUNT_MODULE,
        "current_mapping",
        return_value=r"\\server\unrelated",
    ):
        try:
            MOUNT_MODULE.clear_stale_mapping("L:", expected)
        except OSError as exc:
            assert "anders belegt" in str(exc)
        else:
            raise AssertionError("An unrelated drive mapping must not be removed.")


def test_transport_error_log_detection(tmp_path: Path) -> None:
    log = tmp_path / "step.err"
    log.write_text("old text\n", encoding="utf-8")
    offset = log.stat().st_size
    with log.open("a", encoding="utf-8") as handle:
        handle.write("OSError: [WinError 995] transport interrupted\n")
    assert ORCHESTRATOR_MODULE.log_has_transport_error(log, offset)
    assert not ORCHESTRATOR_MODULE.log_has_transport_error(log, log.stat().st_size)


def test_stale_foreign_local_lock_is_released(tmp_path: Path) -> None:
    lock = tmp_path / "pipeline.lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps({"host": "cluster.example", "pid": 999999}),
        encoding="utf-8",
    )
    assert ORCHESTRATOR_MODULE.release_stale_local_lock(
        {"pipeline_control": {"lock_dir": str(lock)}}
    )
    assert not lock.exists()


def test_live_local_lock_is_preserved(tmp_path: Path) -> None:
    lock = tmp_path / "pipeline.lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps({"host": ORCHESTRATOR_MODULE.socket.gethostname(), "pid": os.getpid()}),
        encoding="utf-8",
    )
    assert not ORCHESTRATOR_MODULE.release_stale_local_lock(
        {"pipeline_control": {"lock_dir": str(lock)}}
    )
    assert lock.exists()


def test_local_dependencies_require_success_by_default(_tmp_path: Path) -> None:
    pipeline = ORCHESTRATOR_MODULE.Pipeline.__new__(ORCHESTRATOR_MODULE.Pipeline)
    pipeline.steps = {}
    pipeline.add("upstream", "upstream", lambda: 0)
    pipeline.add("downstream", "downstream", lambda: 0, ["upstream"])
    assert pipeline.steps["downstream"].dependencies == ["upstream"]
    assert pipeline.steps["downstream"].require_success == ["upstream"]


if __name__ == "__main__":
    for test in (
        test_local_path_mapping,
        test_copy_if_changed_reuses_identical_file,
        test_optional_config_input_does_not_block_cache,
        test_horeka_output_bootstrap_excludes_runtime_files,
        test_local_publish_translates_paths_and_excludes_runtime,
        test_sshfs_root_unc,
        test_stale_sshfs_mapping_is_cleared,
        test_transport_error_log_detection,
        test_stale_foreign_local_lock_is_released,
        test_live_local_lock_is_preserved,
        test_local_dependencies_require_success_by_default,
    ):
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    print("test_local_run.py: OK")

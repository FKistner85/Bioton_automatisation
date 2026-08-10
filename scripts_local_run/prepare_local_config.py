#!/usr/bin/env python3
"""Generate a Windows-local config from config.horeka.json."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any


REMOTE_PROJECT = "/lsdf/kit/ipf/projects/Bio-O-Ton"
REMOTE_OUTPUTS = REMOTE_PROJECT + "/Data_automatisation_skripts/outputs"
REMOTE_PIPELINE = REMOTE_PROJECT + "/Data_automatisation_skripts/bio_o_ton_pipeline/scripts_horeka"
DIRECT_REMOTE_DIRS = (
    "PointData/SoundRecordings",
    "PointData/Images_SoundRecordings",
    "PointData/Weather/Hostrada",
    "PointData/S2",
)
LOCAL_CACHE_DIRECTORIES = (
    "Biodiversity_data/Bundeslander/All_Bundeslander",
)
DEFAULT_SHARED_OUTPUT_PREFIXES = (
    "step_5_2_weather_download/hostrada_cache",
    "step_5_3_hostrada_monthly_download/netcdf",
    "step_5_4_hostrada_raster_products",
)
DEFAULT_OPTIONAL_LSDF_INPUTS = (
    "InspireGrid/Vector_Data/grid_public.gpkg",
    "Biodiversity_data/Bundeslander/LRT_Germany_Clean.gpkg",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def windows_path(path: Path) -> str:
    return str(path.resolve())


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


def copy_if_changed(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"LSDF-Eingabedatei fehlt: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_stat = source.stat()
    unchanged = (
        destination.is_file()
        and destination.stat().st_size == source_stat.st_size
        and destination.stat().st_mtime_ns == source_stat.st_mtime_ns
    )
    if unchanged:
        print(f"CACHE unveraendert: {destination}")
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"CACHE {source} -> {destination}")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def copy_config_inputs(
    cache_sources: dict[Path, Path],
    *,
    mounted_project: Path,
    optional_inputs: set[str],
) -> None:
    for source, destination in sorted(cache_sources.items(), key=lambda item: str(item[0])):
        try:
            relative = source.relative_to(mounted_project).as_posix().casefold()
        except ValueError:
            relative = ""
        if not source.is_file() and relative in optional_inputs:
            print(f"CACHE optional nicht vorhanden, uebersprungen: {source}")
            continue
        copy_if_changed(source, destination)


def copy_directory_if_changed(source: Path, destination: Path) -> None:
    """Mirror a required input directory into the local cache."""
    if not source.is_dir():
        raise FileNotFoundError(f"LSDF-Eingabeordner fehlt: {source}")
    for item in source.rglob("*"):
        if item.is_file():
            copy_if_changed(item, destination / item.relative_to(source))


def optional_input_paths(settings: dict) -> set[str]:
    paths = {value.casefold() for value in DEFAULT_OPTIONAL_LSDF_INPUTS}
    paths.update(
        str(value).replace("\\", "/").strip("/").casefold()
        for value in settings.get("optional_lsdf_inputs", ())
        if str(value).strip()
    )
    return paths


def project_relative(value: str) -> str | None:
    normalised = value.replace("\\", "/")
    prefixes = (
        REMOTE_PROJECT + "/",
        "/lsdf01/lsdf/kit/ipf/projects/Bio-O-Ton/",
        "/gfse/data/LSDF/lsdf01/lsdf/kit/ipf/projects/Bio-O-Ton/",
    )
    for prefix in prefixes:
        if normalised.startswith(prefix):
            return normalised[len(prefix):]
    return None


def transform_value(
    value: Any,
    *,
    repo_root: Path,
    workspace: Path,
    mounted_project: Path,
    cache_root: Path,
    cache_sources: dict[Path, Path],
    shared_output_prefixes: tuple[str, ...] = DEFAULT_SHARED_OUTPUT_PREFIXES,
) -> Any:
    if isinstance(value, dict):
        return {
            key: transform_value(
                item,
                repo_root=repo_root,
                workspace=workspace,
                mounted_project=mounted_project,
                cache_root=cache_root,
                cache_sources=cache_sources,
                shared_output_prefixes=shared_output_prefixes,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            transform_value(
                item,
                repo_root=repo_root,
                workspace=workspace,
                mounted_project=mounted_project,
                cache_root=cache_root,
                cache_sources=cache_sources,
                shared_output_prefixes=shared_output_prefixes,
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value

    normalised = value.replace("\\", "/")
    if normalised.startswith(REMOTE_OUTPUTS + "/") or normalised == REMOTE_OUTPUTS:
        relative = normalised[len(REMOTE_OUTPUTS):].lstrip("/")
        relative_casefold = relative.casefold()
        if any(
            relative_casefold == prefix
            or relative_casefold.startswith(prefix + "/")
            for prefix in shared_output_prefixes
        ):
            return windows_path(
                mounted_project
                / "Data_automatisation_skripts"
                / "outputs"
                / Path(*PurePosixPath(relative).parts)
            )
        return windows_path(workspace / "outputs" / Path(*PurePosixPath(relative).parts))
    if normalised.startswith(REMOTE_PIPELINE + "/") or normalised == REMOTE_PIPELINE:
        relative = normalised[len(REMOTE_PIPELINE):].lstrip("/")
        if relative.startswith("bacpipe/model_checkpoints"):
            suffix = relative.removeprefix("bacpipe/model_checkpoints").lstrip("/")
            return windows_path(workspace / "model_checkpoints" / Path(*PurePosixPath(suffix).parts))
        return windows_path(repo_root / Path(*PurePosixPath(relative).parts))

    relative = project_relative(normalised)
    if relative is None:
        return value
    relative_path = Path(*PurePosixPath(relative).parts)
    if any(relative == prefix or relative.startswith(prefix + "/") for prefix in DIRECT_REMOTE_DIRS):
        return windows_path(mounted_project / relative_path)

    if any(relative == prefix or relative.startswith(prefix + "/") for prefix in LOCAL_CACHE_DIRECTORIES):
        return windows_path(cache_root / relative_path)

    source = mounted_project / relative_path
    destination = cache_root / relative_path
    cache_sources[source] = destination
    return windows_path(destination)


def apply_local_resources(config: dict, settings: dict) -> None:
    logical = max(1, int(settings.get("logical_cpus", 20)))
    process_workers = max(1, min(10, logical // 2))
    thread_workers = max(1, min(20, logical))
    download_workers = max(1, min(12, logical))

    config["lrt_cleaning"]["processes"] = process_workers
    config["lrt_grid_merge"]["processes"] = process_workers
    config["lrt_grid_aggregation"]["processes"] = min(3, process_workers)
    config["susi_10m_products"]["write_grid_chunks"] = bool(
        settings.get("step2_10m_write_grid_chunks", False)
    )
    config["susi_10m_products"]["write_ix_chunks"] = bool(
        settings.get("step2_10m_write_ix_chunks", False)
    )
    config["audio_inventory"]["workers"] = thread_workers
    config["photo_inventory"]["workers"] = thread_workers
    config["audio_download"]["workers"] = download_workers
    config["photo_download"]["workers"] = download_workers
    config["sentinel2_inventory"]["workers"] = thread_workers
    config["weather_inventory"]["workers"] = thread_workers
    config["weather_download"]["cache_download_workers"] = download_workers
    config["weather_download"]["cache_download_max_workers"] = download_workers
    config["weather_download"]["recording_workers"] = download_workers
    config["weather_download"]["recording_max_workers"] = download_workers
    config["hostrada_monthly_download"]["workers"] = download_workers
    config["hostrada_raster_quality_check"]["workers"] = thread_workers
    config["master_table"]["weather_qc_workers"] = thread_workers
    config["bioacoustics"]["max_concurrent_tasks"] = int(
        settings.get("bioacoustic_array_workers_gpu", 1)
        if config["bioacoustics"].get("device") == "cuda"
        else settings.get("bioacoustic_array_workers_cpu", 2)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--skip-cache-copy", action="store_true")
    args = parser.parse_args()

    settings = load_json(args.settings)
    source_config = load_json(args.source_config)
    repo_root = args.repo_root.resolve()
    workspace = Path(settings["workspace_dir"]).expanduser().resolve()
    mounted_project = mount_root(settings)
    cache_root = workspace / "lsdf_cache"
    if not args.skip_cache_copy and not (mounted_project / "PointData").is_dir():
        raise FileNotFoundError(f"LSDF-Mount ist nicht lesbar: {mounted_project}")

    if not args.skip_cache_copy:
        for relative in LOCAL_CACHE_DIRECTORIES:
            relative_path = Path(*PurePosixPath(relative).parts)
            copy_directory_if_changed(
                mounted_project / relative_path,
                cache_root / relative_path,
            )

    cache_sources: dict[Path, Path] = {}
    shared_output_prefixes = tuple(
        str(value).replace("\\", "/").strip("/").casefold()
        for value in settings.get(
            "shared_lsdf_output_prefixes",
            DEFAULT_SHARED_OUTPUT_PREFIXES,
        )
        if str(value).strip()
    )
    config = transform_value(
        source_config,
        repo_root=repo_root,
        workspace=workspace,
        mounted_project=mounted_project,
        cache_root=cache_root,
        cache_sources=cache_sources,
        shared_output_prefixes=shared_output_prefixes,
    )
    config["local_runtime"] = {
        "workspace_dir": windows_path(workspace),
        "mounted_project_root": windows_path(mounted_project),
        "logical_cpus": int(settings.get("logical_cpus", 20)),
        "max_parallel_steps": int(settings.get("max_parallel_steps", 2)),
        "array_workers": int(settings.get("array_workers", 2)),
        "hostrada_execution": str(
            settings.get("hostrada_execution", "local")
        ).strip().casefold(),
    }
    config["slurm_log_dir"] = windows_path(workspace / "outputs" / "step_0_local_logs")
    config["bioacoustics"]["device"] = args.device

    credentials = repo_root / "credentials.json"
    token = workspace / "google_token.json"
    if "sentinel2_download" in config:
        config["sentinel2_download"]["credentials_path"] = windows_path(credentials)
        config["sentinel2_download"]["token_path"] = windows_path(token)

    apply_local_resources(config, settings)
    if not args.skip_cache_copy:
        optional_inputs = optional_input_paths(settings)
        copy_config_inputs(
            cache_sources,
            mounted_project=mounted_project,
            optional_inputs=optional_inputs,
        )

    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_config.with_suffix(args.output_config.suffix + ".part")
    temporary.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, args.output_config)
    print(args.output_config.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


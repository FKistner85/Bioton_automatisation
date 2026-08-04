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
    "Biodiversity_data/Bundeslander/All_Bundeslander",
    "PointData/SoundRecordings",
    "PointData/Images_SoundRecordings",
    "PointData/Weather/Hostrada",
    "PointData/S2",
)
DEFAULT_SHARED_OUTPUT_PREFIXES = (
    "step_5_2_weather_download/hostrada_cache",
    "step_5_3_hostrada_monthly_download/netcdf",
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


def optional_input_paths(settings: dict) -> set[str]:
    paths = {value.casefold() for value in DEFAULT_OPTIONAL_LSDF_INPUTS}
    paths.update(
        str(value).replace("\\", "/").strip("/").casefold()
        for value in settings.get("o}¶лЫh‘йм¶»§q«^wЫЩЧЩ\€—HHЪ[™ЭЬЧЬ]
ЫЬљЬЬXЩHИ›Э]]И€ИњЭ\МЫШШ[ЫЩЬИЉB€ЫЫ™љYЦИљ[ШXЫЭ\ЭXЬИ—VИ™]љXЩH—HH\™ЬЛ™]љXЩB‚€Ь™Y[ќX[ИH™\ЧЬ›ЫЭИЬ™Y[ќX[ЛљњЫЫ€‚€ЪЩ[€HЫЬљЬЬXЩHИ™ЫЫЩЫWЭЪЩ[‹љњЫЫ€‚€Y€њЩ[ќ[™[—ЩЭЫ›ШY€[€ЫЫ™љYО‚€ЫЫ™љYЦИњЩ[ќ[™[—ЩЭЫ›ШY—VИЬ™Y[ќX[ЧЬ]—HHЪ[™ЭЬЧЬ]
Ь™Y[ќX[КB€ЫЫ™љYЦИњЩ[ќ[™[—ЩЭЫ›ШY—VИќЪЩ[—Ь]—HHЪ[™ЭЬЧЬ]
ЪЩ[ЉB‚€\WЫШШ[Ь™\ЫЭ\Щ\КЫЫ™љYЛЩ][™ЬКB€Y€›Э\™ЬЛњЪЪ\ШШXЪWШЫЬN‚€Ь[Ы[Ъ[њ]ИHЬ[Ы[Ъ[њ]Ь]КЩ][™ЬКB€ЫЬWШЫЫ™љYЧЪ[њ]К€ШXЪWЬЫЭ\Щ\Л€[Э[ќYЬ›Ъ™XЭ[[Э[ќYЬ›Ъ™XЭ€Ь[Ы[Ъ[њ]П[Ь[Ы[Ъ[њ]Л€
B‚€\™ЬЛ›Э]]ШЫЫ™љYЛњ\™[ќ›ZЩ\Љ\™[ќПUќYK^\ЭЫЪПUќYJB€[\Ь\ћHH\™ЬЛ›Э]]ШЫЫ™љYЛќЪ]ЬЭY™љ^
\™ЬЛ›Э]]ШЫЫ™љYЛњЭY™љ^
И‹њ\ќЉB€[\Ь\ћKќЬљ]WЭ^
њЫЫ‹™[\КЫЫ™љYЛ[™[ќL‹[њЭ\™WШ\ШЪZOQ[ЩJH
И—€‹[ЫЩ[™ПHќ]‹NЉB€ЬЛњ™\XЩJ[\Ь\ћK\™ЬЛ›Э]]ШЫЫ™љYКB€љ[ќ
\™ЬЛ›Э]]ШЫЫ™љYЛњ™\ЫЫ™J
JB€™]\›€‚‚љY€ЧЫ[YWЧИOH—ЧЫXZ[—ЧИЋ‚€Z\ЩHЮ\Э[Q^]
XZ[Љ
JBѓB
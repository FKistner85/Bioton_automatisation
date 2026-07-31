#!/usr/bin/env python3
"""
Step 3_0_a: Inventory and validate Dawn Chorus audio files.

The script scans the original SoundRecordings directory recursively for files
containing the "_audio" filename tag.

Files are validated directly at their original location. No files are copied
or modified.

Checks include:
- filename pattern and Dawn Chorus ID
- file size
- readable audio stream
- full audio decoding
- duration within the configured tolerance
- codec, format, sample rate and channel metadata

Outputs:
- detailed file-level inventory CSV
- compact issue status per Dawn Chorus ID
- JSON state summary
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import av

from common import print_path_report, resolve_existing_path, resolve_output_path


TAG_RE = re.compile(
    r"^(?P<id>\d+)_audio(?:$|[._-])",
    re.IGNORECASE,
)

DEFAULT_SOURCE = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/SoundRecordings"
)

DEFAULT_PROCESSED = Path(
    "/lsdf/kit/ipf/projects/Bio-O-Ton/"
    "Data_automatisation_skripts/outputs"
)

DETAIL_COLUMNS = [
    "dawn_chorus_id",
    "source_relative_path",
    "source_path",
    "filename",
    "extension",
    "size_bytes",
    "mtime_ns",
    "probe_ok",
    "decode_ok",
    "duration_seconds",
    "duration_target_seconds",
    "duration_tolerance_seconds",
    "duration_ok",
    "codec_name",
    "format_name",
    "sample_rate_hz",
    "channels",
    "decoded_frames",
    "decoded_samples",
    "has_issues",
    "issues",
]


def load_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the complete JSON config and the audio_inventory section."""
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    section = config.get("audio_inventory", {})

    if not isinstance(section, dict):
        raise TypeError("'audio_inventory' must be a JSON object.")

    return config, section


def discover(source_dir: Path) -> list[Path]:
    """Find all files containing the '_audio' tag recursively."""
    if not source_dir.is_dir():
        raise NotADirectoryError(
            f"Audio source directory not found: {source_dir}"
        )

    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file()
        and "_audio" in path.stem.lower()
    )


def inspect_audio(path: Path) -> dict[str, Any]:
    """Open and fully decode one audio file with PyAV."""
    issues: list[str] = []

    probe_ok = False
    decode_ok = False
    duration: float | None = None

    codec_name = ""
    format_name = ""
    sample_rate: int | str = ""
    channels: int | str = ""

    decoded_frames = 0
    decoded_samples = 0

    try:
        with av.open(str(path), mode="r") as container:
            audio_streams = [
                stream
                for stream in container.streams
                if stream.type == "audio"
            ]

            if not audio_streams:
                issues.append("no_audio_stream_found")

                return {
                    "probe_ok": False,
                    "decode_ok": False,
                    "duration": None,
                    "codec_name": "",
                    "format_name": str(
                        getattr(container.format, "name", "") or ""
                    ),
                    "sample_rate": "",
                    "channels": "",
                    "decoded_frames": 0,
                    "decoded_samples": 0,
                    "issues": issues,
                }

            stream = audio_streams[0]

            if len(audio_streams) > 1:
                issues.append(
                    f"multiple_audio_streams:{len(audio_streams)}"
                )

            codec_name = str(
                getattr(stream.codec_context, "name", "") or ""
            )

            format_name = str(
                getattr(container.format, "name", "") or ""
            )

            sample_rate_value = getattr(
                stream.codec_context,
                "sample_rate",
                None,
            )

            channels_value = getattr(
                stream.codec_context,
                "channels",
                None,
            )

            sample_rate = (
                ""
                if sample_rate_value is None
                else int(sample_rate_value)
            )

            channels = (
                ""
                if channels_value is None
                else int(channels_value)
            )

            if sample_rate_value is None or sample_rate_value <= 0:
                issues.append("invalid_or_missing_sample_rate")

            if channels_value is None or channels_value <= 0:
                issues.append("invalid_or_missing_channel_count")

            if (
                stream.duration is not None
                and stream.time_base is not None
            ):
                duration = float(
                    stream.duration * stream.time_base
                )

            elif container.duration is not None:
                duration = float(
                    container.duration / av.time_base
                )

            probe_ok = True

            # Decode the complete stream to detect errors beyond the header.
            for frame in container.decode(stream):
                decoded_frames += 1
                decoded_samples += int(
                    getattr(frame, "samples", 0) or 0
                )

            if decoded_frames == 0:
                issues.append("no_audio_frames_decoded")
            else:
                decode_ok = True

            if (
                duration is None
                and decoded_samples > 0
                and sample_rate_value is not None
                and sample_rate_value > 0
            ):
                duration = (
                    decoded_samples / float(sample_rate_value)
                )

            if duration is None:
                issues.append("duration_unavailable")

            elif duration <= 0:
                issues.append(
                    f"invalid_duration:{duration:.6f}"
                )

    except Exception as exc:
        issues.append(
            "pyav_decode_failed:"
            f"{type(exc).__name__}:"
            f"{exc}"
        )

    return {
        "probe_ok": probe_ok,
        "decode_ok": decode_ok,
        "duration": duration,
        "codec_name": codec_name,
        "format_name": format_name,
        "sample_rate": sample_rate,
        "channels": channels,
        "decoded_frames": decoded_frames,
        "decoded_samples": decoded_samples,
        "issues": issues,
    }


def validate_original_file(
    task: tuple[Path, Path, float, float],
) -> dict[str, Any]:
    """Validate one file directly at its original source path."""
    source, source_root, target, tolerance = task

    relative = source.relative_to(source_root)
    issues: list[str] = []

    match = TAG_RE.match(source.stem)
    dawn_id = match.group("id") if match else ""

    if not match:
        issues.append(
            "filename_does_not_match_<id>_audio_pattern"
        )

    try:
        stat = source.stat()

    except OSError as exc:
        issues.append(
            f"source_stat_failed:{type(exc).__name__}:{exc}"
        )

        return {
            "dawn_chorus_id": dawn_id,
            "source_relative_path": relative.as_posix(),
            "source_path": str(source),
            "filename": source.name,
            "extension": source.suffix.lower(),
            "size_bytes": "",
            "mtime_ns": "",
            "probe_ok": False,
            "decode_ok": False,
            "duration_seconds": "",
            "duration_target_seconds": target,
            "duration_tolerance_seconds": tolerance,
            "duration_ok": False,
            "codec_name": "",
            "format_name": "",
            "sample_rate_hz": "",
            "channels": "",
            "decoded_frames": 0,
            "decoded_samples": 0,
            "has_issues": True,
            "issues": " | ".join(issues),
        }

    if stat.st_size == 0:
        issues.append("empty_file")

    inspection = inspect_audio(source)

    probe_ok = bool(inspection["probe_ok"])
    decode_ok = bool(inspection["decode_ok"])
    duration = inspection["duration"]

    issues.extend(inspection["issues"])

    duration_ok = (
        duration is not None
        and duration > 0
        and abs(duration - target) <= tolerance
    )

    if duration is not None and duration > 0 and not duration_ok:
        issues.append(
            f"duration_not_{target:g}s:"
            f"observed={duration:.6f}s,"
            f"allowed={target - tolerance:g}-"
            f"{target + tolerance:g}s"
        )

    return {
        "dawn_chorus_id": dawn_id,
        "source_relative_path": relative.as_posix(),
        "source_path": str(source),
        "filename": source.name,
        "extension": source.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "probe_ok": probe_ok,
        "decode_ok": decode_ok,
        "duration_seconds": (
            ""
            if duration is None
            else f"{duration:.6f}"
        ),
        "duration_target_seconds": target,
        "duration_tolerance_seconds": tolerance,
        "duration_ok": duration_ok,
        "codec_name": str(inspection["codec_name"]),
        "format_name": str(inspection["format_name"]),
        "sample_rate_hz": inspection["sample_rate"],
        "channels": inspection["channels"],
        "decoded_frames": int(
            inspection["decoded_frames"]
        ),
        "decoded_samples": int(
            inspection["decoded_samples"]
        ),
        "has_issues": bool(issues),
        "issues": " | ".join(issues),
    }


def read_existing(
    path: Path,
) -> dict[str, dict[str, str]]:
    """Read an existing detailed inventory for incremental processing."""
    if not path.is_file():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return {
            row["source_relative_path"]: row
            for row in csv.DictReader(handle)
            if row.get("source_relative_path")
        }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> None:
    """Write a CSV atomically through a temporary file."""
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inventory and validate original Dawn Chorus "
            "audio files without copying them."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "config.json"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Revalidate all files, including unchanged files.",
    )

    return parser.parse_args()


def main() -> int:
    """Run the incremental audio inventory and validation workflow."""
    args = parse_args()

    try:
        config, settings = load_config(args.config)

        processed_root = resolve_output_path(
            settings.get(
                "processed_dir",
                DEFAULT_PROCESSED,
            )
        )

        source_report = resolve_existing_path(
            settings.get(
                "source_dir",
                DEFAULT_SOURCE,
            ),
            label="audio",
            expected="dir",
        )
        print_path_report(source_report)
        source_dir = source_report.resolved

        detailed_csv = resolve_output_path(
            settings.get(
                "detailed_log",
                processed_root
                / "audio_inventory_detailed.csv",
            )
        )

        compact_csv = resolve_output_path(
            settings.get(
                "compact_log",
                processed_root
                / "audio_inventory_compact.csv",
            )
        )

        status_dir = resolve_output_path(
            config.get(
                "status_dir",
                processed_root / "_status",
            )
        )

        state_file = resolve_output_path(
            settings.get(
                "state_file",
                status_dir
                / "step_3_0_a_audio_inventory_state.json",
            )
        )

        target = float(
            settings.get(
                "target_duration_seconds",
                60.0,
            )
        )

        tolerance = float(
            settings.get(
                "duration_tolerance_seconds",
                1.0,
            )
        )

        allocated = int(
            os.environ.get(
                "SLURM_CPUS_PER_TASK",
                "1",
            )
        )

        configured_workers = int(
            settings.get(
                "workers",
                allocated,
            )
        )

        workers = max(
            1,
            min(configured_workers, allocated),
        )

        if target <= 0:
            raise ValueError(
                "target_duration_seconds must be greater than zero."
            )

        if tolerance < 0:
            raise ValueError(
                "duration_tolerance_seconds must not be negative."
            )

        files = discover(source_dir)
        existing = read_existing(detailed_csv)

        current_relative_paths = {
            path.relative_to(source_dir).as_posix()
            for path in files
        }

        # Drop manifest rows for source files that no longer exist.
        retained = {
            key: value
            for key, value in existing.items()
            if key in current_relative_paths
        }

        tasks: list[
            tuple[Path, Path, float, float]
        ] = []

        unchanged_count = 0

        for path in files:
            relative_path = (
                path.relative_to(source_dir).as_posix()
            )

            try:
                stat = path.stat()

            except OSError:
                tasks.append(
                    (
                        path,
                        source_dir,
                        target,
                        tolerance,
                    )
                )
                continue

            old = existing.get(relative_path)

            # Reuse results when file size and modification time are unchanged.
            unchanged = (
                not args.force
                and old is not None
                and old.get("size_bytes")
                == str(stat.st_size)
                and old.get("mtime_ns")
                == str(stat.st_mtime_ns)
            )

            if unchanged:
                unchanged_count += 1

            else:
                tasks.append(
                    (
                        path,
                        source_dir,
                        target,
                        tolerance,
                    )
                )

        print(
            f"Audio-tagged source files      : {len(files):,}"
        )
        print(
            f"Unchanged manifest rows        : {unchanged_count:,}"
        )
        print(
            f"New/changed files to validate  : {len(tasks):,}"
        )
        print(
            f"Worker threads                 : {workers}"
        )
        print(
            f"Original source directory      : {source_dir}"
        )

        if tasks:
            with ThreadPoolExecutor(
                max_workers=workers
            ) as pool:

                futures = [
                    pool.submit(
                        validate_original_file,
                        task,
                    )
                    for task in tasks
                ]

                for index, future in enumerate(
                    as_completed(futures),
                    start=1,
                ):
                    row = future.result()

                    relative_path = str(
                        row["source_relative_path"]
                    )

                    retained[relative_path] = {
                        key: str(value)
                        for key, value in row.items()
                    }

                    if (
                        index % 100 == 0
                        or index == len(futures)
                    ):
                        print(
                            f"Validated {index:,}/{len(futures):,}"
                        )

        rows = [
            retained[key]
            for key in sorted(retained)
        ]

        write_csv(
            detailed_csv,
            rows,
            DETAIL_COLUMNS,
        )

        # Aggregate file-level issue flags by Dawn Chorus ID.
        compact_by_id: dict[str, bool] = {}

        for row in rows:
            dawn_id = str(
                row.get("dawn_chorus_id", "")
            ).strip()

            if not dawn_id:
                continue

            row_has_issues = (
                str(
                    row.get("has_issues", "")
                ).lower()
                == "true"
            )

            compact_by_id[dawn_id] = (
                compact_by_id.get(dawn_id, False)
                or row_has_issues
            )

        compact_rows = [
            {
                "dawn_chorus_id": dawn_id,
                "has_issues": has_issues,
            }
            for dawn_id, has_issues in sorted(
                compact_by_id.items(),
                key=lambda item: int(item[0]),
            )
        ]

        write_csv(
            compact_csv,
            compact_rows,
            [
                "dawn_chorus_id",
                "has_issues",
            ],
        )

        issue_count = sum(
            str(
                row.get("has_issues", "")
            ).lower()
            == "true"
            for row in rows
        )

        probe_failure_count = sum(
            str(
                row.get("probe_ok", "")
            ).lower()
            != "true"
            for row in rows
        )

        decode_failure_count = sum(
            str(
                row.get("decode_ok", "")
            ).lower()
            != "true"
            for row in rows
        )

        duration_failure_count = sum(
            str(
                row.get("duration_ok", "")
            ).lower()
            != "true"
            for row in rows
        )

        state_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        state_data = {
            "source_dir": str(source_dir),
            "detailed_log": str(detailed_csv),
            "compact_log": str(compact_csv),
            "source_files": len(files),
            "manifest_rows": len(rows),
            "unchanged_files_reused": unchanged_count,
            "files_validated_this_run": len(tasks),
            "files_with_issues": issue_count,
            "probe_failures": probe_failure_count,
            "decode_failures": decode_failure_count,
            "duration_failures": duration_failure_count,
            "target_duration_seconds": target,
            "duration_tolerance_seconds": tolerance,
            "workers": workers,
            "force_run": bool(args.force),
            "copying_enabled": False,
        }

        temporary_state = state_file.with_suffix(
            state_file.suffix + ".tmp"
        )

        with temporary_state.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                state_data,
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.write("\n")

        temporary_state.replace(state_file)

        print()
        print("Step 3_0_a completed.")
        print(
            f"Manifest rows               : {len(rows):,}"
        )
        print(
            f"Files checked this run      : {len(tasks):,}"
        )
        print(
            f"Unchanged files reused      : {unchanged_count:,}"
        )
        print(
            f"Files with issues           : {issue_count:,}"
        )
        print(
            f"Probe failures              : {probe_failure_count:,}"
        )
        print(
            f"Decode failures             : {decode_failure_count:,}"
        )
        print(
            f"Duration failures           : {duration_failure_count:,}"
        )
        print(
            f"Original audio directory    : {source_dir}"
        )
        print(
            f"Detailed log                : {detailed_csv}"
        )
        print(
            f"Compact log                 : {compact_csv}"
        )
        print(
            f"State file                  : {state_file}"
        )
        print("Audio files copied          : 0")

        return 0

    except Exception as exc:
        print(
            f"ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

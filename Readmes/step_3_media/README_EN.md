# Step 3 Media Inventory And Download (EN)

## Purpose
Validates and fills audio and photo files.

## Script
`scripts/Step_3_0_a_audio_inventory.py, Step_3_0_b_photo_inventory.py, Step_3_1_a_audio_download.py, Step_3_1_b_photo_download.py`

## Inputs
- `PointData/SoundRecordings`
- `PointData/Images_SoundRecordings`
- `PointData/dawn-chorus-soundscape.csv`

## Outputs
- `outputs/step_3_0_*/*`
- `outputs/step_3_1_*/*`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_3_0_audio_inventory`, `step_3_0_photo_inventory`, `step_3_1_audio_download`, `step_3_1_photo_download`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `audio_inventory`, `photo_inventory`, `audio_download`, `photo_download`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_3_0_a_audio_inventory.py --config config.horeka.json`
- `python scripts/Step_3_0_b_photo_inventory.py --config config.horeka.json`
- `python scripts/Step_3_1_a_audio_download.py --config config.horeka.json`
- `python scripts/Step_3_1_b_photo_download.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
Inventories and persistent retry logs prevent duplicate downloads.

## Quality Control
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical run statuses are defined in `scripts/common.py`; `schemas/status_model.json` defines status-event fields.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `WinError 53` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 64` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 121` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 995` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 1203` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `no_audio_stream_found` | No audio stream found in the file. | [Step_3_0_a_audio_inventory.py:216](../../scripts/Step_3_0_a_audio_inventory.py) |
| `multiple_audio_streams:{len(audio_streams)}` | File contains multiple audio streams. | [Step_3_0_a_audio_inventory.py:236](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_or_missing_sample_rate` | Sample rate is missing or nonpositive. | [Step_3_0_a_audio_inventory.py:273](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_or_missing_channel_count` | Audio channel count is missing or nonpositive. | [Step_3_0_a_audio_inventory.py:276](../../scripts/Step_3_0_a_audio_inventory.py) |
| `no_audio_frames_decoded` | Decoder returned no audio frames. | [Step_3_0_a_audio_inventory.py:301](../../scripts/Step_3_0_a_audio_inventory.py) |
| `duration_unavailable` | Audio duration could not be determined. | [Step_3_0_a_audio_inventory.py:316](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_duration:{duration}` | Determined audio duration is not positive. | [Step_3_0_a_audio_inventory.py:319](../../scripts/Step_3_0_a_audio_inventory.py) |
| `pyav_decode_failed:{type(exc).__name__}:{exc}` | PyAV could not decode the audio successfully. | [Step_3_0_a_audio_inventory.py:325](../../scripts/Step_3_0_a_audio_inventory.py) |
| `filename_does_not_match_<id>_audio_pattern` | Audio filename does not match the expected ID pattern. | [Step_3_0_a_audio_inventory.py:359](../../scripts/Step_3_0_a_audio_inventory.py) |
| `source_stat_failed:{type(exc).__name__}:{exc}` | Filesystem stat failed for the source file. | [Step_3_0_a_audio_inventory.py:367](../../scripts/Step_3_0_a_audio_inventory.py) |
| `empty_file` | Existing file has zero bytes. | [Step_3_0_a_audio_inventory.py:397](../../scripts/Step_3_0_a_audio_inventory.py) |
| `duration_not_{target}s:observed={duration}s,allowed={target - tolerance}-{target + tolerance}s` | Audio duration is outside target plus/minus tolerance; values are included. | [Step_3_0_a_audio_inventory.py:414](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 53` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 64` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 121` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 995` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 1203` | Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `filename_does_not_match_<id>_photo_pattern` | Photo filename does not match the expected ID pattern. | [Step_3_0_b_photo_inventory.py:139](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_failed:{type(exc).__name__}:{exc}` | File copy failed. | [Step_3_0_b_photo_inventory.py:158](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_size_mismatch` | Source and copied file sizes differ. | [Step_3_0_b_photo_inventory.py:165](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_verification_failed:{type(exc).__name__}:{exc}` | Verification after copying failed. | [Step_3_0_b_photo_inventory.py:167](../../scripts/Step_3_0_b_photo_inventory.py) |
| `destination_missing_after_copy` | Destination is missing after the copy attempt. | [Step_3_0_b_photo_inventory.py:169](../../scripts/Step_3_0_b_photo_inventory.py) |
| `image_verify_failed:{type(exc).__name__}:{exc}` | Pillow image verification failed. | [Step_3_0_b_photo_inventory.py:189](../../scripts/Step_3_0_b_photo_inventory.py) |
| `pixel_load_failed:{type(exc).__name__}:{exc}` | Image pixels could not be loaded after header inspection. | [Step_3_0_b_photo_inventory.py:197](../../scripts/Step_3_0_b_photo_inventory.py) |
| `invalid_dimensions:{width}x{height}` | Raster/image width or height is invalid. | [Step_3_0_b_photo_inventory.py:200](../../scripts/Step_3_0_b_photo_inventory.py) |
| `no_audio_stream_found` | No audio stream found in the file. | [Step_3_1_a_audio_download.py:170](../../scripts/Step_3_1_a_audio_download.py) |
| `multiple_audio_streams:{len(streams)}` | File contains multiple audio streams. | [Step_3_1_a_audio_download.py:187](../../scripts/Step_3_1_a_audio_download.py) |
| `duration_unavailable` | Audio duration could not be determined. | [Step_3_1_a_audio_download.py:230](../../scripts/Step_3_1_a_audio_download.py) |
| `no_audio_frames_decoded` | Decoder returned no audio frames. | [Step_3_1_a_audio_download.py:243](../../scripts/Step_3_1_a_audio_download.py) |
| `pyav_decode_failed:{type(exc).__name__}:{exc}` | PyAV could not decode the audio successfully. | [Step_3_1_a_audio_download.py:257](../../scripts/Step_3_1_a_audio_download.py) |
| `HTTPError:{exc.code}:{exc.reason}` | HTTP download failed; suffix contains status and server message. Follow retry policy. | [Step_3_1_a_audio_download.py:328](../../scripts/Step_3_1_a_audio_download.py) |
| `{type(exc).__name__}:{exc}` | Original exception type and message; not a separate fixed code. | [Step_3_1_a_audio_download.py:335](../../scripts/Step_3_1_a_audio_download.py) |
| `duration_not_{target}s:observed={duration}s,allowed={target - tolerance}-{target + tolerance}s` | Audio duration is outside target plus/minus tolerance; values are included. | [Step_3_1_a_audio_download.py:354](../../scripts/Step_3_1_a_audio_download.py) |
| `missing_audio_url` | Audio download URL is missing. | [Step_3_1_a_audio_download.py:444](../../scripts/Step_3_1_a_audio_download.py) |
| `HTTPError:{exc.code}:{exc.reason}` | HTTP download failed; suffix contains status and server message. Follow retry policy. | [Step_3_1_b_photo_download.py:127](../../scripts/Step_3_1_b_photo_download.py) |
| `{type(exc).__name__}:{exc}` | Original exception type and message; not a separate fixed code. | [Step_3_1_b_photo_download.py:130](../../scripts/Step_3_1_b_photo_download.py) |
| `image_verify_failed:{type(exc).__name__}:{exc}` | Pillow image verification failed. | [Step_3_1_b_photo_download.py:149](../../scripts/Step_3_1_b_photo_download.py) |
| `pixel_load_failed:{type(exc).__name__}:{exc}` | Image pixels could not be loaded after header inspection. | [Step_3_1_b_photo_download.py:157](../../scripts/Step_3_1_b_photo_download.py) |
| `missing_photo_url` | Photo download URL is missing. | [Step_3_1_b_photo_download.py:203](../../scripts/Step_3_1_b_photo_download.py) |

### Status Values (Not All Are Errors)

No fixed values in this category in the associated source.

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_3_0_a_audio_inventory.py:115](../../scripts/Step_3_0_a_audio_inventory.py) |
| `TypeError: 'audio_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_3_0_a_audio_inventory.py:123](../../scripts/Step_3_0_a_audio_inventory.py) |
| `NotADirectoryError: Audio source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_3_0_a_audio_inventory.py:131](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ConnectionError: LSDF transport failed while listing {path}: {exc}` | `is_transport_error(exc)` | [Step_3_0_a_audio_inventory.py:150](../../scripts/Step_3_0_a_audio_inventory.py) |
| `FileNotFoundError: Dawn Chorus metadata CSV not found: {metadata_csv}` | `not metadata_csv.is_file()` | [Step_3_0_a_audio_inventory.py:170](../../scripts/Step_3_0_a_audio_inventory.py) |
| `KeyError: Missing metadata columns in {metadata_csv}: {sorted(missing)}` | `missing` | [Step_3_0_a_audio_inventory.py:177](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ValueError: target_duration_seconds must be greater than zero.` | `target <= 0` | [Step_3_0_a_audio_inventory.py:634](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ValueError: duration_tolerance_seconds must not be negative.` | `tolerance < 0` | [Step_3_0_a_audio_inventory.py:639](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ConnectionError: Audio inventory stopped because the LSDF transport failed ({len(transport_rows)} files in the current validation block). Sample: {sample}` | `transport_rows` | [Step_3_0_a_audio_inventory.py:786](../../scripts/Step_3_0_a_audio_inventory.py) |
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_3_0_b_photo_inventory.py:58](../../scripts/Step_3_0_b_photo_inventory.py) |
| `TypeError: 'photo_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_3_0_b_photo_inventory.py:63](../../scripts/Step_3_0_b_photo_inventory.py) |
| `NotADirectoryError: Photo source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_3_0_b_photo_inventory.py:69](../../scripts/Step_3_0_b_photo_inventory.py) |
| `FileNotFoundError: Dawn Chorus metadata CSV not found: {metadata_csv}` | `not metadata_csv.is_file()` | [Step_3_0_b_photo_inventory.py:96](../../scripts/Step_3_0_b_photo_inventory.py) |
| `KeyError: Missing metadata columns in {metadata_csv}: {sorted(missing)}` | `missing` | [Step_3_0_b_photo_inventory.py:103](../../scripts/Step_3_0_b_photo_inventory.py) |
| `NotADirectoryError: Photo {label} directory not found: {raw}` | `not create_if_missing` | [Step_3_0_b_photo_inventory.py:122](../../scripts/Step_3_0_b_photo_inventory.py) |
| `ConnectionError: Photo inventory stopped because the LSDF transport failed. Affected rows: {len(transport_rows)}; sample: {transport_rows[0].get('issues', '')}` | `transport_rows` | [Step_3_0_b_photo_inventory.py:375](../../scripts/Step_3_0_b_photo_inventory.py) |
| `TypeError: 'audio_download' must be an object.` | `not isinstance(section, dict)` | [Step_3_1_a_audio_download.py:97](../../scripts/Step_3_1_a_audio_download.py) |
| `OSError: Downloaded file is empty.` | `temporary.stat().st_size == 0` | [Step_3_1_a_audio_download.py:321](../../scripts/Step_3_1_a_audio_download.py) |
| `OSError: Downloaded file is empty.` | `temporary.stat().st_size == 0` | [Step_3_1_b_photo_download.py:122](../../scripts/Step_3_1_b_photo_download.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `args.list_only` | [Step_3_0_a_audio_inventory.py:684](../../scripts/Step_3_0_a_audio_inventory.py) |
| `0` | `Emitted by main` | [Step_3_0_a_audio_inventory.py:966](../../scripts/Step_3_0_a_audio_inventory.py) |
| `1` | `except Exception` | [Step_3_0_a_audio_inventory.py:973](../../scripts/Step_3_0_a_audio_inventory.py) |
| `0` | `args.list_only` | [Step_3_0_b_photo_inventory.py:331](../../scripts/Step_3_0_b_photo_inventory.py) |
| `0` | `Emitted by main` | [Step_3_0_b_photo_inventory.py:423](../../scripts/Step_3_0_b_photo_inventory.py) |
| `1` | `except Exception` | [Step_3_0_b_photo_inventory.py:426](../../scripts/Step_3_0_b_photo_inventory.py) |
| `0` | `Emitted by main` | [Step_3_1_a_audio_download.py:901](../../scripts/Step_3_1_a_audio_download.py) |
| `1` | `except Exception` | [Step_3_1_a_audio_download.py:908](../../scripts/Step_3_1_a_audio_download.py) |
| `0` | `Emitted by main` | [Step_3_1_b_photo_download.py:430](../../scripts/Step_3_1_b_photo_download.py) |
| `1` | `except Exception` | [Step_3_1_b_photo_download.py:433](../../scripts/Step_3_1_b_photo_download.py) |
| `1` | `failures or not image_source_usable or (not image_output_usable)` | [step3_path_preflight.py:153](../../tools/step3_path_preflight.py) |
| `0` | `Emitted by main` | [step3_path_preflight.py:156](../../tools/step3_path_preflight.py) |
| `1` | `except Exception` | [step3_path_preflight.py:159](../../tools/step3_path_preflight.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

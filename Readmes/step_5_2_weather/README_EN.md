# Step 5_2 HOSTRADA Weather Per Recording (EN)

## Purpose
Downloads/caches HOSTRADA data and extracts weather time series per recording.

## Script
`scripts/Step_5_2_download_weather_data.py`

## Inputs
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `DWD HOSTRADA`

## Outputs
- `PointData/Weather/Hostrada/weather_<id>.csv`
- `outputs/step_5_2_weather_download/*`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_5_1_weather_inventory`, `step_5_2_weather_download`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `weather_inventory`, `weather_download`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_5_2_download_weather_data.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits parallelism inside one job. The orchestrator
deterministically distributes large ID sets across up to eight `bio_step52`
array tasks, with at most four tasks running concurrently by default. Small
incremental sets remain a single task. Shared monthly NetCDF files use an
LSDF-safe download lock. `bio_step52verify` subsequently checks that every
requested ID still present in metadata has a non-empty weather CSV.

## Checkpoint/Resume
Non-empty `weather_<id>.csv` files and `_recording_status` are reused. When an
`--ids-file` is supplied it is authoritative, preventing unrelated historical
problems from re-entering the worklist. Progress and ETA are written per shard
to `progress_shard_<n>.json`.

## Quality Control

The weather window includes `preceding_days` complete local calendar days before
the recording plus the complete recording day in `input_timezone`. Ten preceding
days normally give 264 hourly observations, or 263/265 across daylight-saving
transitions. Download and inventory share the same calendar boundaries.
The CSV retains local times without offsets. Inventory therefore expects the
missing spring hour and repeated autumn hour, while still rejecting extra
duplicates and missing observations. `weather_inventory.expected_rows` is only
a fallback without a recording timestamp; otherwise the actual window sets the
expected row count.

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
| `filename_does_not_match_weather_id_pattern` | Weather filename does not match the expected ID pattern. | [Step_5_1_Weather_inventory.py:205](../../scripts/Step_5_1_Weather_inventory.py) |
| `invalid_metadata_datetime` | Metadata recording time is invalid for the weather window. | [Step_5_1_Weather_inventory.py:216](../../scripts/Step_5_1_Weather_inventory.py) |
| `empty_file` | Existing file has zero bytes. | [Step_5_1_Weather_inventory.py:245](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_row_count` | Row count does not match the expected weather window. | [Step_5_1_Weather_inventory.py:270](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_required_column` | At least one configured required column is missing. | [Step_5_1_Weather_inventory.py:277](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_value` | Values are missing; the specific check or NaN tolerance determines failure. | [Step_5_1_Weather_inventory.py:286](../../scripts/Step_5_1_Weather_inventory.py) |
| `unparseable_datetime` | Timestamps in the data file cannot be parsed. | [Step_5_1_Weather_inventory.py:294](../../scripts/Step_5_1_Weather_inventory.py) |
| `duplicate_datetime` | More duplicate timestamps than allowed by the local DST window. | [Step_5_1_Weather_inventory.py:302](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_time_interval` | Timestamps and their multiplicities do not match the complete expected local weather window. Correct DST transitions are allowed; this code alone does not distinguish missing, extra or shifted hours. | [Step_5_1_Weather_inventory.py:316](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_time_window` | Timestamps do not cover the calculated local weather window. | [Step_5_1_Weather_inventory.py:330](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_datetime_column` | Weather CSV has no datetime column. | [Step_5_1_Weather_inventory.py:334](../../scripts/Step_5_1_Weather_inventory.py) |
| `implausible_value` | At least one value violates configured plausibility limits. | [Step_5_1_Weather_inventory.py:338](../../scripts/Step_5_1_Weather_inventory.py) |
| `read_error:{type(exc).__name__}` | Data file could not be read; suffix identifies exception type. | [Step_5_1_Weather_inventory.py:341](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_file` | Expected file is missing. | [Step_5_1_Weather_inventory.py:373](../../scripts/Step_5_1_Weather_inventory.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `out_of_bounds` | `bounds_checked and (not bounds_ok)` | [Step_5_2_download_weather_data.py:422](../../scripts/Step_5_2_download_weather_data.py) |
| `upstream_unavailable` | `unavailable_source_months` | [Step_5_2_download_weather_data.py:481](../../scripts/Step_5_2_download_weather_data.py) |
| `ok` | `Emitted by process_recording` | [Step_5_2_download_weather_data.py:482](../../scripts/Step_5_2_download_weather_data.py) |
| `failed` | `except Exception` | [Step_5_2_download_weather_data.py:485](../../scripts/Step_5_2_download_weather_data.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_5_1_Weather_inventory.py:76](../../scripts/Step_5_1_Weather_inventory.py) |
| `KeyError: Missing 'weather_inventory' section in config.` | `not isinstance(config.get('weather_inventory'), dict)` | [Step_5_1_Weather_inventory.py:80](../../scripts/Step_5_1_Weather_inventory.py) |
| `ValueError: Metadata ID column '{id_column}' not found in {metadata_csv}.` | `id_column not in metadata.columns` | [Step_5_1_Weather_inventory.py:133](../../scripts/Step_5_1_Weather_inventory.py) |
| `NotADirectoryError: Weather directory not found: {directory}` | `not directory.is_dir()` | [Step_5_1_Weather_inventory.py:512](../../scripts/Step_5_1_Weather_inventory.py) |
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_5_2_download_weather_data.py:98](../../scripts/Step_5_2_download_weather_data.py) |
| `KeyError: Missing 'weather_download' section in config.json.` | `not isinstance(section, dict)` | [Step_5_2_download_weather_data.py:104](../../scripts/Step_5_2_download_weather_data.py) |
| `RuntimeError: Step 5_2 worker was not initialised.` | `_worker_transformer is None or _worker_preceding_days is None or _worker_input_timezone is None or (_worker_cache_dir is None) or (_worker_download_settings is None)` | [Step_5_2_download_weather_data.py:532](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: Input CSV missing required column(s): {missing}.` | `missing` | [Step_5_2_download_weather_data.py:579](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: --task-count must be at least 1.` | `args.task_count < 1` | [Step_5_2_download_weather_data.py:812](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: --task-index must satisfy 0 <= index < task-count.` | `args.task_index < 0 or args.task_index >= args.task_count` | [Step_5_2_download_weather_data.py:814](../../scripts/Step_5_2_download_weather_data.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `args.list_only` | [Step_5_1_Weather_inventory.py:570](../../scripts/Step_5_1_Weather_inventory.py) |
| `0` | `Emitted by main` | [Step_5_1_Weather_inventory.py:674](../../scripts/Step_5_1_Weather_inventory.py) |
| `1` | `except Exception` | [Step_5_1_Weather_inventory.py:677](../../scripts/Step_5_1_Weather_inventory.py) |
| `1` | `missing` | [Step_5_2_download_weather_data.py:847](../../scripts/Step_5_2_download_weather_data.py) |
| `2` | `unavailable` | [Step_5_2_download_weather_data.py:854](../../scripts/Step_5_2_download_weather_data.py) |
| `0` | `args.verify_shards` | [Step_5_2_download_weather_data.py:855](../../scripts/Step_5_2_download_weather_data.py) |
| `1 if processed_failed or (bool(section.get('fail_on_upstream_unavailable', False)) and processed_upstream_unavailable) else 0` | `Emitted by main` | [Step_5_2_download_weather_data.py:1269](../../scripts/Step_5_2_download_weather_data.py) |
| `1` | `except Exception` | [Step_5_2_download_weather_data.py:1288](../../scripts/Step_5_2_download_weather_data.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

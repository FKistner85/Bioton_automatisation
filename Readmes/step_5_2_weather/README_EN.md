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
Authoritative dependencies, scope and invalidation rules are defined in `pipeline_steps.json` under `step_5_1_weather_inventory`, `step_5_2_weather_download`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `weather_inventory`, `weather_download`. Paths, worker counts and domain thresholds are not duplicated in Slurm scripts.

## Execution
`bash slurm_add_new_ids.sh` starts the regular incremental DAG; `bash slurm_from_scratch.sh` starts or resumes a full generation. An isolated technical direct run is available with:
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
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical statuses are defined in `schemas/status_model.json`.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

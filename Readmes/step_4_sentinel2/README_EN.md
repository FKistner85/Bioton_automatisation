# Step 4 Sentinel-2 Mirror And Inventory (EN)

## Purpose
Mirrors external Sentinel-2 Drive files and inventories GeoTIFFs.

## Script
`scripts/Step_4_1_Sentinel2_download.py, scripts/Step_4_0_Sentinel2_inventory.py`

## Inputs
- `Google Drive token.json`
- `PointData/S2`
- `PointData/S2_Scores.csv`

The score-table identifier is configured through
`sentinel2_inventory.score_id_column`. The inventory also recognises the
case-insensitive aliases `id`, `DC_id`, `dawn_chorus_id`, and `recording_id`.

## Outputs
- `PointData/S2/*.tif`
- `outputs/step_4_0_Sentinel2_inventory/*`
- `outputs/step_4_1_sentinel2_download/*`

## Dependencies And Invalidation
Authoritative dependencies, scope and invalidation rules are defined in `pipeline_steps.json` under `step_4_1_sentinel2_mirror`, `step_4_0_sentinel2_inventory`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `sentinel2_download`, `sentinel2_inventory`. Paths, worker counts and domain thresholds are not duplicated in Slurm scripts.

## Execution
`bash slurm_add_new_ids.sh` starts the regular incremental DAG; `bash slurm_from_scratch.sh` starts or resumes a full generation. An isolated technical direct run is available with:
- `python scripts/Step_4_1_Sentinel2_download.py --config config.horeka.json`
- `python scripts/Step_4_0_Sentinel2_inventory.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
The Drive log, file size and modification time control incremental processing.

## Quality Control
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical statuses are defined in `schemas/status_model.json`.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

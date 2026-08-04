# Step 2_1 100m Formation Status (EN)

## Purpose
Overlays LRTs with the 100m grid and creates majority and formation-status products.

## Script
`scripts/Step_2_1_merge_lrts_and_grid.py`

## Inputs
- `InspireGrid/Vector_Data/grid.gpkg`
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_1/*`
- `outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/*`

The Susi-compatible matrix stores all formation and LRT shares as integer
percentages with a factor of 100 (`10000 = 100 percent`). Formation totals
include A/B/C/K. Majority status is selected from A/B/C only;
`majority_disputed` means `majority_delta <= 200`, i.e. no more than two
percentage points apart.

## Dependencies And Invalidation
Authoritative dependencies, scope and invalidation rules are defined in `pipeline_steps.json` under `step_2_1_100m_formation`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `lrt_grid_merge`. Paths, worker counts and domain thresholds are not duplicated in Slurm scripts.

## Execution
`bash slurm_add_new_ids.sh` starts the regular incremental DAG; `bash slurm_from_scratch.sh` starts or resumes a full generation. An isolated technical direct run is available with:
- `python scripts/Step_2_1_merge_lrts_and_grid.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
Chunk-Checkpoints und State-Datei ermoeglichen Wiederaufnahme.

## Quality Control
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical statuses are defined in `schemas/status_model.json`.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

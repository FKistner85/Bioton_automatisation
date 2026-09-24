# Step 2_3 Grid Aggregation (EN)

## Purpose
Aggregates 100m grid products to coarser grid resolutions.

## Script
`scripts/Step_2_3_generate_remaining_grid_products.py`

## Inputs
- `outputs/step_2_variants/<suffix>/step_2_1/majority_formation_grid_<suffix>.parquet`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_3/*.csv`
- `outputs/step_2_variants/<suffix>/step_2_3/state.json`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_2_3_grid_aggregation`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `lrt_grid_aggregation`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_2_3_generate_remaining_grid_products.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
State and input fingerprints allow unchanged products to be skipped.

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

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

No fixed values in this category in the associated source.

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `KeyError: Missing 'lrt_grid_aggregation' section.` | `not isinstance(config.get('lrt_grid_aggregation'), dict)` | [Step_2_3_generate_remaining_grid_products.py:32](../../scripts/Step_2_3_generate_remaining_grid_products.py) |
| `KeyError: Missing 'lrt_grid_merge' section.` | `not isinstance(config.get('lrt_grid_merge'), dict)` | [Step_2_3_generate_remaining_grid_products.py:34](../../scripts/Step_2_3_generate_remaining_grid_products.py) |
| `RuntimeError: Worker source was not initialised.` | `_BASE is None` | [Step_2_3_generate_remaining_grid_products.py:141](../../scripts/Step_2_3_generate_remaining_grid_products.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `previous == expected_state` | [Step_2_3_generate_remaining_grid_products.py:402](../../scripts/Step_2_3_generate_remaining_grid_products.py) |
| `0` | `Emitted by main` | [Step_2_3_generate_remaining_grid_products.py:436](../../scripts/Step_2_3_generate_remaining_grid_products.py) |
| `1` | `except Exception` | [Step_2_3_generate_remaining_grid_products.py:440](../../scripts/Step_2_3_generate_remaining_grid_products.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

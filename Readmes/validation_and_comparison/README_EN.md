# Validation And Formation-Status Comparison (EN)

## Current Operation (2026-09-23)

The final report identifies its `phase`. Core does not require Step-6 products; bioacoustics checks Step 6 and its prerequisites. Without `BIOOTON_RUN_PLAN`, a direct command validates the legacy full scope. Readiness policy and individual require_* settings remain effective within the selected phase.


## Purpose
Compares formation-status products and creates the final validation report.

## Script
`tools/compare_formation_status_products.py, tools/final_validation_report.py`

## Inputs
- `outputs/step_2_*`
- `optional legacy/reference formation-status files`

## Outputs
- `outputs/step_8_susi_compatibility/*`
- `outputs/step_9_validation/*`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_7_0_master_table`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `master_table`, `final_validation`, `susi_sanity_check`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python tools/compare_formation_status_products.py --config config.horeka.json`
- `python tools/final_validation_report.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
Reports are rebuilt for each run; their input products remain unchanged.

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
| `master_table_missing_or_empty` | Master file is missing or empty. | [final_validation_report.py:249](../../tools/final_validation_report.py) |
| `master_table_read_error:{type(exc).__name__}` | Master file could not be read. | [final_validation_report.py:256](../../tools/final_validation_report.py) |
| `master_missing_column:{column}` | An enabled readiness check requires a missing master column. | [final_validation_report.py:295](../../tools/final_validation_report.py) |
| `{column}_not_ready:{not_ready}` | Under strict readiness policy, rows do not meet this requirement. | [final_validation_report.py:307](../../tools/final_validation_report.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `ok` | `Emitted by check_path` | [final_validation_report.py:35](../../tools/final_validation_report.py) |
| `missing` | `required and (not exists)` | [final_validation_report.py:37](../../tools/final_validation_report.py) |
| `empty` | `required and (not nonempty)` | [final_validation_report.py:39](../../tools/final_validation_report.py) |
| `optional_missing` | `not required and (not exists)` | [final_validation_report.py:41](../../tools/final_validation_report.py) |
| `missing_column` | `column not in table.columns` | [final_validation_report.py:289](../../tools/final_validation_report.py) |
| `ok` | `Emitted by master_readiness` | [final_validation_report.py:301](../../tools/final_validation_report.py) |
| `not_ready` | `Emitted by master_readiness` | [final_validation_report.py:301](../../tools/final_validation_report.py) |
| `validated` | `Emitted by main` | [final_validation_report.py:435](../../tools/final_validation_report.py) |
| `has_issues` | `critical or failed_manifest_steps or missing_planned_manifests or readiness['critical']` | [final_validation_report.py:442](../../tools/final_validation_report.py) |
| `ready` | `Emitted by main` | [final_validation_report.py:446](../../tools/final_validation_report.py) |
| `manual_review_required` | `Emitted by main` | [final_validation_report.py:446](../../tools/final_validation_report.py) |
| `approved` | `Emitted by main` | [final_validation_report.py:449](../../tools/final_validation_report.py) |
| `not_started` | `Emitted by main` | [final_validation_report.py:449](../../tools/final_validation_report.py) |

### Explicit Failure Messages

No fixed values in this category in the associated source.

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0 if technical_status == 'validated' else 2` | `Emitted by main` | [final_validation_report.py:495](../../tools/final_validation_report.py) |
| `0` | `Emitted by main` | [compare_formation_status_products.py:509](../../tools/compare_formation_status_products.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

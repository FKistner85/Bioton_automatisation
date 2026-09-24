# Step 2_4 10m Formation Status (EN)

## Purpose
Creates checkpointed 10m formation-status products.

## Script
`scripts/Step_2_4_generate_10m_formation_status_products.py`

## Inputs
- `outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet`
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`

No separate original INSPIRE 10m grid is read. As in Susi's
`3_10mgrid_prep.py`, the 100 10m cells per 100m INSPIRE ID are derived
deterministically in EPSG:3035: `x0=E100*100`, `y0=N100*100`, then
`grid_id_10=10mN(N100*10+dy)E(E100*10+dx)` for `dx,dy=0..9`.

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_4_susi_10m/*`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_2_4_10m_formation`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `susi_10m_products`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_2_4_generate_10m_formation_status_products.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
Parquet parts and `_batch_status` allow processing to resume after a timeout.

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

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `in_progress` | `reset_required` | [Step_2_4_generate_10m_formation_status_products.py:614](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `complete` | `Emitted by main` | [Step_2_4_generate_10m_formation_status_products.py:707](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:43](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `KeyError: Missing 'susi_10m_products' section in config.` | `'susi_10m_products' not in config` | [Step_2_4_generate_10m_formation_status_products.py:47](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:53](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: Invalid 100 m grid_id: {grid_id}` | `match is None` | [Step_2_4_generate_10m_formation_status_products.py:101](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `RuntimeError: Temporary final parquet is empty: {temporary}` | `not temporary.is_file() or temporary.stat().st_size == 0` | [Step_2_4_generate_10m_formation_status_products.py:307](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `RuntimeError: Step 2_4 worker was not initialised.` | `_WORKER_LRT is None or _WORKER_SETTINGS is None` | [Step_2_4_generate_10m_formation_status_products.py:467](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: 10 m grid selection CSV not found: {path}` | `not path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:503](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `KeyError: 10 m grid selection CSV needs a 'grid_100m_id' or 'grid_id' column.` | `column is None` | [Step_2_4_generate_10m_formation_status_products.py:510](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: 10 m grid selection CSV contains no usable grid IDs.` | `not selected` | [Step_2_4_generate_10m_formation_status_products.py:516](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Missing source parquet: {source}` | `not source.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:545](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Missing LRT GPKG: {lrt_gpkg}` | `not lrt_gpkg.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:547](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: No selected 100 m grid IDs occur in the Step 2.1 product.` | `not grid_ids` | [Step_2_4_generate_10m_formation_status_products.py:636](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `same_inputs and previous_state.get('status') == 'complete' and final_parquet.is_file() and (final_parquet.stat().st_size > 0) and (not args.force)` | [Step_2_4_generate_10m_formation_status_products.py:593](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `0` | `Emitted by main` | [Step_2_4_generate_10m_formation_status_products.py:738](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `1` | `except Exception` | [Step_2_4_generate_10m_formation_status_products.py:748](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

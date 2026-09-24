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
Logical step contracts are recorded in `pipeline_steps.json` under `step_2_1_100m_formation`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `lrt_grid_merge`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_2_1_merge_lrts_and_grid.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
Chunk checkpoints and the state file allow a run to resume.

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
| `majority_formation_status` | `Emitted by build_summary` | [Step_2_1_merge_lrts_and_grid.py:584](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `RuntimeError: Temporary GeoPackage is empty: {temporary}` | `not temporary.is_file() or temporary.stat().st_size == 0` | [Step_2_1_merge_lrts_and_grid.py:67](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_1_merge_lrts_and_grid.py:73](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `KeyError: Missing 'lrt_grid_merge' section in config.json.` | `not isinstance(section, dict)` | [Step_2_1_merge_lrts_and_grid.py:80](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_1_merge_lrts_and_grid.py:95](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Grid ID column '{grid_id_column}' not found. Available columns: {list(grid.columns)}` | `grid_id_column not in grid.columns` | [Step_2_1_merge_lrts_and_grid.py:161](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Grid and LRT data must both have a CRS.` | `grid.crs is None or lrt.crs is None` | [Step_2_1_merge_lrts_and_grid.py:182](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `RuntimeError: Step 2_1 worker was not initialised.` | `_WORKER_GRID is None or _WORKER_LRT is None or _WORKER_GRID_ID is None` | [Step_2_1_merge_lrts_and_grid.py:211](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `RuntimeError: No intersections found between grid and LRT.` | `not parts` | [Step_2_1_merge_lrts_and_grid.py:446](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Could not derive 100 m coordinates from grid_id. Examples: {bad}` | `ids.isna().any(axis=None)` | [Step_2_1_merge_lrts_and_grid.py:772](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `should_skip(output_paths, state_file, expected_state, args.force)` | [Step_2_1_merge_lrts_and_grid.py:1196](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `0` | `Emitted by main` | [Step_2_1_merge_lrts_and_grid.py:1271](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `1` | `except Exception` | [Step_2_1_merge_lrts_and_grid.py:1275](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

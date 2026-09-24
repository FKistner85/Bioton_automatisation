# Step 2_2 Point Assignment (EN)

## Purpose
Assigns every Dawn Chorus point to its INSPIRE 100 m grid cell and LRT polygons.
The grid ID is emitted even without a majority formation; majority formation
remains a separate attribute.

## Script
`scripts/Step_2_2_assign_points_to_lrt_grid.py`

## Inputs
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `outputs/step_2_variants/<suffix>/step_2_1/LRT_Grid_Majority_<suffix>.csv`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_2/DawnChorus_LRT_Grid_Assignment_<suffix>.csv`
- `outputs/step_2_variants/<suffix>/step_2_2/DawnChorus_LRT_Polygon_Matches_<suffix>.csv`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_2_2_point_assignment`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `point_lrt_assignment`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_2_2_assign_points_to_lrt_grid.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
When spatial inputs are unchanged, only affected/new IDs are processed.

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
| `processed` | `Emitted by build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:505](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `missing_coordinates` | `Emitted by build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:506](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `outside_majority_grid` | `Emitted by build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:510](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `inside_majority_grid_outside_lrt` | `Emitted by build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:515](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `inside_lrt_polygon` | `Emitted by build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:520](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_2_assign_points_to_lrt_grid.py:56](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `KeyError: Missing 'point_lrt_assignment' section in config.json.` | `not isinstance(section, dict)` | [Step_2_2_assign_points_to_lrt_grid.py:63](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_2_assign_points_to_lrt_grid.py:91](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: Grid ID column '{grid_id_column}' not found. Available columns: {list(grid.columns)}` | `grid_id_column not in grid.columns` | [Step_2_2_assign_points_to_lrt_grid.py:189](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: The INSPIRE grid contains no cells.` | `grid.empty` | [Step_2_2_assign_points_to_lrt_grid.py:203](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: The cleaned LRT layer has no CRS.` | `lrt.crs is None` | [Step_2_2_assign_points_to_lrt_grid.py:239](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `KeyError: No dawn_chorus_id/id column in {path}` | `Emitted by read_ids_file` | [Step_2_2_assign_points_to_lrt_grid.py:545](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `not target_ids` | [Step_2_2_assign_points_to_lrt_grid.py:694](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `0` | `Emitted by main` | [Step_2_2_assign_points_to_lrt_grid.py:786](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `1` | `except Exception` | [Step_2_2_assign_points_to_lrt_grid.py:790](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

# Step 2_0 LRT Cleaning (EN)

## Purpose
Cleans LRT polygons and normalises code, status and formation fields.

## Script
`scripts/Step_2_0_clean_lrts.py`

## Inputs
- `Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_<suffix>.gpkg`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`
- `outputs/step_2_variants/<suffix>/step_2_0/state.json`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_2_0_lrt_cleaning`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `lrt_cleaning`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_2_0_clean_lrts.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
State/Fingerprints entscheiden, ob ein Rebuild noetig ist.

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
| `conservation_status` | `Emitted by module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `Conservation_status` | `Emitted by module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `CONSERVATION_STATUS` | `Emitted by module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `conservationstatus` | `Emitted by module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `ConservationStatus` | `Emitted by module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_0_clean_lrts.py:52](../../scripts/Step_2_0_clean_lrts.py) |
| `KeyError: Missing 'lrt_cleaning' section in config.json.` | `not isinstance(section, dict)` | [Step_2_0_clean_lrts.py:59](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: 'lrt_cleaning.source_gpkgs' must be a non-empty list.` | `not isinstance(section['source_gpkgs'], list) or not section['source_gpkgs']` | [Step_2_0_clean_lrts.py:69](../../scripts/Step_2_0_clean_lrts.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_0_clean_lrts.py:76](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: Required column '{canonical}' not found in {source}. Available columns: {list(gdf.columns)}` | `found is None` | [Step_2_0_clean_lrts.py:133](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: No layers found in {gpkg_path}` | `not layers` | [Step_2_0_clean_lrts.py:163](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: Layer has no CRS: {gpkg_path.name}:{layer_name}` | `layer.crs is None` | [Step_2_0_clean_lrts.py:186](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: No usable LRT layers found in {gpkg_path}` | `not prepared` | [Step_2_0_clean_lrts.py:203](../../scripts/Step_2_0_clean_lrts.py) |
| `RuntimeError: No formation group was processed successfully.` | `not results` | [Step_2_0_clean_lrts.py:369](../../scripts/Step_2_0_clean_lrts.py) |
| `RuntimeError: Atomic GPKG validation failed: expected {len(output)} rows, found {written_rows}.` | `written_rows != len(output)` | [Step_2_0_clean_lrts.py:536](../../scripts/Step_2_0_clean_lrts.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `should_skip(output_gpkg, state_file, expected_state, args.force)` | [Step_2_0_clean_lrts.py:469](../../scripts/Step_2_0_clean_lrts.py) |
| `0` | `Emitted by main` | [Step_2_0_clean_lrts.py:549](../../scripts/Step_2_0_clean_lrts.py) |
| `1` | `except Exception` | [Step_2_0_clean_lrts.py:553](../../scripts/Step_2_0_clean_lrts.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

# Pipeline Control (EN)

## Current Operation (2026-09-23)

`add_new_ids` and `from_scratch` plan the core only. `bioacoustics` plans Step 6 and its master/validation ending. The actual run plan and launcher determine submissions. Bioacoustics consumes prepared metadata, inventory and master rather than Step-1 deltas. Both phases share the lock. `afterany` permits diagnostics after failure; hard `afterok` edges (especially Step 6) block dependent work and can leave `DependencyNeverSatisfied` jobs. Inspect before resubmission.


### Slurm submission failures

`AssocGrpSubmitJobsLimit` means the shared Slurm association submission limit has been reached. Some jobs may already be queued. Inspect `squeue` and `sacct` first; do not submit a second pipeline or remove the lock while jobs remain active. Bounded workers reduce the number of queued array elements.

## Purpose
Builds a deterministic run plan before submitting the Slurm DAG and prevents
concurrent workflows from writing the same products.

## Tools
`tools/plan_pipeline_run.py`, `tools/pipeline_lock.py`,
`tools/run_with_manifest.py`, `submit_bio_o_ton_horeka.sh`

## Inputs
- Dawn Chorus CSV and Step 1 domain fingerprints
- previous master table
- global step states and configured outputs

## Outputs
- `outputs/step_0_control/run_plans/<run_id>/run_plan.json`
- `outputs/step_0_control/run_plans/<run_id>/*_ids.csv`
- `outputs/step_0_control/full_rebuild/current.json`
- `outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json`
- `outputs/step_0_control/pipeline.lock/owner.json`
- `outputs/step_0_manifests/<step>/<step_run_id>.json`

## Behaviour
`add_new_ids` plans new, changed and previously problematic IDs.
`from_scratch` plans all current IDs and all global core steps. Slurm uses both `afterany` and `afterok`; inspect jobs blocked by failed dependencies.
Successful full-run steps receive atomic markers; a new submission only queues
steps whose markers are missing.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `in_progress` | `not resume` | [plan_pipeline_run.py:469](../../tools/plan_pipeline_run.py) |
| `complete` | `Emitted by main` | [run_with_manifest.py:117](../../tools/run_with_manifest.py) |
| `failed` | `Emitted by main` | [run_with_manifest.py:117](../../tools/run_with_manifest.py) |
| `starting` | `Emitted by main` | [horeka_controller.py:180](../../tools/horeka_controller.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `ValueError: Bioacoustics is disabled in this configuration.` | `not config.get('bioacoustics', {}).get('enabled', True)` | [plan_pipeline_run.py:522](../../tools/plan_pipeline_run.py) |
| `FileNotFoundError: Run the core pipeline first; missing prerequisite: {path}` | `not path.is_file()` | [plan_pipeline_run.py:528](../../tools/plan_pipeline_run.py) |
| `ValueError: Prepared metadata and master IDs differ; finish the core pipeline first.` | `ids != master_ids` | [plan_pipeline_run.py:534](../../tools/plan_pipeline_run.py) |
| `ValueError: Require positive counts and 0 <= worker-index < worker-count` | `worker_count < 1 or task_count < 1 or (not 0 <= worker_index < worker_count)` | [run_array_worker.py:13](../../tools/run_array_worker.py) |
| `ValueError: A child command is required` | `not command` | [run_array_worker.py:20](../../tools/run_array_worker.py) |
| `ValueError: Unknown pipeline phase: {phase}` | `phase not in {'core', 'bioacoustics', 'all'}` | [pipeline_phase.py:16](../../scripts/pipeline_phase.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `args.mode == 'bioacoustics'` | [plan_pipeline_run.py:564](../../tools/plan_pipeline_run.py) |
| `0` | `Emitted by main` | [plan_pipeline_run.py:884](../../tools/plan_pipeline_run.py) |
| `3` | `except FileExistsError` | [pipeline_lock.py:50](../../tools/pipeline_lock.py) |
| `0` | `Emitted by acquire` | [pipeline_lock.py:62](../../tools/pipeline_lock.py) |
| `0` | `not path.exists()` | [pipeline_lock.py:68](../../tools/pipeline_lock.py) |
| `4` | `not force and owner_run and (owner_run != run_id)` | [pipeline_lock.py:76](../../tools/pipeline_lock.py) |
| `0` | `Emitted by release` | [pipeline_lock.py:79](../../tools/pipeline_lock.py) |
| `0` | `args.command == 'status'` | [pipeline_lock.py:95](../../tools/pipeline_lock.py) |
| `2` | `not args.run_id and (not args.force)` | [pipeline_lock.py:98](../../tools/pipeline_lock.py) |
| `2` | `not command` | [run_with_manifest.py:76](../../tools/run_with_manifest.py) |
| `submitted.returncode or 1` | `submitted.returncode != 0 or not submission_path.is_file()` | [horeka_controller.py:233](../../tools/horeka_controller.py) |
| `0` | `args.local_test` | [horeka_controller.py:256](../../tools/horeka_controller.py) |
| `130` | `except KeyboardInterrupt` | [horeka_controller.py:313](../../tools/horeka_controller.py) |
| `128 + interrupted` | `interrupted` | [run_array_worker.py:54](../../tools/run_array_worker.py) |
| `1` | `failed` | [run_array_worker.py:57](../../tools/run_array_worker.py) |
| `0` | `Emitted by run_worker` | [run_array_worker.py:58](../../tools/run_array_worker.py) |
| `run_stage_all(root, Path(sys.executable), variants, args.stage, force=args.force, ids_file=args.ids_file, max_workers=1)` | `config.get('lrt_variants', {}).get('input_dir')` | [run_spatial_stage.py:22](../../tools/run_spatial_stage.py) |
| `0` | `Emitted by main` | [finalize_master.py:23](../../tools/finalize_master.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

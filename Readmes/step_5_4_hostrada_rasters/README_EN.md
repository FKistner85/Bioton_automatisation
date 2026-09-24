# Step 5_4 HOSTRADA 100m Rasters (EN)

The main workflow launches Step 5_4 as a Slurm array: up to two Slurm workers process
multiple deterministic variable/year tasks sequentially; each logical task processes
one combination. Incomplete years (fewer
than twelve monthly NetCDF files) are skipped without error. A short single-job
verification checks tile states for all complete source years before Step 5_5
runs raster QC.

`tools/run_hostrada_raster_all.py` is the array dispatcher and calls the raster
logic in `scripts/Step_5_4_prepare_hostrada_rasters.py`.

Input:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`

Outputs:
- `outputs/step_5_4_hostrada_raster_products/Hostrada_<Variable>/*.tif`
- `.../_tile_status/<year>/*.json`
- `.../_force_state/<Variable>_<year>.json`

A full run invalidates old tile status once per generation. The persistent
`in_progress` state survives a new Slurm submission, so completed tiles are
reused after a timeout.

The orchestrator defaults to two parallel array tasks with 8 CPUs and 32 GB
RAM each. Adjust them without code changes:

```bash
BIOOTON_STEP54_CPUS=8 \
BIOOTON_STEP54_MEMORY=32G \
BIOOTON_STEP54_MAX_CONCURRENT_TASKS=2 \
bash slurm_add_new_ids.sh
```

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `in_progress` | `Emitted by prepare_force_resume` | [Step_5_4_prepare_hostrada_rasters.py:142](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `complete` | `Emitted by finish_force_resume` | [Step_5_4_prepare_hostrada_rasters.py:171](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `KeyError: Missing hostrada_raster_products section in config.` | `'hostrada_raster_products' not in config` | [Step_5_4_prepare_hostrada_rasters.py:48](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `ValueError: Unsafe tile status directory: {status_dir}` | `resolved_output not in resolved_status.parents` | [Step_5_4_prepare_hostrada_rasters.py:137](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `FileNotFoundError: Missing HOSTRADA file: {path}` | `not path.exists()` | [Step_5_4_prepare_hostrada_rasters.py:223](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `ValueError: Task index {args.task_index} outside 0..{len(jobs) - 1}` | `args.task_index < 0 or args.task_index >= len(jobs)` | [run_hostrada_raster_all.py:131](../../tools/run_hostrada_raster_all.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `Emitted by main` | [Step_5_4_prepare_hostrada_rasters.py:388](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `1` | `except Exception` | [Step_5_4_prepare_hostrada_rasters.py:398](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `0` | `args.task_count` | [run_hostrada_raster_all.py:112](../../tools/run_hostrada_raster_all.py) |
| `1 if incomplete else 0` | `args.verify_array` | [run_hostrada_raster_all.py:120](../../tools/run_hostrada_raster_all.py) |
| `0` | `not task_is_complete(input_dir, variable, year)` | [run_hostrada_raster_all.py:140](../../tools/run_hostrada_raster_all.py) |
| `0` | `Emitted by main` | [run_hostrada_raster_all.py:171](../../tools/run_hostrada_raster_all.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

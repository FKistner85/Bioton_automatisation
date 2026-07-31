# Step 5_4 HOSTRADA 100m Rasters (EN)

The main workflow launches Step 5_4 as a Slurm array: one array task processes
exactly one deterministic variable/year combination. Incomplete years (fewer
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

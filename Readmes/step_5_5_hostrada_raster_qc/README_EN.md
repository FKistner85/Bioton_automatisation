# Step 5_5 HOSTRADA Raster QC (EN)

Recursively checks all raster variables for readability, dimensions, CRS,
NoData and constant or entirely missing rows and columns.

Input:
- `outputs/step_5_4_hostrada_raster_products/**/*.tif`

Outputs:
- `outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.csv`
- `hostrada_raster_quality.json`
- `hostrada_raster_quality.md`
- `state.json`

Unchanged clean rasters are reused by file size and mtime. Previous issues are
checked again.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `ONLY_NODATA` | `valid.size == 0` | [Step_5_5_check_hostrada_raster_products.py:104](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `OK` | `not (valid.size == 0)` | [Step_5_5_check_hostrada_raster_products.py:107](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `KeyError: Missing hostrada_raster_quality_check section in config.` | `'hostrada_raster_quality_check' not in config` | [Step_5_5_check_hostrada_raster_products.py:26](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `FileNotFoundError: No TIFF files found in {input_dir}` | `not tif_files` | [Step_5_5_check_hostrada_raster_products.py:204](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `Emitted by main` | [Step_5_5_check_hostrada_raster_products.py:297](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `1` | `except Exception` | [Step_5_5_check_hostrada_raster_products.py:300](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

# Step 5_3 HOSTRADA Monthly Data (EN)

Mirrors configured DWD HOSTRADA monthly NetCDF files for Ta, Rh, Radiation,
CloudCover, Winddirection and Windspeed.

Input: DWD Open Data URLs from `config.horeka.json`.

Outputs:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`
- `outputs/step_5_3_hostrada_monthly_download/download_log.csv`

Existing non-empty files are skipped. Step 5_4 depends on this step.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `{type(exc).__name__}:{exc}` | Original exception type and message; not a separate fixed code. | [Step_5_3_download_hostrada_monthly.py:106](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `failed` | `except Exception` | [Step_5_3_download_hostrada_monthly.py:105](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `KeyError: Missing hostrada_monthly_download section in config.` | `'hostrada_monthly_download' not in config` | [Step_5_3_download_hostrada_monthly.py:24](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `1 if failed else 0` | `Emitted by main` | [Step_5_3_download_hostrada_monthly.py:202](../../scripts/Step_5_3_download_hostrada_monthly.py) |
| `1` | `except Exception` | [Step_5_3_download_hostrada_monthly.py:205](../../scripts/Step_5_3_download_hostrada_monthly.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

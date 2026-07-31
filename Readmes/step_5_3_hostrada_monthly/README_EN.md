# Step 5_3 HOSTRADA Monthly Data (EN)

Mirrors configured DWD HOSTRADA monthly NetCDF files for Ta, Rh, Radiation,
CloudCover, Winddirection and Windspeed.

Input: DWD Open Data URLs from `config.horeka.json`.

Outputs:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`
- `outputs/step_5_3_hostrada_monthly_download/download_log.csv`

Existing non-empty files are skipped. Step 5_4 depends on this step.

# Step 5_3 HOSTRADA Monatsdaten (DE)

Spiegelt die konfigurierten DWD-HOSTRADA-Monats-NetCDFs fuer Ta, Rh,
Radiation, CloudCover, Winddirection und Windspeed.

Input: DWD Open Data URLs aus `config.horeka.json`.

Outputs:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`
- `outputs/step_5_3_hostrada_monthly_download/download_log.csv`

Vorhandene nichtleere Dateien werden uebersprungen. Step 5_4 haengt von diesem
Step ab.

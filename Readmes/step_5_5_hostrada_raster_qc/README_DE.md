# Step 5_5 HOSTRADA Raster-QC (DE)

Prueft alle Rastervariablen rekursiv auf Lesbarkeit, Dimensionen, CRS, NoData
und konstante beziehungsweise vollstaendig fehlende Zeilen/Spalten.

Input:
- `outputs/step_5_4_hostrada_raster_products/**/*.tif`

Outputs:
- `outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.csv`
- `hostrada_raster_quality.json`
- `hostrada_raster_quality.md`
- `state.json`

Unveraenderte fehlerfreie Raster werden anhand Dateigroesse und mtime
wiederverwendet. Alte Fehler werden erneut geprueft.

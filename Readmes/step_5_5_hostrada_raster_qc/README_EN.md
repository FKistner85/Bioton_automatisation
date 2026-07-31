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

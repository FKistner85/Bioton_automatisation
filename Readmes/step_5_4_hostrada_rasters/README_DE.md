# Step 5_4 HOSTRADA 100m Raster (DE)

Der Hauptworkflow startet Step 5_4 als Slurm-Array: Ein Array-Task bearbeitet
genau eine deterministische Variable/Jahr-Kombination. Unvollstaendige Jahre
(weniger als zwoelf Monats-NetCDFs) werden ohne Fehler uebersprungen. Nach dem
Array verifiziert ein kurzer Einzeljob die Tile-Statusdateien aller vollstaendigen
Quelljahre, bevor Step 5_5 die Raster-QC ausfuehrt.

`tools/run_hostrada_raster_all.py` ist der Array-Dispatcher und ruft die
Rasterlogik aus `scripts/Step_5_4_prepare_hostrada_rasters.py` auf.

Input:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`

Outputs:
- `outputs/step_5_4_hostrada_raster_products/Hostrada_<Variable>/*.tif`
- `.../_tile_status/<year>/*.json`
- `.../_force_state/<Variable>_<year>.json`

Im Vollauf werden alte Tile-Statusdateien pro Generation genau einmal
invalidiert. Ein `in_progress`-Status ueberlebt neue Slurm-Submits, sodass nach
einem Timeout fertiggestellte Tiles weiterverwendet werden.

Standardressourcen im Orchestrator: zwei parallele Array-Tasks mit je 8 CPUs
und 32 GB RAM. Diese Werte lassen sich ohne Codeaenderung anpassen:

```bash
BIOOTON_STEP54_CPUS=8 \
BIOOTON_STEP54_MEMORY=32G \
BIOOTON_STEP54_MAX_CONCURRENT_TASKS=2 \
bash slurm_add_new_ids.sh
```

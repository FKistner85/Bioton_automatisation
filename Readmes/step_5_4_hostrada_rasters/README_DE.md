# Step 5_4 HOSTRADA 100m Raster (DE)

Der Hauptworkflow startet Step 5_4 als Slurm-Array: Bis zu zwei Slurm-Worker bearbeiten
mehrere deterministische Variable/Jahr-Aufgaben nacheinander; jede logische Aufgabe
verarbeitet genau eine Kombination. Unvollstaendige Jahre
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

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `in_progress` | `Ausgabe in prepare_force_resume` | [Step_5_4_prepare_hostrada_rasters.py:142](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `complete` | `Ausgabe in finish_force_resume` | [Step_5_4_prepare_hostrada_rasters.py:171](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `KeyError: Missing hostrada_raster_products section in config.` | `'hostrada_raster_products' not in config` | [Step_5_4_prepare_hostrada_rasters.py:48](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `ValueError: Unsafe tile status directory: {status_dir}` | `resolved_output not in resolved_status.parents` | [Step_5_4_prepare_hostrada_rasters.py:137](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `FileNotFoundError: Missing HOSTRADA file: {path}` | `not path.exists()` | [Step_5_4_prepare_hostrada_rasters.py:223](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `ValueError: Task index {args.task_index} outside 0..{len(jobs) - 1}` | `args.task_index < 0 or args.task_index >= len(jobs)` | [run_hostrada_raster_all.py:131](../../tools/run_hostrada_raster_all.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `Ausgabe in main` | [Step_5_4_prepare_hostrada_rasters.py:388](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `1` | `except Exception` | [Step_5_4_prepare_hostrada_rasters.py:398](../../scripts/Step_5_4_prepare_hostrada_rasters.py) |
| `0` | `args.task_count` | [run_hostrada_raster_all.py:112](../../tools/run_hostrada_raster_all.py) |
| `1 if incomplete else 0` | `args.verify_array` | [run_hostrada_raster_all.py:120](../../tools/run_hostrada_raster_all.py) |
| `0` | `not task_is_complete(input_dir, variable, year)` | [run_hostrada_raster_all.py:140](../../tools/run_hostrada_raster_all.py) |
| `0` | `Ausgabe in main` | [run_hostrada_raster_all.py:171](../../tools/run_hostrada_raster_all.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

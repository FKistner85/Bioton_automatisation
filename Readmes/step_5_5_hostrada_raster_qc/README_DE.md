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

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `ONLY_NODATA` | `valid.size == 0` | [Step_5_5_check_hostrada_raster_products.py:104](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `OK` | `not (valid.size == 0)` | [Step_5_5_check_hostrada_raster_products.py:107](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `KeyError: Missing hostrada_raster_quality_check section in config.` | `'hostrada_raster_quality_check' not in config` | [Step_5_5_check_hostrada_raster_products.py:26](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `FileNotFoundError: No TIFF files found in {input_dir}` | `not tif_files` | [Step_5_5_check_hostrada_raster_products.py:204](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `Ausgabe in main` | [Step_5_5_check_hostrada_raster_products.py:297](../../scripts/Step_5_5_check_hostrada_raster_products.py) |
| `1` | `except Exception` | [Step_5_5_check_hostrada_raster_products.py:300](../../scripts/Step_5_5_check_hostrada_raster_products.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

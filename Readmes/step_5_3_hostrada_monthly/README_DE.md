# Step 5_3 HOSTRADA Monatsdaten (DE)

Spiegelt die konfigurierten DWD-HOSTRADA-Monats-NetCDFs fuer Ta, Rh,
Radiation, CloudCover, Winddirection und Windspeed.

Input: DWD Open Data URLs aus `config.horeka.json`.

Outputs:
- `outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc`
- `outputs/step_5_3_hostrada_monthly_download/download_log.csv`

Vorhandene nichtleere Dateien werden uebersprungen. Step 5_4 haengt von diesem
Step ab.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `{type(exc).__name__}:{exc}` | Originaler Exception-Typ und Meldung; kein eigener statischer Fehlercode. | [Step_5_3_download_hostrada_monthly.py:106](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `failed` | `except Exception` | [Step_5_3_download_hostrada_monthly.py:105](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `KeyError: Missing hostrada_monthly_download section in config.` | `'hostrada_monthly_download' not in config` | [Step_5_3_download_hostrada_monthly.py:24](../../scripts/Step_5_3_download_hostrada_monthly.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `1 if failed else 0` | `Ausgabe in main` | [Step_5_3_download_hostrada_monthly.py:202](../../scripts/Step_5_3_download_hostrada_monthly.py) |
| `1` | `except Exception` | [Step_5_3_download_hostrada_monthly.py:205](../../scripts/Step_5_3_download_hostrada_monthly.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

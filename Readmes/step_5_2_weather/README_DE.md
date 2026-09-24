# Step 5_2 HOSTRADA Weather Per Recording (DE)

## Zweck
Laedt/cached HOSTRADA und extrahiert Wetterzeitreihen pro Recording.

## Script
`scripts/Step_5_2_download_weather_data.py`

## Eingaben
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `DWD HOSTRADA`

## Outputs
- `PointData/Weather/Hostrada/weather_<id>.csv`
- `outputs/step_5_2_weather_download/*`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_5_1_weather_inventory`, `step_5_2_weather_download`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `weather_inventory`, `weather_download`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_5_2_download_weather_data.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die Parallelitaet innerhalb eines Jobs. Der
Orchestrator teilt grosse ID-Mengen deterministisch auf bis zu acht
`bio_step52`-Array-Tasks auf; standardmaessig laufen maximal vier Tasks
gleichzeitig. Kleine inkrementelle Mengen bleiben ein einzelner Task.
Gemeinsam genutzte Monats-NetCDFs besitzen einen LSDF-kompatiblen Download-Lock,
damit parallele Tasks keine unvollstaendigen Cachedateien erzeugen. Nach dem
Array bestaetigt `bio_step52verify`, dass fuer jede angeforderte, noch in den
Metadaten vorhandene ID eine nichtleere Wetter-CSV geschrieben wurde.

## Checkpoint/Resume
Nichtleere `weather_<id>.csv` und `_recording_status` werden wiederverwendet.
Bei `--ids-file` ist diese ID-Liste verbindlich; alte Probleme ausserhalb des
Run-Plans werden nicht unbeabsichtigt erneut verarbeitet. Fortschritt und ETA
werden pro Shard in `progress_shard_<n>.json` gespeichert.

## Qualitaetskontrolle

Das Wetterfenster umfasst `preceding_days` vollstaendige lokale Kalendertage
vor der Aufnahme plus den gesamten Aufnahmetag in `input_timezone`.
Bei zehn Vortagen sind das normalerweise 264 Stunden, bei einer Zeitumstellung
263 oder 265 Stunden. Download und Inventar verwenden dieselben Kalendergrenzen.
Die CSV speichert weiterhin lokale Uhrzeiten ohne Offset. Das Inventar erwartet
deshalb die fehlende Fruehjahrsstunde beziehungsweise die doppelte Herbststunde;
zusaetzliche Duplikate und fehlende Messwerte bleiben Fehler.
`weather_inventory.expected_rows` ist nur der Ersatzwert ohne Aufnahmezeit;
sonst ergibt sich die Zeilenzahl aus dem konkreten Fenster.

Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Run-Statuswerte stehen in `scripts/common.py`; `schemas/status_model.json` definiert Status-Event-Felder.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `filename_does_not_match_weather_id_pattern` | Wetter-Dateiname entspricht nicht dem erwarteten ID-Muster. | [Step_5_1_Weather_inventory.py:205](../../scripts/Step_5_1_Weather_inventory.py) |
| `invalid_metadata_datetime` | Aufnahmezeit aus Metadaten ist fuer das Wetterfenster ungueltig. | [Step_5_1_Weather_inventory.py:216](../../scripts/Step_5_1_Weather_inventory.py) |
| `empty_file` | Vorhandene Datei hat null Bytes. | [Step_5_1_Weather_inventory.py:245](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_row_count` | Zeilenzahl entspricht nicht dem erwarteten Wetterfenster. | [Step_5_1_Weather_inventory.py:270](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_required_column` | Mindestens eine konfigurierte Pflichtspalte fehlt. | [Step_5_1_Weather_inventory.py:277](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_value` | Werte fehlen; massgeblich ist die jeweilige Pruefung bzw. NaN-Toleranz. | [Step_5_1_Weather_inventory.py:286](../../scripts/Step_5_1_Weather_inventory.py) |
| `unparseable_datetime` | Zeitstempel in der Datendatei sind nicht parsebar. | [Step_5_1_Weather_inventory.py:294](../../scripts/Step_5_1_Weather_inventory.py) |
| `duplicate_datetime` | Mehr Zeitstempelduplikate als im lokalen DST-Fenster zulaessig. | [Step_5_1_Weather_inventory.py:302](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_time_interval` | Zeitstempel einschliesslich ihrer Haeufigkeit entsprechen nicht dem vollstaendigen erwarteten lokalen Wetterfenster. Korrekte Sommer-/Winterzeitwechsel sind erlaubt; Code allein unterscheidet fehlende, zusaetzliche und verschobene Stunden nicht. | [Step_5_1_Weather_inventory.py:316](../../scripts/Step_5_1_Weather_inventory.py) |
| `unexpected_time_window` | Zeitstempel decken nicht das berechnete lokale Wetterfenster ab. | [Step_5_1_Weather_inventory.py:330](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_datetime_column` | Wetter-CSV enthaelt keine datetime-Spalte. | [Step_5_1_Weather_inventory.py:334](../../scripts/Step_5_1_Weather_inventory.py) |
| `implausible_value` | Mindestens ein Wert verletzt konfigurierte Plausibilitaetsgrenzen. | [Step_5_1_Weather_inventory.py:338](../../scripts/Step_5_1_Weather_inventory.py) |
| `read_error:{type(exc).__name__}` | Datendatei konnte nicht gelesen werden; Exception-Typ steht im Suffix. | [Step_5_1_Weather_inventory.py:341](../../scripts/Step_5_1_Weather_inventory.py) |
| `missing_file` | Erwartete Datei fehlt. | [Step_5_1_Weather_inventory.py:373](../../scripts/Step_5_1_Weather_inventory.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `out_of_bounds` | `bounds_checked and (not bounds_ok)` | [Step_5_2_download_weather_data.py:422](../../scripts/Step_5_2_download_weather_data.py) |
| `upstream_unavailable` | `unavailable_source_months` | [Step_5_2_download_weather_data.py:481](../../scripts/Step_5_2_download_weather_data.py) |
| `ok` | `Ausgabe in process_recording` | [Step_5_2_download_weather_data.py:482](../../scripts/Step_5_2_download_weather_data.py) |
| `failed` | `except Exception` | [Step_5_2_download_weather_data.py:485](../../scripts/Step_5_2_download_weather_data.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_5_1_Weather_inventory.py:76](../../scripts/Step_5_1_Weather_inventory.py) |
| `KeyError: Missing 'weather_inventory' section in config.` | `not isinstance(config.get('weather_inventory'), dict)` | [Step_5_1_Weather_inventory.py:80](../../scripts/Step_5_1_Weather_inventory.py) |
| `ValueError: Metadata ID column '{id_column}' not found in {metadata_csv}.` | `id_column not in metadata.columns` | [Step_5_1_Weather_inventory.py:133](../../scripts/Step_5_1_Weather_inventory.py) |
| `NotADirectoryError: Weather directory not found: {directory}` | `not directory.is_dir()` | [Step_5_1_Weather_inventory.py:512](../../scripts/Step_5_1_Weather_inventory.py) |
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_5_2_download_weather_data.py:98](../../scripts/Step_5_2_download_weather_data.py) |
| `KeyError: Missing 'weather_download' section in config.json.` | `not isinstance(section, dict)` | [Step_5_2_download_weather_data.py:104](../../scripts/Step_5_2_download_weather_data.py) |
| `RuntimeError: Step 5_2 worker was not initialised.` | `_worker_transformer is None or _worker_preceding_days is None or _worker_input_timezone is None or (_worker_cache_dir is None) or (_worker_download_settings is None)` | [Step_5_2_download_weather_data.py:532](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: Input CSV missing required column(s): {missing}.` | `missing` | [Step_5_2_download_weather_data.py:579](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: --task-count must be at least 1.` | `args.task_count < 1` | [Step_5_2_download_weather_data.py:812](../../scripts/Step_5_2_download_weather_data.py) |
| `ValueError: --task-index must satisfy 0 <= index < task-count.` | `args.task_index < 0 or args.task_index >= args.task_count` | [Step_5_2_download_weather_data.py:814](../../scripts/Step_5_2_download_weather_data.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `args.list_only` | [Step_5_1_Weather_inventory.py:570](../../scripts/Step_5_1_Weather_inventory.py) |
| `0` | `Ausgabe in main` | [Step_5_1_Weather_inventory.py:674](../../scripts/Step_5_1_Weather_inventory.py) |
| `1` | `except Exception` | [Step_5_1_Weather_inventory.py:677](../../scripts/Step_5_1_Weather_inventory.py) |
| `1` | `missing` | [Step_5_2_download_weather_data.py:847](../../scripts/Step_5_2_download_weather_data.py) |
| `2` | `unavailable` | [Step_5_2_download_weather_data.py:854](../../scripts/Step_5_2_download_weather_data.py) |
| `0` | `args.verify_shards` | [Step_5_2_download_weather_data.py:855](../../scripts/Step_5_2_download_weather_data.py) |
| `1 if processed_failed or (bool(section.get('fail_on_upstream_unavailable', False)) and processed_upstream_unavailable) else 0` | `Ausgabe in main` | [Step_5_2_download_weather_data.py:1269](../../scripts/Step_5_2_download_weather_data.py) |
| `1` | `except Exception` | [Step_5_2_download_weather_data.py:1288](../../scripts/Step_5_2_download_weather_data.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

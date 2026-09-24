# Step 4 Sentinel-2 Mirror And Inventory (DE)

## Zweck
Spiegelt externe Sentinel-2-Drive-Dateien und inventarisiert GeoTIFFs. Die
Score-Tabelle wird ueber die konfigurierte ID-Spalte `DC_id` verbunden;
gaengige Alternativen wie `id` und `dawn_chorus_id` werden ebenfalls erkannt.

## Script
`scripts/Step_4_1_Sentinel2_download.py, scripts/Step_4_0_Sentinel2_inventory.py`

## Eingaben
- `Google Drive token.json`
- `PointData/S2`
- `PointData/S2_Scores.csv`

## Outputs
- `PointData/S2/*.tif`
- `outputs/step_4_0_Sentinel2_inventory/*`
- `outputs/step_4_1_sentinel2_download/*`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_4_1_sentinel2_mirror`, `step_4_0_sentinel2_inventory`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `sentinel2_download`, `sentinel2_inventory`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_4_1_Sentinel2_download.py --config config.horeka.json`
- `python scripts/Step_4_0_Sentinel2_inventory.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Drive-Log, Dateigroesse und mtime steuern inkrementelle Verarbeitung.

## Qualitaetskontrolle
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
| `score_rows_with_invalid_id:{invalid_id_count}` | Scoredatei enthaelt Zeilen ohne gueltige ID. | [Step_4_0_Sentinel2_inventory.py:222](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `duplicate_score_rows:{row_count}` | Mehrere Score-Zeilen fuer dieselbe ID. | [Step_4_0_Sentinel2_inventory.py:275](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `non_numeric_or_missing_scores:{missing_numeric_count}` | Scorewerte sind nicht numerisch oder fehlen. | [Step_4_0_Sentinel2_inventory.py:280](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `scores_outside_0_1:{invalid_range_count}` | Numerische Sentinel-Scores liegen ausserhalb 0 bis 1. | [Step_4_0_Sentinel2_inventory.py:285](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `quality_score_missing` | Fuer die Aufnahme liegt kein Score vor. | [Step_4_0_Sentinel2_inventory.py:290](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `no_valid_quality_score` | Kein gueltiger Sentinel-Score in den vorhandenen Zeilen. | [Step_4_0_Sentinel2_inventory.py:293](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `unexpected_raster_driver:{dataset.driver}` | Rasterformat ist nicht GTiff. | [Step_4_0_Sentinel2_inventory.py:358](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `invalid_dimensions:{dataset.width}x{dataset.height}` | Raster-/Bildbreite oder -hoehe ist ungueltig. | [Step_4_0_Sentinel2_inventory.py:363](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `no_raster_bands` | Raster enthaelt keine Baender. | [Step_4_0_Sentinel2_inventory.py:368](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `missing_crs` | Raster hat kein Koordinatenreferenzsystem. | [Step_4_0_Sentinel2_inventory.py:371](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `identity_geotransform` | Raster besitzt nur die Identitaetstransformation; Georeferenzierung pruefen. | [Step_4_0_Sentinel2_inventory.py:374](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `non_finite_bounds` | Rastergrenzen enthalten NaN oder unendliche Werte. | [Step_4_0_Sentinel2_inventory.py:387](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `invalid_bounds` | Rastergrenzen haben keine gueltige raeumliche Ausdehnung. | [Step_4_0_Sentinel2_inventory.py:393](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `raster_read_failed:{type(exc).__name__}:{exc}` | Raster konnte nicht geoeffnet oder gelesen werden. | [Step_4_0_Sentinel2_inventory.py:448](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `all_pixels_nodata` | Alle geprueften Rasterpixel sind NoData. | [Step_4_0_Sentinel2_inventory.py:470](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `contains_nan_values:{nan_values}` | Raster enthaelt NaN-Werte. | [Step_4_0_Sentinel2_inventory.py:473](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `contains_infinite_values:{infinite_values}` | Raster enthaelt unendliche Werte. | [Step_4_0_Sentinel2_inventory.py:478](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `constant_raster:value={global_min}` | Alle gueltigen Rasterwerte sind identisch; Plausibilitaet pruefen. | [Step_4_0_Sentinel2_inventory.py:483](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `filename_does_not_contain_id_before_tif_extension` | TIFF-Dateiname liefert keine erwartete Aufnahme-ID. | [Step_4_0_Sentinel2_inventory.py:524](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `source_stat_failed:{type(exc).__name__}:{exc}` | Quelldatei konnte nicht per Dateisystem-Stat abgefragt werden. | [Step_4_0_Sentinel2_inventory.py:532](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `empty_file` | Vorhandene Datei hat null Bytes. | [Step_4_0_Sentinel2_inventory.py:574](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `duplicate_tif_files_for_id:{len(id_rows)}` | Mehrere TIFF-Dateien sind derselben Aufnahme zugeordnet. | [Step_4_0_Sentinel2_inventory.py:948](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `quality_score_missing` | Fuer die Aufnahme liegt kein Score vor. | [Step_4_0_Sentinel2_inventory.py:969](../../scripts/Step_4_0_Sentinel2_inventory.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `skipped_existing_immutable` | `dc_id in immutable_ids` | [sentinel2_gee.py:666](../../scripts/sentinel2_gee.py) |
| `completed_existing_task` | `state == 'COMPLETED'` | [sentinel2_gee.py:683](../../scripts/sentinel2_gee.py) |
| `ready` | `Ausgabe in run_gee_drive_exports` | [sentinel2_gee.py:721](../../scripts/sentinel2_gee.py) |
| `score_only` | `score_only` | [sentinel2_gee.py:748](../../scripts/sentinel2_gee.py) |
| `score_only` | `bool(getattr(args, 'score_only', False))` | [sentinel2_gee.py:815](../../scripts/sentinel2_gee.py) |
| `skipped_existing` | `ok` | [sentinel2_gee.py:837](../../scripts/sentinel2_gee.py) |
| `downloaded` | `ok` | [sentinel2_gee.py:847](../../scripts/sentinel2_gee.py) |
| `validation_failed` | `not (ok)` | [sentinel2_gee.py:850](../../scripts/sentinel2_gee.py) |
| `download_failed` | `except Exception` | [sentinel2_gee.py:854](../../scripts/sentinel2_gee.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_4_0_Sentinel2_inventory.py:104](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `TypeError: 'sentinel2_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_4_0_Sentinel2_inventory.py:112](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `NotADirectoryError: Sentinel-2 source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_4_0_Sentinel2_inventory.py:123](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `ValueError: Missing Dawn Chorus ID column in Sentinel-2 score CSV. Tried {[candidate for candidate in candidates if candidate]}. Available columns: {columns}` | `Ausgabe in resolve_score_id_column` | [Step_4_0_Sentinel2_inventory.py:166](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `FileNotFoundError: Sentinel-2 score CSV not found: {score_csv}` | `not score_csv.is_file()` | [Step_4_0_Sentinel2_inventory.py:184](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `ValueError: Missing required columns in Sentinel-2 score CSV: {sorted(missing_columns)}. Available columns: {df.columns.tolist()}` | `missing_columns` | [Step_4_0_Sentinel2_inventory.py:198](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `KeyError: Missing sentinel2_download section in config.` | `'sentinel2_download' not in config` | [Step_4_1_Sentinel2_download.py:48](../../scripts/Step_4_1_Sentinel2_download.py) |
| `KeyError: No ID column found in Sentinel-2 metadata CSV: {metadata_csv}` | `id_column is None` | [Step_4_1_Sentinel2_download.py:133](../../scripts/Step_4_1_Sentinel2_download.py) |
| `TimeoutError: Completed GEE exports not visible in Drive folder {folder_id}: {sample}` | `time.monotonic() >= deadline` | [Step_4_1_Sentinel2_download.py:192](../../scripts/Step_4_1_Sentinel2_download.py) |
| `RuntimeError: Google Drive credentials/token missing or interactive auth disabled` | `service is None` | [Step_4_1_Sentinel2_download.py:442](../../scripts/Step_4_1_Sentinel2_download.py) |
| `RuntimeError: --score-only requires sentinel2_download.gee_drive_export_enabled=true` | `args.score_only` | [Step_4_1_Sentinel2_download.py:500](../../scripts/Step_4_1_Sentinel2_download.py) |
| `KeyError: Missing sentinel2_cleaning section in config.` | `'sentinel2_cleaning' not in config` | [Step_4_2_clean_sentinel2.py:20](../../scripts/Step_4_2_clean_sentinel2.py) |
| `KeyError: No Dawn Chorus ID column found in {path}` | `id_column is None` | [sentinel2_gee.py:78](../../scripts/sentinel2_gee.py) |
| `KeyError: Metadata must contain lat and lon/lng columns: {path}` | `'lat' not in frame or not ('lon' in frame or 'lng' in frame)` | [sentinel2_gee.py:80](../../scripts/sentinel2_gee.py) |
| `KeyError: Metadata must contain datetime or datetime_utc: {path}` | `datetime_column is None` | [sentinel2_gee.py:86](../../scripts/sentinel2_gee.py) |
| `KeyError: Score file must contain an ID column and score: {path}` | `column is None or 'score' not in frame` | [sentinel2_gee.py:153](../../scripts/sentinel2_gee.py) |
| `KeyError: Incoming score rows must contain DC_id` | `'DC_id' not in update` | [sentinel2_gee.py:198](../../scripts/sentinel2_gee.py) |
| `requests.HTTPError: Earth Engine HTTP {response.status_code}` | `response.status_code in {429, 500, 502, 503, 504}` | [sentinel2_gee.py:332](../../scripts/sentinel2_gee.py) |
| `RuntimeError: GEE download failed for {target.name}: {last_error}` | `Ausgabe in _download_image` | [sentinel2_gee.py:342](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE service-account key not found: {key_path}` | `not key_path.is_file()` | [sentinel2_gee.py:379](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: No GEE service-account key configured and stored Earth Engine credentials are unavailable` | `except Exception` | [sentinel2_gee.py:390](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: No user OAuth token configured for legacy Earth Engine Drive exports` | `not token_value` | [sentinel2_gee.py:402](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token not found: {token_path}` | `not token_path.is_file()` | [sentinel2_gee.py:407](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Cannot read GEE export OAuth token: {token_path}` | `except (OSError, json.JSONDecodeError)` | [sentinel2_gee.py:414](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Invalid GEE export OAuth token: {token_path}` | `not isinstance(token_payload, dict)` | [sentinel2_gee.py:416](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token lacks required scopes: {missing}` | `granted and (not required_scopes.issubset(granted))` | [sentinel2_gee.py:440](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token has no refresh token` | `not credentials.refresh_token` | [sentinel2_gee.py:443](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored_chunk` | [sentinel2_gee.py:491](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: earthengine-api is not installed` | `except ImportError` | [sentinel2_gee.py:584](../../scripts/sentinel2_gee.py) |
| `TimeoutError: Timed out waiting for legacy Sentinel-2 Drive exports (queued={len(queue)}, active={len(running)})` | `time.monotonic() >= export_deadline` | [sentinel2_gee.py:733](../../scripts/sentinel2_gee.py) |
| `RuntimeError: {failed} legacy Sentinel-2 Drive export task(s) failed` | `failed` | [sentinel2_gee.py:757](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Direct GEE raster download is disabled until parity with the legacy export is verified` | `not bool(settings.get('gee_direct_download_verified', False))` | [sentinel2_gee.py:773](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: earthengine-api is not installed` | `except ImportError` | [sentinel2_gee.py:779](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored_chunk` | [sentinel2_gee.py:796](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored` | [sentinel2_gee.py:806](../../scripts/sentinel2_gee.py) |
| `RuntimeError: {failed} Sentinel-2 GEE tile downloads failed` | `failed` | [sentinel2_gee.py:857](../../scripts/sentinel2_gee.py) |
| `FileNotFoundError: {label} missing: {path}` | `not path.is_file()` | [sentinel_credentials_preflight.py:16](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: {label} is not valid JSON: {path}` | `except Exception` | [sentinel_credentials_preflight.py:20](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: {label} must contain a JSON object: {path}` | `not isinstance(value, dict)` | [sentinel_credentials_preflight.py:22](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Missing Sentinel credential setting: {setting}` | `not value` | [sentinel_credentials_preflight.py:35](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE service-account key has the wrong structure` | `service_key.get('type') != 'service_account' or not service_key.get('client_email')` | [sentinel_credentials_preflight.py:84](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE user export token has no refresh_token` | `not export_token.get('refresh_token')` | [sentinel_credentials_preflight.py:88](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE user export token lacks Earth Engine or Drive scope` | `export_scopes and (not required_export_scopes.issubset(export_scopes))` | [sentinel_credentials_preflight.py:95](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Drive OAuth client has the wrong structure` | `not any((key in drive_credentials for key in ('installed', 'web')))` | [sentinel_credentials_preflight.py:101](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Drive read-only token has no refresh_token` | `not drive_token.get('refresh_token')` | [sentinel_credentials_preflight.py:104](../../tools/sentinel_credentials_preflight.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `Ausgabe in main` | [Step_4_0_Sentinel2_inventory.py:1235](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `1` | `except Exception` | [Step_4_0_Sentinel2_inventory.py:1242](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `0` | `acquisition_mode in {'auto', 'gee_direct'}` | [Step_4_1_Sentinel2_download.py:370](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `args.score_only` | [Step_4_1_Sentinel2_download.py:489](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `Ausgabe in main` | [Step_4_1_Sentinel2_download.py:670](../../scripts/Step_4_1_Sentinel2_download.py) |
| `1` | `except Exception` | [Step_4_1_Sentinel2_download.py:680](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `Ausgabe in main` | [Step_4_2_clean_sentinel2.py:86](../../scripts/Step_4_2_clean_sentinel2.py) |
| `1` | `except Exception` | [Step_4_2_clean_sentinel2.py:89](../../scripts/Step_4_2_clean_sentinel2.py) |
| `0` | `not bool(settings.get('gee_drive_export_enabled', False))` | [sentinel_credentials_preflight.py:55](../../tools/sentinel_credentials_preflight.py) |
| `0` | `Ausgabe in main` | [sentinel_credentials_preflight.py:112](../../tools/sentinel_credentials_preflight.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

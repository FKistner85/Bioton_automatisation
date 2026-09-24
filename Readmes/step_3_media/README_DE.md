# Step 3 Media Inventory And Download (DE)

## Zweck
Prueft und ergaenzt Audio- und Bilddateien.

## Script
`scripts/Step_3_0_a_audio_inventory.py, Step_3_0_b_photo_inventory.py, Step_3_1_a_audio_download.py, Step_3_1_b_photo_download.py`

## Eingaben
- `PointData/SoundRecordings`
- `PointData/Images_SoundRecordings`
- `PointData/dawn-chorus-soundscape.csv`

## Outputs
- `outputs/step_3_0_*/*`
- `outputs/step_3_1_*/*`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_3_0_audio_inventory`, `step_3_0_photo_inventory`, `step_3_1_audio_download`, `step_3_1_photo_download`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `audio_inventory`, `photo_inventory`, `audio_download`, `photo_download`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_3_0_a_audio_inventory.py --config config.horeka.json`
- `python scripts/Step_3_0_b_photo_inventory.py --config config.horeka.json`
- `python scripts/Step_3_1_a_audio_download.py --config config.horeka.json`
- `python scripts/Step_3_1_b_photo_download.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Inventare und Retry-Logs verhindern doppelte Downloads.

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
| `WinError 53` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 64` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 121` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 995` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 1203` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_a_audio_inventory.py:90](../../scripts/Step_3_0_a_audio_inventory.py) |
| `no_audio_stream_found` | Kein Audiostream in der Datei gefunden. | [Step_3_0_a_audio_inventory.py:216](../../scripts/Step_3_0_a_audio_inventory.py) |
| `multiple_audio_streams:{len(audio_streams)}` | Datei enthaelt mehrere Audiostreams. | [Step_3_0_a_audio_inventory.py:236](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_or_missing_sample_rate` | Samplingrate fehlt oder ist nicht positiv. | [Step_3_0_a_audio_inventory.py:273](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_or_missing_channel_count` | Audiokanalzahl fehlt oder ist nicht positiv. | [Step_3_0_a_audio_inventory.py:276](../../scripts/Step_3_0_a_audio_inventory.py) |
| `no_audio_frames_decoded` | Decoder lieferte keine Audioframes. | [Step_3_0_a_audio_inventory.py:301](../../scripts/Step_3_0_a_audio_inventory.py) |
| `duration_unavailable` | Audiodauer konnte nicht bestimmt werden. | [Step_3_0_a_audio_inventory.py:316](../../scripts/Step_3_0_a_audio_inventory.py) |
| `invalid_duration:{duration}` | Ermittelte Audiodauer ist nicht positiv. | [Step_3_0_a_audio_inventory.py:319](../../scripts/Step_3_0_a_audio_inventory.py) |
| `pyav_decode_failed:{type(exc).__name__}:{exc}` | PyAV konnte Audio nicht vollstaendig decodieren. | [Step_3_0_a_audio_inventory.py:325](../../scripts/Step_3_0_a_audio_inventory.py) |
| `filename_does_not_match_<id>_audio_pattern` | Audio-Dateiname entspricht nicht dem erwarteten ID-Muster. | [Step_3_0_a_audio_inventory.py:359](../../scripts/Step_3_0_a_audio_inventory.py) |
| `source_stat_failed:{type(exc).__name__}:{exc}` | Quelldatei konnte nicht per Dateisystem-Stat abgefragt werden. | [Step_3_0_a_audio_inventory.py:367](../../scripts/Step_3_0_a_audio_inventory.py) |
| `empty_file` | Vorhandene Datei hat null Bytes. | [Step_3_0_a_audio_inventory.py:397](../../scripts/Step_3_0_a_audio_inventory.py) |
| `duration_not_{target}s:observed={duration}s,allowed={target - tolerance}-{target + tolerance}s` | Audiodauer liegt ausserhalb Zielwert plus/minus Toleranz; Werte stehen im Code. | [Step_3_0_a_audio_inventory.py:414](../../scripts/Step_3_0_a_audio_inventory.py) |
| `WinError 53` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 64` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 121` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 995` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `WinError 1203` | Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen. | [Step_3_0_b_photo_inventory.py:46](../../scripts/Step_3_0_b_photo_inventory.py) |
| `filename_does_not_match_<id>_photo_pattern` | Foto-Dateiname entspricht nicht dem erwarteten ID-Muster. | [Step_3_0_b_photo_inventory.py:139](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_failed:{type(exc).__name__}:{exc}` | Dateikopie ist fehlgeschlagen. | [Step_3_0_b_photo_inventory.py:158](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_size_mismatch` | Dateigroessen von Quelle und Kopie stimmen nicht ueberein. | [Step_3_0_b_photo_inventory.py:165](../../scripts/Step_3_0_b_photo_inventory.py) |
| `copy_verification_failed:{type(exc).__name__}:{exc}` | Die Kontrolle nach dem Kopieren ist fehlgeschlagen. | [Step_3_0_b_photo_inventory.py:167](../../scripts/Step_3_0_b_photo_inventory.py) |
| `destination_missing_after_copy` | Zieldatei fehlt nach dem Kopierversuch. | [Step_3_0_b_photo_inventory.py:169](../../scripts/Step_3_0_b_photo_inventory.py) |
| `image_verify_failed:{type(exc).__name__}:{exc}` | Pillow-Dateipruefung fehlgeschlagen. | [Step_3_0_b_photo_inventory.py:189](../../scripts/Step_3_0_b_photo_inventory.py) |
| `pixel_load_failed:{type(exc).__name__}:{exc}` | Bildheader lesbar, aber Pixel konnten nicht geladen werden. | [Step_3_0_b_photo_inventory.py:197](../../scripts/Step_3_0_b_photo_inventory.py) |
| `invalid_dimensions:{width}x{height}` | Raster-/Bildbreite oder -hoehe ist ungueltig. | [Step_3_0_b_photo_inventory.py:200](../../scripts/Step_3_0_b_photo_inventory.py) |
| `no_audio_stream_found` | Kein Audiostream in der Datei gefunden. | [Step_3_1_a_audio_download.py:170](../../scripts/Step_3_1_a_audio_download.py) |
| `multiple_audio_streams:{len(streams)}` | Datei enthaelt mehrere Audiostreams. | [Step_3_1_a_audio_download.py:187](../../scripts/Step_3_1_a_audio_download.py) |
| `duration_unavailable` | Audiodauer konnte nicht bestimmt werden. | [Step_3_1_a_audio_download.py:230](../../scripts/Step_3_1_a_audio_download.py) |
| `no_audio_frames_decoded` | Decoder lieferte keine Audioframes. | [Step_3_1_a_audio_download.py:243](../../scripts/Step_3_1_a_audio_download.py) |
| `pyav_decode_failed:{type(exc).__name__}:{exc}` | PyAV konnte Audio nicht vollstaendig decodieren. | [Step_3_1_a_audio_download.py:257](../../scripts/Step_3_1_a_audio_download.py) |
| `HTTPError:{exc.code}:{exc.reason}` | HTTP-Download fehlgeschlagen; Suffix enthaelt Status und Servermeldung. Retry-Regeln beachten. | [Step_3_1_a_audio_download.py:328](../../scripts/Step_3_1_a_audio_download.py) |
| `{type(exc).__name__}:{exc}` | Originaler Exception-Typ und Meldung; kein eigener statischer Fehlercode. | [Step_3_1_a_audio_download.py:335](../../scripts/Step_3_1_a_audio_download.py) |
| `duration_not_{target}s:observed={duration}s,allowed={target - tolerance}-{target + tolerance}s` | Audiodauer liegt ausserhalb Zielwert plus/minus Toleranz; Werte stehen im Code. | [Step_3_1_a_audio_download.py:354](../../scripts/Step_3_1_a_audio_download.py) |
| `missing_audio_url` | Fuer den Audio-Download fehlt eine URL. | [Step_3_1_a_audio_download.py:444](../../scripts/Step_3_1_a_audio_download.py) |
| `HTTPError:{exc.code}:{exc.reason}` | HTTP-Download fehlgeschlagen; Suffix enthaelt Status und Servermeldung. Retry-Regeln beachten. | [Step_3_1_b_photo_download.py:127](../../scripts/Step_3_1_b_photo_download.py) |
| `{type(exc).__name__}:{exc}` | Originaler Exception-Typ und Meldung; kein eigener statischer Fehlercode. | [Step_3_1_b_photo_download.py:130](../../scripts/Step_3_1_b_photo_download.py) |
| `image_verify_failed:{type(exc).__name__}:{exc}` | Pillow-Dateipruefung fehlgeschlagen. | [Step_3_1_b_photo_download.py:149](../../scripts/Step_3_1_b_photo_download.py) |
| `pixel_load_failed:{type(exc).__name__}:{exc}` | Bildheader lesbar, aber Pixel konnten nicht geladen werden. | [Step_3_1_b_photo_download.py:157](../../scripts/Step_3_1_b_photo_download.py) |
| `missing_photo_url` | Fuer den Foto-Download fehlt eine URL. | [Step_3_1_b_photo_download.py:203](../../scripts/Step_3_1_b_photo_download.py) |

### Statuswerte (nicht alle sind Fehler)

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_3_0_a_audio_inventory.py:115](../../scripts/Step_3_0_a_audio_inventory.py) |
| `TypeError: 'audio_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_3_0_a_audio_inventory.py:123](../../scripts/Step_3_0_a_audio_inventory.py) |
| `NotADirectoryError: Audio source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_3_0_a_audio_inventory.py:131](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ConnectionError: LSDF transport failed while listing {path}: {exc}` | `is_transport_error(exc)` | [Step_3_0_a_audio_inventory.py:150](../../scripts/Step_3_0_a_audio_inventory.py) |
| `FileNotFoundError: Dawn Chorus metadata CSV not found: {metadata_csv}` | `not metadata_csv.is_file()` | [Step_3_0_a_audio_inventory.py:170](../../scripts/Step_3_0_a_audio_inventory.py) |
| `KeyError: Missing metadata columns in {metadata_csv}: {sorted(missing)}` | `missing` | [Step_3_0_a_audio_inventory.py:177](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ValueError: target_duration_seconds must be greater than zero.` | `target <= 0` | [Step_3_0_a_audio_inventory.py:634](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ValueError: duration_tolerance_seconds must not be negative.` | `tolerance < 0` | [Step_3_0_a_audio_inventory.py:639](../../scripts/Step_3_0_a_audio_inventory.py) |
| `ConnectionError: Audio inventory stopped because the LSDF transport failed ({len(transport_rows)} files in the current validation block). Sample: {sample}` | `transport_rows` | [Step_3_0_a_audio_inventory.py:786](../../scripts/Step_3_0_a_audio_inventory.py) |
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_3_0_b_photo_inventory.py:58](../../scripts/Step_3_0_b_photo_inventory.py) |
| `TypeError: 'photo_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_3_0_b_photo_inventory.py:63](../../scripts/Step_3_0_b_photo_inventory.py) |
| `NotADirectoryError: Photo source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_3_0_b_photo_inventory.py:69](../../scripts/Step_3_0_b_photo_inventory.py) |
| `FileNotFoundError: Dawn Chorus metadata CSV not found: {metadata_csv}` | `not metadata_csv.is_file()` | [Step_3_0_b_photo_inventory.py:96](../../scripts/Step_3_0_b_photo_inventory.py) |
| `KeyError: Missing metadata columns in {metadata_csv}: {sorted(missing)}` | `missing` | [Step_3_0_b_photo_inventory.py:103](../../scripts/Step_3_0_b_photo_inventory.py) |
| `NotADirectoryError: Photo {label} directory not found: {raw}` | `not create_if_missing` | [Step_3_0_b_photo_inventory.py:122](../../scripts/Step_3_0_b_photo_inventory.py) |
| `ConnectionError: Photo inventory stopped because the LSDF transport failed. Affected rows: {len(transport_rows)}; sample: {transport_rows[0].get('issues', '')}` | `transport_rows` | [Step_3_0_b_photo_inventory.py:375](../../scripts/Step_3_0_b_photo_inventory.py) |
| `TypeError: 'audio_download' must be an object.` | `not isinstance(section, dict)` | [Step_3_1_a_audio_download.py:97](../../scripts/Step_3_1_a_audio_download.py) |
| `OSError: Downloaded file is empty.` | `temporary.stat().st_size == 0` | [Step_3_1_a_audio_download.py:321](../../scripts/Step_3_1_a_audio_download.py) |
| `OSError: Downloaded file is empty.` | `temporary.stat().st_size == 0` | [Step_3_1_b_photo_download.py:122](../../scripts/Step_3_1_b_photo_download.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `args.list_only` | [Step_3_0_a_audio_inventory.py:684](../../scripts/Step_3_0_a_audio_inventory.py) |
| `0` | `Ausgabe in main` | [Step_3_0_a_audio_inventory.py:966](../../scripts/Step_3_0_a_audio_inventory.py) |
| `1` | `except Exception` | [Step_3_0_a_audio_inventory.py:973](../../scripts/Step_3_0_a_audio_inventory.py) |
| `0` | `args.list_only` | [Step_3_0_b_photo_inventory.py:331](../../scripts/Step_3_0_b_photo_inventory.py) |
| `0` | `Ausgabe in main` | [Step_3_0_b_photo_inventory.py:423](../../scripts/Step_3_0_b_photo_inventory.py) |
| `1` | `except Exception` | [Step_3_0_b_photo_inventory.py:426](../../scripts/Step_3_0_b_photo_inventory.py) |
| `0` | `Ausgabe in main` | [Step_3_1_a_audio_download.py:901](../../scripts/Step_3_1_a_audio_download.py) |
| `1` | `except Exception` | [Step_3_1_a_audio_download.py:908](../../scripts/Step_3_1_a_audio_download.py) |
| `0` | `Ausgabe in main` | [Step_3_1_b_photo_download.py:430](../../scripts/Step_3_1_b_photo_download.py) |
| `1` | `except Exception` | [Step_3_1_b_photo_download.py:433](../../scripts/Step_3_1_b_photo_download.py) |
| `1` | `failures or not image_source_usable or (not image_output_usable)` | [step3_path_preflight.py:153](../../tools/step3_path_preflight.py) |
| `0` | `Ausgabe in main` | [step3_path_preflight.py:156](../../tools/step3_path_preflight.py) |
| `1` | `except Exception` | [step3_path_preflight.py:159](../../tools/step3_path_preflight.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

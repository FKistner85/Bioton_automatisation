# Step 2_0 LRT Cleaning (DE)

## Zweck
Bereinigt LRT-Polygone, normalisiert Codes, Status und Formation.

## Script
`scripts/Step_2_0_clean_lrts.py`

## Eingaben
- `Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_<suffix>.gpkg`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`
- `outputs/step_2_variants/<suffix>/step_2_0/state.json`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_2_0_lrt_cleaning`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `lrt_cleaning`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_0_clean_lrts.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
State/Fingerprints entscheiden, ob ein Rebuild noetig ist.

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

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `conservation_status` | `Ausgabe in module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `Conservation_status` | `Ausgabe in module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `CONSERVATION_STATUS` | `Ausgabe in module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `conservationstatus` | `Ausgabe in module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |
| `ConservationStatus` | `Ausgabe in module` | [Step_2_0_clean_lrts.py:34](../../scripts/Step_2_0_clean_lrts.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_0_clean_lrts.py:52](../../scripts/Step_2_0_clean_lrts.py) |
| `KeyError: Missing 'lrt_cleaning' section in config.json.` | `not isinstance(section, dict)` | [Step_2_0_clean_lrts.py:59](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: 'lrt_cleaning.source_gpkgs' must be a non-empty list.` | `not isinstance(section['source_gpkgs'], list) or not section['source_gpkgs']` | [Step_2_0_clean_lrts.py:69](../../scripts/Step_2_0_clean_lrts.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_0_clean_lrts.py:76](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: Required column '{canonical}' not found in {source}. Available columns: {list(gdf.columns)}` | `found is None` | [Step_2_0_clean_lrts.py:133](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: No layers found in {gpkg_path}` | `not layers` | [Step_2_0_clean_lrts.py:163](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: Layer has no CRS: {gpkg_path.name}:{layer_name}` | `layer.crs is None` | [Step_2_0_clean_lrts.py:186](../../scripts/Step_2_0_clean_lrts.py) |
| `ValueError: No usable LRT layers found in {gpkg_path}` | `not prepared` | [Step_2_0_clean_lrts.py:203](../../scripts/Step_2_0_clean_lrts.py) |
| `RuntimeError: No formation group was processed successfully.` | `not results` | [Step_2_0_clean_lrts.py:369](../../scripts/Step_2_0_clean_lrts.py) |
| `RuntimeError: Atomic GPKG validation failed: expected {len(output)} rows, found {written_rows}.` | `written_rows != len(output)` | [Step_2_0_clean_lrts.py:536](../../scripts/Step_2_0_clean_lrts.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `should_skip(output_gpkg, state_file, expected_state, args.force)` | [Step_2_0_clean_lrts.py:469](../../scripts/Step_2_0_clean_lrts.py) |
| `0` | `Ausgabe in main` | [Step_2_0_clean_lrts.py:549](../../scripts/Step_2_0_clean_lrts.py) |
| `1` | `except Exception` | [Step_2_0_clean_lrts.py:553](../../scripts/Step_2_0_clean_lrts.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

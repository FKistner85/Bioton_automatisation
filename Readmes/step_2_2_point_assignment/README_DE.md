# Step 2_2 Point Assignment (DE)

## Zweck
Ordnet jeden Dawn-Chorus-Punkt der INSPIRE-100m-Gridzelle und LRT-Polygonen zu.
Die Grid-ID wird auch ohne Majority Formation ausgegeben; eine vorhandene
Majority Formation bleibt ein separates Attribut.

## Script
`scripts/Step_2_2_assign_points_to_lrt_grid.py`

## Eingaben
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `outputs/step_2_variants/<suffix>/step_2_1/LRT_Grid_Majority_<suffix>.csv`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_2/DawnChorus_LRT_Grid_Assignment_<suffix>.csv`
- `outputs/step_2_variants/<suffix>/step_2_2/DawnChorus_LRT_Polygon_Matches_<suffix>.csv`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_2_2_point_assignment`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `point_lrt_assignment`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_2_assign_points_to_lrt_grid.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Bei unveraenderten Spatial Inputs werden nur neue IDs verarbeitet.

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
| `processed` | `Ausgabe in build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:505](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `missing_coordinates` | `Ausgabe in build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:506](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `outside_majority_grid` | `Ausgabe in build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:510](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `inside_majority_grid_outside_lrt` | `Ausgabe in build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:515](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `inside_lrt_polygon` | `Ausgabe in build_outputs` | [Step_2_2_assign_points_to_lrt_grid.py:520](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_2_assign_points_to_lrt_grid.py:56](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `KeyError: Missing 'point_lrt_assignment' section in config.json.` | `not isinstance(section, dict)` | [Step_2_2_assign_points_to_lrt_grid.py:63](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_2_assign_points_to_lrt_grid.py:91](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: Grid ID column '{grid_id_column}' not found. Available columns: {list(grid.columns)}` | `grid_id_column not in grid.columns` | [Step_2_2_assign_points_to_lrt_grid.py:189](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: The INSPIRE grid contains no cells.` | `grid.empty` | [Step_2_2_assign_points_to_lrt_grid.py:203](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: The cleaned LRT layer has no CRS.` | `lrt.crs is None` | [Step_2_2_assign_points_to_lrt_grid.py:239](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `KeyError: No dawn_chorus_id/id column in {path}` | `Ausgabe in read_ids_file` | [Step_2_2_assign_points_to_lrt_grid.py:545](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `not target_ids` | [Step_2_2_assign_points_to_lrt_grid.py:694](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `0` | `Ausgabe in main` | [Step_2_2_assign_points_to_lrt_grid.py:786](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |
| `1` | `except Exception` | [Step_2_2_assign_points_to_lrt_grid.py:790](../../scripts/Step_2_2_assign_points_to_lrt_grid.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

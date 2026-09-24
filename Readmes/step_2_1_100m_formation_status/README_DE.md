# Step 2_1 100m Formation Status (DE)

## Zweck
Verschneidet LRTs mit dem 100m-Grid und erzeugt Majority- und Formation-Status-Produkte.

## Script
`scripts/Step_2_1_merge_lrts_and_grid.py`

## Eingaben
- `InspireGrid/Vector_Data/grid.gpkg`
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_1/*`
- `outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/*`

Die Susi-kompatible Matrix speichert alle Formation- und LRT-Anteile als
ganzzahlige Prozentwerte mit Faktor 100 (`10000 = 100 Prozent`). Formation-
Totalsummen enthalten A/B/C/K. Der Majority-Status wird nur aus A/B/C
bestimmt; `majority_disputed` bedeutet `majority_delta <= 200` und damit
maximal zwei Prozentpunkte Abstand.

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_2_1_100m_formation`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `lrt_grid_merge`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_1_merge_lrts_and_grid.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Chunk-Checkpoints und State-Datei ermoeglichen Wiederaufnahme.

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
| `majority_formation_status` | `Ausgabe in build_summary` | [Step_2_1_merge_lrts_and_grid.py:584](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `RuntimeError: Temporary GeoPackage is empty: {temporary}` | `not temporary.is_file() or temporary.stat().st_size == 0` | [Step_2_1_merge_lrts_and_grid.py:67](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_1_merge_lrts_and_grid.py:73](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `KeyError: Missing 'lrt_grid_merge' section in config.json.` | `not isinstance(section, dict)` | [Step_2_1_merge_lrts_and_grid.py:80](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_1_merge_lrts_and_grid.py:95](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Grid ID column '{grid_id_column}' not found. Available columns: {list(grid.columns)}` | `grid_id_column not in grid.columns` | [Step_2_1_merge_lrts_and_grid.py:161](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Grid and LRT data must both have a CRS.` | `grid.crs is None or lrt.crs is None` | [Step_2_1_merge_lrts_and_grid.py:182](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `RuntimeError: Step 2_1 worker was not initialised.` | `_WORKER_GRID is None or _WORKER_LRT is None or _WORKER_GRID_ID is None` | [Step_2_1_merge_lrts_and_grid.py:211](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `RuntimeError: No intersections found between grid and LRT.` | `not parts` | [Step_2_1_merge_lrts_and_grid.py:446](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `ValueError: Could not derive 100 m coordinates from grid_id. Examples: {bad}` | `ids.isna().any(axis=None)` | [Step_2_1_merge_lrts_and_grid.py:772](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `should_skip(output_paths, state_file, expected_state, args.force)` | [Step_2_1_merge_lrts_and_grid.py:1196](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `0` | `Ausgabe in main` | [Step_2_1_merge_lrts_and_grid.py:1271](../../scripts/Step_2_1_merge_lrts_and_grid.py) |
| `1` | `except Exception` | [Step_2_1_merge_lrts_and_grid.py:1275](../../scripts/Step_2_1_merge_lrts_and_grid.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

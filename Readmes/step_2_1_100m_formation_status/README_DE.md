# Step 2_1 100m Formation Status (DE)

## Zweck
Verschneidet LRTs mit dem 100m-Grid und erzeugt Majority- und Formation-Status-Produkte.

## Script
`scripts/Step_2_1_merge_lrts_and_grid.py`

## Eingaben
- `InspireGrid/Vector_Data/grid.gpkg`
- `outputs/step_2_0/lrt.gpkg`

## Outputs
- `outputs/step_2_1/*`
- `outputs/step_2_1_susi_compatible/*`

Die Susi-kompatible Matrix speichert alle Formation- und LRT-Anteile als
ganzzahlige Prozentwerte mit Faktor 100 (`10000 = 100 Prozent`). Formation-
Totalsummen enthalten A/B/C/K. Der Majority-Status wird nur aus A/B/C
bestimmt; `majority_disputed` bedeutet `majority_delta <= 200` und damit
maximal zwei Prozentpunkte Abstand.

## Abhaengigkeiten und Invalidierung
Die verbindlichen Abhaengigkeiten, der Scope und die Invalidierungsregeln stehen in `pipeline_steps.json` unter `step_2_1_100m_formation`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `lrt_grid_merge`. Pfade, Workerzahlen und fachliche Schwellen werden nicht im Slurm-Script dupliziert.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den regulaeren inkrementellen DAG; `bash slurm_from_scratch.sh` startet oder setzt eine Vollgeneration fort. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_1_merge_lrts_and_grid.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Chunk-Checkpoints und State-Datei ermoeglichen Wiederaufnahme.

## Qualitaetskontrolle
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Statuswerte stehen in `schemas/status_model.json`.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

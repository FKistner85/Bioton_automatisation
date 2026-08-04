# Step 2_4 10m Formation Status (DE)

## Zweck
Erzeugt checkpointfaehige 10m-Formation-Status-Produkte.

## Script
`scripts/Step_2_4_generate_10m_formation_status_products.py`

## Eingaben
- `outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet`
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`

Es wird kein separates originales INSPIRE-10m-Grid eingelesen. Wie in Susis
`3_10mgrid_prep.py` werden die 100 10m-Zellen je 100m-INSPIRE-ID in EPSG:3035
deterministisch abgeleitet: `x0=E100*100`, `y0=N100*100`, anschliessend
`grid_id_10=10mN(N100*10+dy)E(E100*10+dx)` fuer `dx,dy=0..9`.

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_4_susi_10m/*`

## Abhaengigkeiten und Invalidierung
Die verbindlichen Abhaengigkeiten, der Scope und die Invalidierungsregeln stehen in `pipeline_steps.json` unter `step_2_4_10m_formation`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `susi_10m_products`. Pfade, Workerzahlen und fachliche Schwellen werden nicht im Slurm-Script dupliziert.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den regulaeren inkrementellen DAG; `bash slurm_from_scratch.sh` startet oder setzt eine Vollgeneration fort. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_4_generate_10m_formation_status_products.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Parquet-Parts und _batch_status erlauben Wiederaufnahme nach Timeout.

## Qualitaetskontrolle
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Statuswerte stehen in `schemas/status_model.json`.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

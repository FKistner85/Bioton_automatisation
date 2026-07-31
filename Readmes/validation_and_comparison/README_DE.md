# Validation And Formation-Status Comparison (DE)

## Zweck
Vergleicht Formation-Status-Produkte und erzeugt finalen Validierungsreport.

## Script
`tools/compare_formation_status_products.py, tools/final_validation_report.py`

## Eingaben
- `outputs/step_2_*`
- `optional legacy/reference formation-status files`

## Outputs
- `outputs/step_8_susi_compatibility/*`
- `outputs/step_9_validation/*`

## Abhaengigkeiten und Invalidierung
Die verbindlichen Abhaengigkeiten, der Scope und die Invalidierungsregeln stehen in `pipeline_steps.json` unter `step_7_0_master_table`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `master_table`, `final_validation`, `susi_sanity_check`. Pfade, Workerzahlen und fachliche Schwellen werden nicht im Slurm-Script dupliziert.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den regulaeren inkrementellen DAG; `bash slurm_from_scratch.sh` startet oder setzt eine Vollgeneration fort. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python tools/compare_formation_status_products.py --config config.horeka.json`
- `python tools/final_validation_report.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Reports werden pro Lauf neu geschrieben; Inputs bleiben unveraendert.

## Qualitaetskontrolle
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Statuswerte stehen in `schemas/status_model.json`.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

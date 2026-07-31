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
Die verbindlichen Abhaengigkeiten, der Scope und die Invalidierungsregeln stehen in `pipeline_steps.json` unter `step_5_1_weather_inventory`, `step_5_2_weather_download`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `weather_inventory`, `weather_download`. Pfade, Workerzahlen und fachliche Schwellen werden nicht im Slurm-Script dupliziert.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den regulaeren inkrementellen DAG; `bash slurm_from_scratch.sh` startet oder setzt eine Vollgeneration fort. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
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
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Statuswerte stehen in `schemas/status_model.json`.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

# Bio-O-Ton Pipeline auf HoreKa

Dieser Ordner ist das ausfuehrbare HoreKa-Paket. Quelldaten und Downloadziele
liegen auf LSDF; generierte Analyse-, Status- und QC-Produkte liegen unter
`Data_automatisation_skripts/outputs`.

Die vollstaendige deutsche Schrittuebersicht steht in
[`PIPELINE_SCHRITTE_DE.md`](PIPELINE_SCHRITTE_DE.md). Detaildokumentation in
Deutsch und Englisch steht unter [`Readmes/`](Readmes/README_INDEX.md).

## Standardstart

Es gibt genau vier regulaere Slurm-Einstiege:

```bash
bash slurm_functionality_test.sh
bash slurm_add_new_ids.sh
bash slurm_from_scratch.sh
bash slurm_compare_formation_status.sh
```

Alle vier rufen `submit_bio_o_ton_horeka.sh` auf.

| Einstieg | Zweck |
|---|---|
| `slurm_functionality_test.sh` | Schneller Import-, Config-, Schema-, Syntax- und Regressionstest ohne grosse LSDF-Scans |
| `slurm_add_new_ids.sh` | Regulaerer Lauf fuer neue, geaenderte oder zuvor problematische IDs |
| `slurm_from_scratch.sh` | Logischer Vollauf aller Kernschritte; Originaldownloads werden nicht geloescht |
| `slurm_compare_formation_status.sh` | Vergleich der eigenen Formation-Produkte mit Referenzprodukten |

Optional kann fuer einen Checkpoint-Test jede Slurm-Laufzeit auf 30 Minuten
begrenzt werden:

```bash
BIOOTON_PIPELINE_TIME_OVERRIDE=00:30:00 bash slurm_add_new_ids.sh
```

## Python-Umgebung

```bash
bash bootstrap_env.sh
```

Der Bootstrap verwendet nach Moeglichkeit `micromamba`, `mamba` oder `conda`
und faellt sonst auf `python3 -m venv` zurueck. Standardpfad ist `.venv`.

Ein vorhandener Interpreter kann explizit gesetzt werden:

```bash
export PYTHON=/pfad/zum/python
```

## Run-Plan und Sperre

Vor jedem Datenlauf wird ein gemeinsamer `workflow_run_id` erzeugt. Der Planer
vergleicht die Dawn-Chorus-Quelldaten, per-Domaene-Fingerprints, Step-States und
die letzte Mastertabelle. Er schreibt:

```text
outputs/step_0_control/run_plans/<workflow_run_id>/run_plan.json
outputs/step_0_control/run_plans/<workflow_run_id>/metadata_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/point_assignment_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/audio_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/photo_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/sentinel_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/weather_ids.csv
```

Ein unterbrochener Vollauf wird zusaetzlich als Generation protokolliert:

```text
outputs/step_0_control/full_rebuild/current.json
outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json
```

Ein neuer `from_scratch`-Submit derselben unvollstaendigen Generation reiht
nur Steps ohne Erfolgsmarker erneut ein.

Eine atomare Pipeline-Sperre verhindert zwei gleichzeitig schreibende
Gesamtlaeufe. Sie bleibt bis nach dem Validierungsjob aktiv:

```bash
PYTHON="$(bash bootstrap_env.sh | tail -n 1)"
$PYTHON tools/pipeline_lock.py --config config.horeka.json status
```

Nur nach Kontrolle von `squeue` und `sacct` darf eine verwaiste Sperre manuell
entfernt werden:

```bash
$PYTHON tools/pipeline_lock.py --config config.horeka.json release --force
```

## Inkrementelle Regeln

Step 1 speichert fuer jede ID getrennte Fingerprints fuer Metadaten, Audio-URL,
Foto-URL, Wetterparameter und Sentinel-relevante Koordinaten. Dadurch werden
nicht nur neue IDs, sondern auch Aenderungen bestehender IDs erkannt.

Wichtige Regeln:

```text
Zeit/GPS geaendert   -> Step 1, Punktzuordnung und Punktwetter neu
Audio-URL geaendert  -> Audio-Retry wird zurueckgesetzt und die ID neu geladen
Foto-URL geaendert   -> Foto-Retry wird zurueckgesetzt und die ID neu geladen
LRT-Quelle geaendert -> Step 2_0 bis zu allen abhaengigen Gridprodukten neu
Grid geaendert       -> Step 2_1 bis zu allen abhaengigen Gridprodukten neu
Drive-TIF geaendert  -> Sentinel-Datei anhand Drive-Metadaten neu gespiegelt
alter QC-Fehler      -> beim naechsten Lauf erneut geprueft
alter QC-Erfolg      -> nur bei unveraenderter Groesse/mtime/Quelle wiederverwendet
```

`from_scratch` loescht keine Quelldateien und keine Originaldownloads. Der Lauf
erzwingt eine logische Neuberechnung. Bei Step 5_4 werden pro Vollgeneration
nur einmal die Tile-Statusdateien invalidiert. Der persistente Status
`in_progress` setzt auch nach einem neuen Slurm-Submit an den neu geschriebenen
Tile-Checkpoints fort.

## Checkpoints

```text
Step 2_1: Overlay-Chunk-Checkpoints
Step 2_4: 10m-Parquet-Chunks und Batch-Status
Step 3_1: persistente Retry-CSVs und atomare Downloads
Step 4_1: Drive-Metadatenlog und Batch-Status
Step 5_1: Wiederverwendung unveraenderter fehlerfreier Wetter-QC-Zeilen
Step 5_2: dynamisches Slurm-Array fuer grosse ID-Mengen; per-ID-Status,
          vorhandene fehlerfreie weather_<id>.csv und abschliessender Verify-Job
Step 5_3: vorhandene Monats-NetCDFs
Step 5_4: Slurm-Array pro Variable/Jahr; per Tile gespeicherte Statusdateien
Step 5_5: Wiederverwendung unveraenderter fehlerfreier Raster-QC-Zeilen
```

Slurm-Abhaengigkeiten verwenden `afterany`. Dadurch bleiben keine
`DependencyNeverSatisfied`-Jobs liegen. Ein Folgejob kann bei fehlendem Input
schnell fehlschlagen; der Master- und Validierungsjob laufen trotzdem und
dokumentieren den Gesamtzustand.

Die Mastertabelle wird nicht nur am Workflow-Ende geschrieben: Nach
Metadaten, Gridzuordnung/Gridprodukten, Medien, Sentinel, Wetter und
Bioakustik wird jeweils ein serieller Teilupdate-Job eingereiht. Bei
inkrementellen Schritten ersetzt er nur die IDs aus dem jeweiligen Run-Plan;
unbetroffene Masterzeilen bleiben erhalten. Globale Grid- oder Rasteraenderungen
aktualisieren bewusst den gesamten Masterbestand.

## Formation-Skalierung

Die Susi-kompatiblen 100-m- und 10-m-Parquets verwenden dieselbe Darstellung:
alle Formation- und LRT-Anteile (`<Formation>`, `<Formation>_A/B/C/K`,
`<LRT>_A/B/C/K`) sind ganzzahlige Prozentwerte mit Skalierungsfaktor 100.
`10000` bedeutet damit 100 Prozent. Formation-Totalwerte enthalten A/B/C/K;
`majority_formation_status` wird innerhalb der Majority Formation nur aus
A/B/C bestimmt. `majority_disputed` ist wahr bei `majority_delta <= 200`, also
bei maximal zwei Prozentpunkten Abstand.

## Fortschritt und Batch-Updates

Lange ID-basierte Steps schreiben nach jedem dauerhaft gespeicherten Batch ein
`progress.json` im jeweiligen `outputs/<step>/`-Ordner. Es enthaelt
abgeschlossene/ausstehende Batches, Durchsatz, verstrichene Zeit und ETA.
Audio- und Foto-Downloads aktualisieren die Mastertabelle zusaetzlich nach
je 250 IDs; Punktwetter nach je 500 IDs. Die Werte stehen als
`master_update_batch_size` in `config.horeka.json` und koennen auf `0` gesetzt
werden, um Zwischenupdates abzuschalten. Bioakustik schreibt ETA je
Modell-Shard; die Mastertable wird erst nach der fachlich aussagekraeftigen
Step-6-QC aktualisiert.

## Manifeste und Logs

Jeder Slurm-Step schreibt mindestens ein zentrales Manifest:

```text
outputs/step_0_manifests/<step_name>/<step_run_id>.json
```

Es enthaelt Workflow- und Step-Run-ID, Status, Laufzeit, Slurm-Kontext,
Python-/Paketversionen, Inputfingerprints, Parameter, Logpfade und Ergebnis.
Batch-Statusdateien liegen in den jeweiligen Step-Unterordnern.

Slurm-Ausgaben:

```text
outputs/step_0_slurm_logs/<UTC-Zeitstempel>_<job_name>_<job_id>.out
outputs/step_0_slurm_logs/<UTC-Zeitstempel>_<job_name>_<job_id>.err
```

Alle Jobs eines orchestrierten Laufs tragen denselben UTC-Zeitstempel im
Format `YYYYMMDDTHHMMSSZ`. Array-Jobs tragen zusaetzlich
`<array_job_id>_<array_task_id>`. Logdateien ohne Zeitstempel stammen aus
aelteren Submission-Skriptversionen und sind nicht mit neuen Laeufen zu
verwechseln.

## Downloadquellen und Ziele

Nur diese fachlichen Downloads werden ausserhalb von `outputs` geschrieben:

| Produkt | Quelle | Ziel |
|---|---|---|
| Audio | URL-Spalte `audio` der Dawn-Chorus-Tabelle | `PointData/SoundRecordings/<id>_audio.<ext>` |
| Foto | URL-Spalte `photo` der Dawn-Chorus-Tabelle | `PointData/Images_SoundRecordings/<id>_photo.<ext>` |
| Sentinel-2 | konfigurierte Google-Drive-Folder-ID | `PointData/S2/<Drive-Dateiname>.tif` |
| Punktwetter | DWD Open Data HOSTRADA | `PointData/Weather/Hostrada/weather_<id>.csv` |

Sentinel Step 4_1 wird bei jedem Gesamtworkflow eingereiht. Fehlen ein
verwendbares `token.json` und nichtinteraktive Credentials, dokumentiert der
Step den Status `skipped`; Step 4_0 inventarisiert danach den vorhandenen
LSDF-Bestand. Drive-Dateien werden mit `id`, `md5Checksum`, `modifiedTime` und
`size` abgeglichen, damit Remote-Aenderungen erkannt werden.

## HOSTRADA Raster

Step 5.3 bis 5.5 sind Teil des Haupt-DAG:

```text
Step 5.3: DWD-Monats-NetCDFs spiegeln
Step 5.4: vollstaendige Variable/Jahr-Kombinationen als Slurm-Array in 100m-Tiles umrechnen
Step 5.5: alle Variablen rekursiv inventarisieren und qualitaetspruefen
```

Manuelle Einzelstarts bleiben moeglich:

```bash
bash run_hostrada_raster_year.sh Ta 2017
bash run_hostrada_raster_quality_check.sh
```

Der Hauptworkflow verwendet fuer Step 5.4 standardmaessig zwei parallele
Array-Tasks mit je 8 CPUs und 32 GB RAM. Bei knappen Clusterressourcen kann
die Parallelitaet reduziert werden, ohne die Berechnungslogik zu veraendern:

```bash
BIOOTON_STEP54_MAX_CONCURRENT_TASKS=1 bash slurm_add_new_ids.sh
```

## Bioakustik

Step 6 erzeugt mit Bacpipe segmentweise Embeddings und Artenvorhersagen fuer
technisch valide Audios. Die CPU-Inferenz ist nach Modell und Shard
parallelisiert und schreibt nach jedem Batch einen Resume-Checkpoint. Eine GPU
ist optional und wird nicht vorausgesetzt.

Einmalig oder nach einer Aenderung der Bacpipe-Version:

```bash
bash bootstrap_bacpipe_env.sh
```

Konfiguration, Modelle, Outputs und fachliche Grenzen stehen unter
[`Readmes/step_6_bioacoustics/README_DE.md`](Readmes/step_6_bioacoustics/README_DE.md).

## Mastertabelle und Freigabe

Step 7 schreibt:

```text
Bio_O_Ton_Mastertable.csv
Bio_O_Ton_Mastertable.parquet
Bio_O_Ton_Mastertable_summary.json
outputs/step_0_control/status_events.csv
```

Die Spalten sind in [`MASTER_TABLE_README.md`](MASTER_TABLE_README.md)
definiert. Statusereignisse protokollieren neue, geloeschte und fachlich
geaenderte IDs. Automatische technische Validierung und manuelle Freigabe sind
getrennt; `automatic_release` ist standardmaessig `false`.

Der Abschlussbericht liegt unter:

```text
outputs/step_9_validation/final_validation_<timestamp>.json
outputs/step_9_validation/final_validation_<timestamp>.md
```

Er betrachtet nur Manifeste des aktuellen Workflow-Runs und prueft Pflicht-
Artefakte sowie die konfigurierten Mastertable-Readiness-Regeln.

## Visuelle Reports

Nach der finalen Validierung erzeugt der Workflow statische HTML-Reports unter:

```text
outputs/step_9_visual_reports/index.html
```

Die Uebersicht verlinkt auf eigene Seiten fuer Step 1 bis 7. Sie zeigt nur
kompakte, fachlich relevante Kennzahlen: Metadatenstatus, Formation- und
Dispute-Verteilungen, Medien-/Sentinel-/Wetterprobleme, Raster-QC,
Bioakustik-Abdeckung und Mastertable-Readiness. Bei noch laufenden oder
fehlenden Schritten wird dies sichtbar markiert; der Report selbst bricht nicht
ab.

Der Report kann bei Bedarf auch ausserhalb eines Slurm-Laufs erneuert werden:

```bash
.venv/bin/python tools/generate_pipeline_visual_reports.py --config config.horeka.json
```

Die geplante Git-Ablage und das Update auf Horeka sind in
[`GITHUB_WORKFLOW.md`](GITHUB_WORKFLOW.md) beschrieben. Die bestehende
Verzeichnisstruktur bleibt dabei unveraendert.

## Tests und Schemas

```bash
bash run_tests.sh
```

Der Funktionalitaetsjob fuehrt alle `tests/test_*.py` aus. Abgedeckt sind unter
anderem geaenderte IDs, Step-1-Upserts, Locks, Checkpoints, Wetter-Resume,
Formation-Skalierung, Mastertable-Statushistorie und Medienselektion.

Formale JSON Schemas Draft 2020-12 liegen unter `schemas/`. Die zentrale
Step-Registry liegt in `pipeline_steps.json`.

## Ressourcen

Die Defaults sind fuer die beobachtete `cpuonly`-Partition mit bis zu 152 CPUs
pro Node konservativ auf 16 CPUs fuer I/O- und Geo-Schritte begrenzt. HTTP-
Downloads verwenden `SLURM_CPUS_PER_TASK` und die jeweiligen `max_workers`-
Grenzen aus `config.horeka.json`. Mehr CPUs sollten erst nach Kontrolle von
HTTP-Fehlern, RAM und LSDF-I/O vergeben werden.

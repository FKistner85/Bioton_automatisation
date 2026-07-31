# Bio-O-Ton Pipeline: Schritte, Dateien und Abhaengigkeiten

Diese Datei beschreibt den durch `submit_bio_o_ton_horeka.sh` orchestrierten
HoreKa-Lauf. Alle Pfade stammen aus `config.horeka.json`.

## Speicherregeln

Generierte Analyse-, Inventar-, Status- und QC-Dateien:

```text
/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/<step>
```

Ausnahmen sind die finalen Mastertable-Dateien direkt im Pipeline-Ordner und
die fachlichen Downloads:

```text
Audio      -> PointData/SoundRecordings
Fotos      -> PointData/Images_SoundRecordings
Sentinel-2 -> PointData/S2
Punktwetter-> PointData/Weather/Hostrada
```

## Pipeline-Steuerung

### Run-Plan

Tool: `tools/plan_pipeline_run.py`

Inputs:

```text
PointData/dawn-chorus-soundscape.csv
outputs/step_1_metadata/metadata_source_fingerprints.csv
Bio_O_Ton_Mastertable.csv
State-Dateien der globalen LRT/Grid-Schritte
```

Outputs:

```text
outputs/step_0_control/run_plans/<run_id>/run_plan.json
outputs/step_0_control/run_plans/<run_id>/*_ids.csv
outputs/step_0_control/full_rebuild/current.json
outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json
```

Der Plan unterscheidet neue, geaenderte, geloeschte und bisher problematische
IDs. Globale LRT/Grid-Schritte laufen nur bei geaenderten Inputs, fehlenden
Outputs oder im Modus `from_scratch`. Ein unterbrochener Vollauf submitiert nur
Steps ohne Erfolgsmarker erneut.

### Pipeline-Lock

Tool: `tools/pipeline_lock.py`

Output:

```text
outputs/step_0_control/pipeline.lock/owner.json
```

Der Lock verhindert parallele Gesamtlaeufe. Der letzte Slurm-Job entfernt ihn
nach dem Validierungsjob.

## Step 1: Metadaten und Quellfingerprints

Skript: `scripts/Step_1_metadata_extraction.py`

Input:

```text
PointData/dawn-chorus-soundscape.csv
```

Output:

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_1_metadata/dawnchorus_metadata_log.csv
outputs/step_1_metadata/metadata_source_fingerprints.csv
```

Der Step bereinigt ID, Zeitstempel und GPS. Er fuehrt atomare, ID-basierte
Upserts aus und speichert getrennte Fingerprints fuer Metadaten, Audio, Foto,
Wetter und Sentinel. Aenderungen bestehender IDs werden damit erkannt.

Abhaengig: Step 2_2, Step 3_1, Step 4, Step 5.1/5.2 und Step 6.

## Step 2_0: LRT-Bereinigung und Formation

Skript: `scripts/Step_2_0_clean_lrts.py`

Inputs:

```text
Biodiversity_data/Bundeslander/*.gpkg
```

Outputs:

```text
outputs/step_2_0/lrt.gpkg
outputs/step_2_0/state.json
```

Der Step normalisiert LRT-Polygone, Status und Formation. Das finale GPKG wird
zuerst als Part-Datei geschrieben, gelesen/gezaehlt und danach atomar ersetzt.

Abhaengig: Step 2_1, Step 2_2 und Step 2_4.

## Step 2_1: 100m Formation-Status

Skript: `scripts/Step_2_1_merge_lrts_and_grid.py`

Inputs:

```text
InspireGrid/Vector_Data/grid.gpkg
outputs/step_2_0/lrt.gpkg
```

Kernoutputs:

```text
outputs/step_2_1/LRT_Grid_Majority.csv
outputs/step_2_1/majority_formation_grid.gpkg
outputs/step_2_1/majority_formation_grid.parquet
outputs/step_2_1/state.json
```

Vergleichbare Formation-Status-Matrix:

```text
outputs/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet
outputs/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.csv
outputs/step_2_1_susi_compatible/Formation_Status_Grid.csv
outputs/step_2_1_susi_compatible/ix.csv
```

Der Overlay laeuft in Chunks. Flaechenanteile werden als Centi-Prozent
gespeichert (`10000 = 100.00%`). `majority_disputed` gilt bei
`majority_delta <= 200`.

Abhaengig: Step 2_2, Step 2_3 und Step 2_4.

## Step 2_2: Recording-Punkte zu 100m Grid/LRT

Skript: `scripts/Step_2_2_assign_points_to_lrt_grid.py`

Inputs:

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_2_0/lrt.gpkg
outputs/step_2_1/LRT_Grid_Majority.csv
InspireGrid/Vector_Data/grid.gpkg
```

Outputs:

```text
outputs/step_2_2/DawnChorus_LRT_Grid_Assignment.csv
outputs/step_2_2/DawnChorus_LRT_Polygon_Matches.csv
outputs/step_2_2/point_processing_log.csv
outputs/step_2_2/state.json
```

Nur IDs mit geaenderten Koordinaten beziehungsweise durch Step 2_1
invalidierte IDs werden ersetzt. Die drei CSVs werden atomar per ID aktualisiert.

Abhaengig: Step 6.

## Step 2_3: Groebere Grid-Aggregationen

Skript: `scripts/Step_2_3_generate_remaining_grid_products.py`

Input:

```text
outputs/step_2_1/majority_formation_grid.parquet
```

Outputs:

```text
outputs/step_2_3/*1km*
outputs/step_2_3/*5km*
outputs/step_2_3/*10km*
outputs/step_2_3/state.json
```

Abhaengig: Abschlussvalidierung.

## Step 2_4: 10m Formation-Status

Skript: `scripts/Step_2_4_generate_10m_formation_status_products.py`

Inputs:

```text
outputs/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet
outputs/step_2_0/lrt.gpkg
```

Outputs:

```text
outputs/step_2_4_susi_10m/grid10m_chunks/*.gpkg
outputs/step_2_4_susi_10m/ix_chunks/*.csv
outputs/step_2_4_susi_10m/parquet_10/*.parquet
outputs/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode.parquet
outputs/step_2_4_susi_10m/state.json
```

Die 100m- und 10m-Matrizen verwenden dieselbe Spalten-, Skalierungs- und
Majority-Logik. Chunks werden nur bei geaenderten LRT/100m-Inputs invalidiert.

Abhaengig: Step 6.

## Step 2_5/2_6: Oeffentliche Referenzprodukte

Skripte:

```text
scripts/Step_2_5_clean_public_lrts.py
scripts/Step_2_6_merge_public_lrts_and_grid.py
```

Diese optionale Vergleichsroute wird mit `run_public_lrt_products.sh`
gestartet. Sie ist nicht Teil des regulaeren ID-Laufs.

## Step 3_0_a: Audio-Inventar

Skript: `scripts/Step_3_0_a_audio_inventory.py`

Input: `PointData/SoundRecordings/*`

Outputs:

```text
outputs/step_3_0_a_audio_inventory/audio_inventory_detailed.csv
outputs/step_3_0_a_audio_inventory/audio_inventory_compact.csv
outputs/step_3_0_a_audio_inventory/state.json
```

Prueft Dateiname, Container, Codec, Decodebarkeit, Sample-Rate, Kanaele und
Aufnahmedauer. Fehlerfreie unveraenderte Dateien koennen wiederverwendet werden;
Fehler werden erneut geprueft.

## Step 3_0_b: Foto-Inventar

Skript: `scripts/Step_3_0_b_photo_inventory.py`

Input: `PointData/Images_SoundRecordings/*`

Outputs:

```text
outputs/step_3_0_b_photo_inventory/photo_inventory_detailed.csv
outputs/step_3_0_b_photo_inventory/photo_inventory_compact.csv
outputs/step_3_0_b_photo_inventory/state.json
```

Prueft Namensschema, Lesbarkeit, Pixeldekodierung, Format und Dimensionen.

## Step 3_1_a/3_1_b: Medien-Downloads

Skripte:

```text
scripts/Step_3_1_a_audio_download.py
scripts/Step_3_1_b_photo_download.py
```

Downloadquellen:

```text
Spalten audio und photo aus dawn-chorus-soundscape.csv
```

Downloadziele:

```text
PointData/SoundRecordings/<id>_audio.<ext>
PointData/Images_SoundRecordings/<id>_photo.<ext>
```

Status:

```text
outputs/step_3_1_a_audio_download/audio_download_retry_log.csv
outputs/step_3_1_b_photo_download/photo_download_retry_log.csv
```

Downloads sind parallel, atomar und wiederaufnehmbar. Eine geaenderte URL setzt
den Retry-Zaehler der betroffenen ID zurueck.

## Step 4_1: Sentinel-2 Drive-Mirror

Skript: `scripts/Step_4_1_Sentinel2_download.py`

Quelle: konfigurierte Google-Drive-Folder-ID.

Ziel und Status:

```text
PointData/S2/<Drive-Dateiname>.tif
outputs/step_4_1_sentinel2_download/download_log.csv
outputs/step_4_1_sentinel2_download/_file_status/*.json
```

Remote-Dateien werden anhand Drive-ID, MD5, Aenderungszeit und Groesse
abgeglichen. Ohne verwendbare nichtinteraktive Authentifizierung wird der Step
als `skipped` dokumentiert.

## Step 4_0: Sentinel-2 Inventar

Skript: `scripts/Step_4_0_Sentinel2_inventory.py`

Inputs:

```text
PointData/S2/*
PointData/S2_Scores.csv
```

Outputs:

```text
outputs/step_4_0_Sentinel2_inventory/sentinel2_inventory_detailed.csv
outputs/step_4_0_Sentinel2_inventory/sentinel2_inventory_compact.csv
outputs/step_4_0_Sentinel2_inventory/state.json
```

Abhaengig: Step 6.

## Step 5_1: Punktwetter-Inventar

Skript: `scripts/Step_5_1_Weather_inventory.py`

Inputs:

```text
PointData/Weather/Hostrada/weather_<id>.csv
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
```

Outputs:

```text
outputs/step_5_1_weather_inventory/weather_inventory_detailed.csv
outputs/step_5_1_weather_inventory/weather_inventory_compact.csv
outputs/step_5_1_weather_inventory/state.json
```

Prueft pro CSV Zeilenzahl, Pflichtspalten, Zeitfenster, Stundenintervall,
fehlende Werte und Wertebereiche. Unveraenderte fehlerfreie Dateien werden
anhand Groesse, mtime und erwartetem Zeitfenster wiederverwendet. Step 5.1
laeuft vor und nach Step 5.2.

## Step 5_2: Punktwetter erzeugen

Skript: `scripts/Step_5_2_download_weather_data.py`

Inputs:

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_5_1_weather_inventory/weather_inventory_compact.csv
DWD Open Data HOSTRADA
```

Downloads und Status:

```text
PointData/Weather/Hostrada/weather_<id>.csv
outputs/step_5_2_weather_download/hostrada_cache/*
outputs/step_5_2_weather_download/run_log.txt
PointData/Weather/Hostrada/_recording_status/<id>.json
```

Neue, geaenderte und problematische IDs werden verarbeitet. Zeit- oder
GPS-Aenderungen erzwingen die Neuberechnung auch bei zuvor fehlerfreier CSV.
Grosse ID-Mengen werden auf bis zu acht deterministische Slurm-Array-Shards
verteilt, von denen standardmaessig vier parallel laufen. Gemeinsame
Monatsdownloads sind per Lock geschuetzt. Ein abschliessender Verify-Job prueft
die Vollstaendigkeit aller angeforderten Wetter-CSVs.

## Step 5_3: HOSTRADA Monats-NetCDF

Skript: `scripts/Step_5_3_download_hostrada_monthly.py`

Quelle: DWD Open Data HOSTRADA fuer sechs Variablen.

Outputs:

```text
outputs/step_5_3_hostrada_monthly_download/netcdf/<Variable>/*.nc
outputs/step_5_3_hostrada_monthly_download/download_log.csv
```

Vorhandene nichtleere Monatsdateien werden uebersprungen.

## Step 5_4: HOSTRADA 100m Raster

Orchestrator: `tools/run_hostrada_raster_all.py`

Worker: `scripts/Step_5_4_prepare_hostrada_rasters.py`

Input: vollstaendige Variable/Jahr-Gruppen aus Step 5.3.

Outputs:

```text
outputs/step_5_4_hostrada_raster_products/Hostrada_<Variable>/*.tif
outputs/step_5_4_hostrada_raster_products/Hostrada_<Variable>/_tile_status/<year>/*.json
outputs/step_5_4_hostrada_raster_products/Hostrada_<Variable>/_force_state/<Variable>_<year>.json
```

Bei `from_scratch` werden die Statusdateien pro Generation einmal invalidiert.
Ein persistenter `in_progress`-Status setzt auch nach einem neuen Slurm-Submit
an den neu fertiggestellten Tiles fort. Erst ein vollstaendig beendeter
Vollauf setzt die Generation auf `complete`.

## Step 5_5: HOSTRADA Raster-QC

Skript: `scripts/Step_5_5_check_hostrada_raster_products.py`

Input: alle Rastervariablen unter Step 5.4, rekursiv.

Outputs:

```text
outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.csv
outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.json
outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.md
outputs/step_5_5_hostrada_raster_quality_check/state.json
```

Unveraenderte fehlerfreie Raster werden wiederverwendet; alte Fehler oder
geaenderte Dateien werden erneut gelesen.

## Step 6: Bioakustische Embeddings und Arteninferenz

Step 6 verarbeitet nur Audiodateien, die im Post-Download-Inventar von
Step 3_0_a technisch validiert wurden. Die Inferenz laeuft als
Modell-mal-Shard-Slurm-Array auf GPU-Knoten und setzt nach einem Timeout am
letzten Batch-Checkpoint fort.

```text
Step 6_0  Bacpipe-/CUDA-/Modell-Preflight und Modellregistry
Step 6_1  ID- und modellbezogene Worklist aus validen Audios
Step 6_2  segmentweise Embeddings und native Top-k-Klassenscores
Step 6_3  einheitliches Vorhersageschema und Scorefilter
Step 6_4  Taxonomieharmonisierung, Deutschland- und Saisonplausibilitaet
Step 6_5  Aggregation pro ID und Taxon
Step 6_6  Vollstaendigkeits- und Fehler-QC pro ID und Modell
```

Wichtigste Outputs:

```text
outputs/step_6_0_bioacoustic_model_preflight/model_registry.json
outputs/step_6_1_bioacoustic_worklist/worklist.parquet
outputs/step_6_2_bioacoustic_embeddings/model=*/part-*.parquet
outputs/step_6_3_species_predictions_raw/model=*/predictions.parquet
outputs/step_6_4_species_predictions_germany/model=*/predictions.parquet
outputs/step_6_5_bioacoustic_recording_summary/recording_summary.csv
outputs/step_6_5_bioacoustic_recording_summary/recording_species.parquet
outputs/step_6_6_bioacoustic_quality_control/bioacoustic_qc_compact.csv
outputs/step_6_6_bioacoustic_quality_control/bioacoustic_qc_detailed.csv
```

Die Deutschland- und Saisonpruefung ist eine Plausibilitaetskontrolle, keine
Beobachtungsbestaetigung. Modell-Scores verschiedener Architekturen sind nicht
automatisch kalibriert oder direkt vergleichbar. Details:
`Readmes/step_6_bioacoustics/README_DE.md`.

## Step 7_0: Finale Mastertabelle

Skript: `scripts/Step_7_0_update_master_table.py`

Inputs: ID-Level-Outputs aus Step 1, 2, 3, 4, 5 und 6.

Outputs:

```text
Bio_O_Ton_Mastertable.csv
Bio_O_Ton_Mastertable.parquet
Bio_O_Ton_Mastertable_summary.json
outputs/step_0_control/status_events.csv
```

Die Mastertabelle verwendet Step 5.1 als einzige Wetter-QC-Quelle und startet
keinen zweiten Vollscan. Sie speichert kanonische Statuswerte pro Domaene,
Readiness-Flags, Issue-Codes, Quellfingerprint, Workflow-Run-ID und manuelle
Freigabefelder. Der Orchestrator aktualisiert sie fortlaufend nach jedem
relevanten Datenbereich: ID-spezifische Updates ersetzen nur die betroffenen
Zeilen, globale Formation- oder Rasteraenderungen aktualisieren den gesamten
Bestand. Die Masterupdate-Jobs werden serialisiert, damit keine Zwischenupdates
einander ueberschreiben.

## Abschlussvalidierung

Tool: `tools/final_validation_report.py`

Outputs:

```text
outputs/step_9_validation/final_validation_<timestamp>.json
outputs/step_9_validation/final_validation_<timestamp>.md
```

Geprueft werden Pflichtartefakte, nur die Manifeste des aktuellen Runs,
fehlende geplante Steps und die in `final_validation` konfigurierten
Mastertable-Readiness-Regeln. Technischer Status und manuelle Freigabe sind
getrennt.

## Abhaengigkeitsgraph

```text
Dawn Chorus CSV -> Step 1
Step 1 -> Step 2_2
Step 1 -> Step 3 Downloads
Step 1 -> Step 4 Sentinel
Step 1 -> Step 5.1/5.2

LRT sources -> Step 2_0 -> Step 2_1
Step 2_1 -> Step 2_2
Step 2_1 -> Step 2_3
Step 2_1 -> Step 2_4

Medienordner -> Step 3.0 -> Step 3.1
Drive -> Step 4.1 -> Step 4.0
Punktwetter -> Step 5.1 -> Step 5.2 -> Step 5.1 post
DWD Monatsdaten -> Step 5.3 -> Step 5.4 -> Step 5.5

valides Audio -> Step 6_0/6_1 -> Step 6_2 -> Step 6_3/6_4/6_5/6_6
Step 1/2/3/4/5/6 -> serielle Step-7-Teilupdates -> Abschlussvalidierung -> Lock-Freigabe
```

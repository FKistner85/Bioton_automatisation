# Step 7_0 - Finale Mastertabelle

## Zweck

Step 7_0 erzeugt eine kompakte Mastertabelle pro `dawn_chorus_id`. Sie fuehrt
die wichtigsten Statusinformationen aus Metadaten, 100m-/10m-Formation,
Audio, Fotos, Sentinel-2, HOSTRADA-Punktwetter und HOSTRADA-100m-Rasterstatus
zusammen.

## Input

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_1_metadata/dawnchorus_metadata_log.csv
outputs/step_2_2/DawnChorus_LRT_Grid_Assignment.csv
outputs/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode.parquet
outputs/step_3_0_a_audio_inventory/audio_inventory_*.csv
outputs/step_3_0_b_photo_inventory/photo_inventory_*.csv
outputs/step_4_0_Sentinel2_inventory/sentinel2_inventory_*.csv
outputs/step_5_1_weather_inventory/weather_inventory_compact.csv
outputs/step_5_4_hostrada_raster_products/
outputs/step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.csv
```

## Output

```text
Bio_O_Ton_Mastertable.csv
Bio_O_Ton_Mastertable.parquet
Bio_O_Ton_Mastertable_summary.json
outputs/step_0_control/status_events.csv
```

Die Output-Dateien liegen direkt im Pipeline-Ordner `bio_o_ton_pipeline`.

## Abhaengigkeiten

Der zentrale Slurm-Orchestrator reiht nach jedem relevanten Step-2-, Step-3-,
Step-4-, Step-5- und Step-6-Ergebnis einen seriellen `bio_master_*`-Job ein.
Bei ID-spezifischen Steps wird `--ids-file` verwendet: Nur diese Zeilen werden
ersetzt, alle anderen bestehenden Masterzeilen bleiben erhalten. Nach globalen
Grid- oder Rasterprodukten erfolgt ein Vollupdate. Der letzte Masterjob laeuft
vor `bio_validate`.

## Hinweise

Die Mastertabelle ersetzt nicht die Detail-Logs. Sie verdichtet nur deren
wichtigste ID-Level-Informationen. Die vollstaendige Spaltendokumentation steht
in `MASTER_TABLE_README.md`. Kanonische Domaenenstatus, Quellfingerprint,
Workflow-Run-ID und manuelle Freigabefelder werden in der Mastertabelle
gespeichert; Statusaenderungen stehen im Event-Log.

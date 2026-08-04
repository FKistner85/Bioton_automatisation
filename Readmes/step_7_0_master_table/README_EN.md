# Step 7_0 - Final Master Table

## Purpose

Step 7_0 creates a compact ID-level master table for each `dawn_chorus_id`.
It combines the most important status fields from metadata, 100m/10m formation
products, audio, photos, Sentinel-2, HOSTRADA point weather and HOSTRADA 100m
raster status.

## Input

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_1_metadata/dawnchorus_metadata_log.csv
outputs/step_2_variants/<primary_suffix>/step_2_2/DawnChorus_LRT_Grid_Assignment_<primary_suffix>.csv
outputs/step_2_variants/<primary_suffix>/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode_<primary_suffix>.parquet
outputs/Bio_O_Ton_Formation_Variants.parquet
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
Bio_O_Ton_Formation_Variants.csv
Bio_O_Ton_Formation_Variants.parquet
```

The output files are written directly below `Data_automatisation_skripts/outputs`.
Step 7_1 creates the normalized variant table; Step 7_0 reads it to add compact
coverage and completeness counts.

## Dependencies

The central Slurm orchestrator submits a serial `bio_master_*` job after each
relevant Step 2, Step 3, Step 4, Step 5 and Step 6 result. ID-specific steps
use `--ids-file`: only those rows are replaced and all other master rows are
preserved. Global grid or raster products trigger a full update. The final
master job runs before `bio_validate`.

## Notes

The master table does not replace the detailed logs. It only condenses their
most important ID-level information. Full column definitions are documented in
`MASTER_TABLE_README.md`. Canonical domain statuses, the source fingerprint,
workflow run ID and preserved manual review fields are stored in the master
table; status changes are written to the event log.

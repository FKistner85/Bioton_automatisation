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
Bio_O_Ton_Master.csv
Bio_O_Ton_Master.parquet
Bio_O_Ton_Master_summary.json
outputs/step_0_control/status_events.csv
Bio_O_Ton_Formation_Variants.csv
Bio_O_Ton_Formation_Variants.parquet
```

Die Output-Dateien liegen direkt unter `Data_automatisation_skripts/outputs`.
Step 7_1 erzeugt die normalisierte Variantentabelle; Step 7_0 liest daraus
kompakte Vollstaendigkeits- und Abdeckungszaehler.

## Abhaengigkeiten

Der zentrale Slurm-Orchestrator reiht nach jedem relevanten Step-2-, Step-3-,
Step-4-, Step-5- und Step-6-Ergebnis einen seriellen `bio_master_*`-Job ein.
Bei ID-spezifischen Steps wird `--ids-file` verwendet: Nur diese Zeilen werden
ersetzt oder bei fehlender ID in den Clean-Metadaten entfernt; alle anderen
bestehenden Masterzeilen bleiben erhalten. Ein Vollupdate uebernimmt die gesamte
aktuelle ID-Menge der Clean-Metadaten. Eine gueltige Datei nur mit Spaltenkopf
ergibt eine leere Mastertabelle; eine fehlende Datei fuehrt zum Abbruch.
Entfernte IDs werden auch bei Teillaeufen im Event-Log protokolliert. Nach globalen
Grid- oder Rasterprodukten erfolgt ein Vollupdate. Der letzte Masterjob laeuft
vor `bio_validate`.

## Hinweise

Bei jedem Masterupdate (auch direkt nach dem Metadatenlauf) werden fehlende
`grid_100m_id` aus dem vollstaendigen `point_lrt_assignment.grid_gpkg` ergaenzt,
unabhaengig von vorhandenen Formationsprodukten. Die Zuordnung verwendet
unveraendert die Projektion, `within`-Pruefung und Mehrfachtreffer-Auswahl aus
Step 2.2. `grid_10m_id` wird weiterhin mit derselben bestehenden Funktion aus
der 100-m-Elternzelle abgeleitet. Vorhandene 100-m-IDs bleiben erhalten.
Ohne gueltige Koordinaten oder ausserhalb des Referenzrasters bleibt die ID leer.
Ein konfiguriertes, nicht lesbares Raster fuehrt zum Fehler statt zu erfundenen IDs.

Eine bestehende CSV kann separat mit `tools/backfill_master_grid_ids.py`
(`--input`, `--output`, `--grid-gpkg`) ergaenzt werden. Das Werkzeug prueft,
dass vorhandene IDs und alle fachfremden Spaltenwerte unveraendert bleiben.

Die Mastertabelle ersetzt nicht die Detail-Logs. Sie verdichtet nur deren
wichtigste ID-Level-Informationen. Die vollstaendige Spaltendokumentation steht
in `MASTER_TABLE_README.md`. Kanonische Domaenenstatus, Quellfingerprint,
Workflow-Run-ID und manuelle Freigabefelder werden in der Mastertabelle
gespeichert; Statusaenderungen stehen im Event-Log.

`datetime_local` now stores the German clock without an offset (`YYYY-MM-DD HH:MM:SS`,
schema v5). UTC is derived from the aware Step-1 product before removing that offset.
A focused local refresh marks preserved weather/Sentinel results for rechecking
when their relevant recording date changes. It does not regenerate those products.

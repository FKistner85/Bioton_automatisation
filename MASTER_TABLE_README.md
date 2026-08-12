# Bio-O-Ton Mastertabelle

Diese Datei beschreibt die finale ID-Level-Mastertabelle:

```text
Bio_O_Ton_Mastertable.csv
Bio_O_Ton_Mastertable.parquet
Bio_O_Ton_Mastertable_summary.json
```

Die LRT-Sensitivitaetsanalyse schreibt zusaetzlich:

```text
Bio_O_Ton_Formation_Variants.csv
Bio_O_Ton_Formation_Variants.parquet
Bio_O_Ton_Formation_Variants_summary.json
```

Diese normalisierte Tabelle hat eine Zeile pro `dawn_chorus_id` und
`lrt_variant`. Die Haupt-Mastertabelle bleibt bei einer Zeile pro ID und nutzt
fuer ihre detaillierten Formation-Felder die konfigurierte Primaervariante
`no_K_post2017_threshold_50`.

Die Tabelle wird durch `scripts/Step_7_0_update_master_table.py` fortlaufend
aktualisiert. Der Slurm-Orchestrator reiht nach jedem relevanten Datenbereich
einen serialisierten Teilupdate ein. Mit `--ids-file` werden nur die betroffenen
IDs ersetzt; nicht betroffene bestehende Zeilen bleiben erhalten. Nach globalen
Grid- oder Rasteraenderungen wird bewusst der gesamte Bestand aktualisiert.
Sie liegt direkt im Pipeline-Ordner `bio_o_ton_pipeline`, nicht unter
`processed`. Die detaillierten Pruef- und Prozessdaten bleiben in den jeweiligen
Step-Ordnern unter `Data_automatisation_skripts/outputs`.

## Grundidee

Die Mastertabelle ist eine kompakte Uebersicht pro `dawn_chorus_id`.
Sie soll schnell zeigen, ob ein Recording fuer allgemeine Analysen,
Formation-Analysen und perspektivisch multimodale Analysen verwendbar ist.

Ausfuehrliche Detailinformationen stehen weiterhin in den Step-Produkten:

```text
Readmes/step_1_metadata/
Readmes/step_2_1_100m_formation_status/
Readmes/step_2_2_point_assignment/
Readmes/step_2_4_10m_formation_status/
Readmes/step_2_variants/
Readmes/step_3_media/
Readmes/step_4_sentinel2/
Readmes/step_5_2_weather/
Readmes/step_6_bioacoustics/
Readmes/step_7_0_master_table/
Readmes/validation_and_comparison/
```

## Quellen pro Bereich

| Bereich | Wichtigste Quelle |
|---|---|
| Metadaten/Zeit/GPS | `outputs/step_1_metadata/dawnchorus_metadata_clean.csv` und `dawnchorus_metadata_log.csv` |
| 100m-Formation | `outputs/step_2_variants/<primary_suffix>/step_2_2/DawnChorus_LRT_Grid_Assignment_<primary_suffix>.csv` |
| 10m-Formation | `outputs/step_2_variants/<primary_suffix>/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode_<primary_suffix>.parquet` |
| Formation-Varianten | `outputs/Bio_O_Ton_Formation_Variants.parquet` und CSV |
| Audio | `outputs/step_3_0_a_audio_inventory/*` und `outputs/step_3_1_a_audio_download/audio_download_retry_log.csv` |
| Fotos | `outputs/step_3_0_b_photo_inventory/*` und `outputs/step_3_1_b_photo_download/photo_download_retry_log.csv` |
| Sentinel-2 | `outputs/step_4_0_Sentinel2_inventory/*` |
| HOSTRADA Punktwetter | `outputs/step_5_1_weather_inventory/weather_inventory_compact.csv`; die Detailpruefung liegt im zugehoerigen Detailed-Log |
| HOSTRADA Raster 100m | `outputs/step_5_4_hostrada_raster_products/` und `outputs/step_5_5_hostrada_raster_quality_check/` |
| Bioakustik | `outputs/step_6_5_bioacoustic_recording_summary/*` und `outputs/step_6_6_bioacoustic_quality_control/*` |

## Spalten

| Spalte | Definition |
|---|---|
| `mastertable_schema_version` | Version des Mastertable-Schemas. |
| `workflow_run_id` | Gemeinsame ID des Slurm-Gesamtworkflows, der diese Tabellenzeile zuletzt aktualisiert hat. |
| `dawn_chorus_id` | Eindeutige Dawn-Chorus-ID. |
| `source_fingerprint` | SHA-256-Fingerprint der relevanten Dawn-Chorus-Quellfelder dieser ID. |
| `datetime_local` | Bereinigter lokaler Zeitstempel aus Step 1. |
| `datetime_utc` | Derselbe Zeitstempel nach UTC konvertiert. |
| `date_local` | Lokales Datum aus `datetime_local`. |
| `time_local` | Lokale Uhrzeit aus `datetime_local`. |
| `timestamp_source` | Quelle des bereinigten Zeitstempels, z.B. `localtimes` oder `datetime`. |
| `timestamp_changed` | `True`, wenn Step 1 den Zeitstempel normalisiert/uminterpretiert hat. |
| `timestamp_change_reason` | Kurzbeschreibung der Zeitstempel-Konvertierung aus Step 1. |
| `lat` | Breitengrad aus den bereinigten Metadaten. |
| `lon` | Laengengrad aus den bereinigten Metadaten. |
| `record_added_to_mastertable_utc` | UTC-Zeitpunkt, zu dem diese ID erstmals in der Mastertabelle geschrieben wurde. Wird bei Updates erhalten. |
| `record_updated_in_mastertable_utc` | UTC-Zeitpunkt des letzten Mastertable-Updates fuer diese Zeile. |
| `metadata_status` | Kanonischer Status fuer Zeit/GPS: `validated` oder `has_issues`. |
| `sound_exists` | Mindestens eine Audio-Datei fuer die ID wurde im Audio-Inventar gefunden. |
| `sound_has_issues` | Das Audio-Inventar oder der Download-Log meldet Probleme fuer diese ID. |
| `sound_issue_codes` | Kompakte Audio-Fehlercodes, z.B. `missing_file`, `duration_unavailable`, `sound_missing_audio_url`. |
| `sound_status` | Kanonischer Audiostatus: `validated`, `missing` oder `has_issues`. |
| `photo_exists` | Mindestens eine Foto-Datei fuer die ID wurde im Foto-Inventar gefunden. |
| `photo_has_issues` | Das Foto-Inventar oder der Download-Log meldet Probleme fuer diese ID. |
| `photo_issue_codes` | Kompakte Foto-Fehlercodes, z.B. `missing_file`, `image_verify_failed`, `photo_missing_photo_url`. |
| `photo_status` | Kanonischer Fotostatus: `validated`, `missing` oder `has_issues`. |
| `sentinel_exists` | Mindestens ein Sentinel-2 GeoTIFF fuer die ID wurde inventarisiert. |
| `sentinel_has_issues` | Sentinel-2 Inventar oder Score-Join meldet technische Probleme. Ein niedriger Score allein ist kein technisches Problem. |
| `sentinel_quality_score` | Sentinel-2 Qualitaetsscore aus `PointData/S2_Scores.csv`, sofern vorhanden. |
| `sentinel_issue_codes` | Kompakte Sentinel-Fehlercodes, z.B. `missing_file`, `quality_score_missing`, `all_pixels_nodata`. |
| `sentinel_status` | Kanonischer Sentinel-Status: `validated`, `missing` oder `has_issues`. |
| `weather_point_exists` | `weather_<id>.csv` existiert im HOSTRADA-Punktwetterordner und ist nicht leer. |
| `weather_point_has_issues` | Punktwetterdatei hat fehlende Spalten, fehlende Werte, unplausible Werte, falsche Zeilenzahl, falsches Zeitintervall oder Lesefehler. |
| `weather_point_issue_codes` | Kompakte HOSTRADA-Punktwetter-Fehlercodes, z.B. `missing_file`, `missing_value`, `unexpected_row_count`. |
| `weather_point_status` | Kanonischer Punktwetterstatus aus Step 5.1. Der Master liest die Wetterdateien nicht erneut vollstaendig ein. |
| `weather_raster_hostrada_100m_exists` | HOSTRADA-Rasterprodukte existieren im 100m-Rasteroutput. Es gibt keine 10m-Wetterrasterspalte. |
| `weather_raster_hostrada_100m_has_issues` | Globaler 100m-Rasterstatus meldet fehlende Raster, NoData-Probleme, QC-Luecken oder Strukturwarnungen. |
| `weather_raster_hostrada_100m_issue_codes` | Kompakte 100m-Raster-Fehlercodes, z.B. `missing_raster`, `qc_not_run`, `all_nodata`. |
| `grid_100m_id` | 100m-Gridzelle, der der Recording-Punkt in Step 2_2 zugeordnet wurde. |
| `grid_100m_assignment_exists` | `True`, wenn eine 100m-Grid-ID fuer den Punkt vorhanden ist. |
| `grid_100m_has_majority_formation` | `True`, wenn fuer die 100m-Zelle eine Majority Formation vorhanden ist. |
| `inside_lrt_polygon` | `True`, wenn der Recording-Punkt direkt innerhalb mindestens eines bereinigten LRT-Polygons liegt; dies ist strenger als die Grid-Zuordnung. |
| `lrt_polygon_count` | Anzahl direkter LRT-Polygon-Treffer des Recording-Punkts. |
| `lrt_code_count`, `lrt_formation_count`, `lrt_status_count`, `lrt_mapping_year_count` | Anzahl unterschiedlicher Attribute der direkt getroffenen LRT-Polygone. |
| `lrt_codes`, `lrt_formations`, `lrt_conservation_statuses`, `lrt_mapping_years` | Zusammengefasste Attribute der direkt getroffenen LRT-Polygone. |
| `majority_formation_100m` | Formation mit groesstem Flaechenanteil in der 100m-Zelle. |
| `majority_formation_status_100m` | Haeufigster Conservation Status innerhalb der 100m-Majority-Formation. |
| `majority_value_100m` | Anteil der 100m-Majority-Formation in Centi-Prozent. `10000` bedeutet 100.00 Prozent. |
| `second_value_100m` | Anteil der zweitgroessten 100m-Formation in Centi-Prozent. |
| `majority_delta_100m` | Differenz zwischen `majority_value_100m` und `second_value_100m` in Centi-Prozent. |
| `majority_disputed_100m` | `True`, wenn `majority_delta_100m <= 200`, also maximal 2 Prozentpunkte Abstand. |
| `formation_100m_status` | Kanonischer Status der 100m-Zuordnung und Majority Formation. |
| `grid_10m_id` | Aus den Koordinaten abgeleitete 10m-Grid-ID in EPSG:3035-Logik. |
| `grid_10m_assignment_exists` | `True`, wenn eine 10m-Grid-ID berechnet werden konnte. |
| `grid_10m_has_majority_formation` | `True`, wenn fuer diese 10m-Zelle eine Majority Formation im 10m-Produkt gefunden wurde. |
| `majority_formation_10m` | Formation mit groesstem Flaechenanteil in der 10m-Zelle. |
| `majority_formation_status_10m` | Haeufigster Conservation Status innerhalb der 10m-Majority-Formation. |
| `majority_value_10m` | Anteil der 10m-Majority-Formation in Centi-Prozent. |
| `second_value_10m` | Anteil der zweitgroessten 10m-Formation in Centi-Prozent. |
| `majority_delta_10m` | Differenz zwischen `majority_value_10m` und `second_value_10m` in Centi-Prozent. |
| `majority_disputed_10m` | `True`, wenn `majority_delta_10m <= 200`, also maximal 2 Prozentpunkte Abstand. |
| `formation_10m_status` | Kanonischer Status der 10m-Zuordnung und Majority Formation. |
| `formation_100m_10m_agree` | `True`, wenn die 100m- und 10m-Majority-Formation identisch sind. |
| `formation_status_100m_10m_agree` | `True`, wenn der Majority-Formation-Status in 100m und 10m identisch ist. |
| `formation_primary_variant` | Suffix des LRT-Datensatzes, dessen detaillierte Formation-Felder in dieser Hauptzeile stehen. |
| `formation_variant_count_expected` | Anzahl der im Eingangsordner erkannten LRT-Varianten. |
| `formation_variants_with_100m_majority` | Anzahl Varianten, die fuer diese ID eine 100m-Majority-Formation liefern. |
| `formation_variants_with_10m_majority` | Anzahl Varianten, die fuer diese ID eine 10m-Majority-Formation liefern. |
| `formation_variant_products_complete` | Globales Flag: 100m- und 10m-Endprodukte aller erwarteten Varianten liegen vor. |
| `bioacoustic_status` | Kanonischer Step-6-Status: `validated`, `partial`, `failed` oder `missing`. |
| `bioacoustic_has_issues` | `True`, wenn mindestens ein erforderliches Modell fehlt oder eine Modellinferenz fehlgeschlagen ist. |
| `bioacoustic_issue_codes` | Kompakte Step-6-Fehlercodes, z.B. `required_models_incomplete` oder `model_inference_failed`. |
| `bioacoustic_models_expected` | Pipe-separierte Liste der fuer die ID geplanten Bacpipe-Modelle. |
| `bioacoustic_models_complete` | Pipe-separierte Liste der fuer die ID erfolgreich abgeschlossenen Modelle. |
| `bioacoustic_required_models_complete` | `True`, wenn alle als erforderlich konfigurierten Modelle abgeschlossen sind. |
| `bioacoustic_inference_version` | Version des Step-6-Ausgabe- und Transformationsschemas. |
| `bioacoustic_species_count` | Anzahl unterschiedlicher, nicht als unplausibel markierter Taxa ueber alle Modelle. Kein bestaetigter Artnachweis. |
| `bird_species_count` | Anzahl der als Voegel gruppierten Taxa in der Aufnahmeaggregation. |
| `nonbird_species_count` | Anzahl der nicht als Voegel gruppierten Taxa in der Aufnahmeaggregation. |
| `bioacoustic_max_confidence` | Hoechster normalisierter Modellscore der Aufnahme; Scores verschiedener Modelle sind nicht zwingend direkt kalibriert. |
| `top_species_scientific` | Wissenschaftlicher Name des hoechst gerankten aggregierten Taxons. |
| `top_species_model_support` | Anzahl Modelle, die das Top-Taxon oberhalb des konfigurierten Schwellenwerts gemeldet haben. |
| `ready_for_general_analysis` | `True`, wenn ID, Zeit, Koordinaten, Audio, Punktwetter und Sentinel technisch vorhanden und ohne Issue sind. Fotos und Formation sind hier nicht blockierend. |
| `ready_for_formation_analysis_100m` | `True`, wenn `ready_for_general_analysis` gilt und eine 100m-Majority-Formation vorhanden ist. HOSTRADA-Flaechenraster blockieren diese fachliche Formation-Readiness nicht. |
| `ready_for_direct_lrt_analysis` | `True`, wenn `ready_for_general_analysis` gilt und der Recording-Punkt direkt in einem LRT-Polygon liegt. |
| `ready_for_formation_weather_raster_analysis_100m` | Optionale kombinierte Readiness aus 100m-Formation und technisch sauberen HOSTRADA-100m-Rastern. |
| `ready_for_formation_analysis_10m` | `True`, wenn `ready_for_general_analysis` gilt und eine 10m-Majority-Formation vorhanden ist. |
| `ready_for_multimodal_analysis` | `True`, wenn `ready_for_general_analysis` gilt und ein technisch unproblematisches Foto vorhanden ist. |
| `ready_for_bioacoustic_analysis` | `True`, wenn ein technisch valides Audio vorliegt, Step 6 ohne Issue abgeschlossen wurde und alle erforderlichen Modelle vollstaendig sind. Diese Flag ist bewusst unabhaengig von Wetter, Sentinel und Formation. |
| `record_blocking_issue_codes` | Zusammenfassung der wichtigsten Gruende, warum mindestens eine Ready-Flag nicht erfuellt ist. Detailursachen stehen in den Step-Logs. |
| `record_status` | Gesamtstatus der Zeile: `validated`, `partial` oder `has_issues`. |
| `release_status` | Freigabestatus. Automatisch wird hoechstens `manual_review_required` gesetzt; `approved` bleibt eine manuelle Entscheidung. |
| `manual_review_comment` | Manuell gepflegter Kommentar; wird bei automatischen Updates erhalten. |
| `manual_reviewed_by` | Manuell gepflegte Person/Kennung; wird bei automatischen Updates erhalten. |
| `manual_reviewed_utc` | Zeitpunkt der manuellen Pruefung; wird bei automatischen Updates erhalten. |

## Issue-Code-Konvention

Issue-Code-Spalten sind pipe-separierte Kurzlisten, z.B.:

```text
missing_file|missing_value|unexpected_row_count
```

Die Codes sind bewusst knapp. Detailzahlen, betroffene Dateien, HTTP-Status,
Rastermetadaten oder Decode-Fehler stehen in den jeweiligen Detail-Logs.

Statusaenderungen werden append-only protokolliert:

```text
outputs/step_0_control/status_events.csv
```

Das Log enthaelt neue und geloeschte IDs sowie Aenderungen der kanonischen
Status-, Ready- und Blocking-Issue-Felder. Ein erneuter Masterlauf mit derselben
`workflow_run_id` ersetzt die Ereignisse dieses Runs, damit Retries idempotent
bleiben.

## Ready-Flags

`ready_for_general_analysis` ist streng und setzt voraus:

```text
valider Zeitstempel
valide Koordinaten
Audio existiert und hat keine Issues
HOSTRADA Punktwetter existiert und hat keine Issues
Sentinel-2 existiert und hat keine technischen Issues
```

`ready_for_formation_analysis_100m` setzt zusaetzlich eine vorhandene
100m-Majority-Formation voraus. Die optionale Rasterwetter-Kombination wird
separat als `ready_for_formation_weather_raster_analysis_100m` ausgewiesen.
`ready_for_formation_analysis_10m` setzt eine vorhandene 10m-Majority-Formation
voraus; ein 10m-Wetterraster existiert in dieser Pipeline bewusst nicht.

`ready_for_multimodal_analysis` setzt zusaetzlich voraus, dass ein Foto
existiert und keine Foto-Issues gemeldet wurden.

`ready_for_bioacoustic_analysis` bewertet nur Audio und Bioakustik. Die
segmentweisen Embeddings, modellweisen Scores, Deutschland-/Saisonflags und
Fehlerdetails bleiben in den Step-6-Produkten. Artenvorhersagen sind
Modellergebnisse und muessen fuer fachliche Nachweise separat validiert werden.

## Ausfuehren

Direkt auf HoreKa aus dem Pipeline-Ordner:

```bash
bash run_master_table_update.sh
```

Im normalen Slurm-Lauf wird der Step automatisch nach den relevanten
Step-2-, Step-3-, Step-4-, Step-5- und Step-6-Jobs eingereiht:

```bash
bash slurm_add_new_ids.sh
bash slurm_from_scratch.sh
```

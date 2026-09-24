# Step 7_0 - Finale Mastertabelle

## Aktueller Betrieb (2026-09-23)

Der direkte Slurm-Start serialisiert Zwischenupdates. Der tmux-/Hybrid-Controller sammelt Abhaengigkeiten und schreibt einen finalen Master. In der Bioakustikphase werden ausschliesslich Bioakustikfelder und deren Readiness aktualisiert. Der Kern schreibt Schema v6 mit 104 Spalten einschliesslich fuenf unverbindlicher Naehe-/Duplikatflags. Eine Bioakustik-Aktualisierung behaelt eine vorhandene aeltere Schemaversion bei. Die vollstaendigen Regeln stehen in der Master-Referenz.


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
schema v6). UTC is derived from the aware Step-1 product before removing that offset.
A focused local refresh marks preserved weather/Sentinel results for rechecking
when their relevant recording date changes. It does not regenerate those products.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `recording_date_changed_recheck_required` | Lokales Aufnahmedatum geaendert; erhaltene Wetter-/Sentinel-Ergebnisse erneut pruefen. | [Step_7_0_update_master_table.py:460](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | Kein verwendbares kompaktes Inventar vorhanden. | [Step_7_0_update_master_table.py:517](../../scripts/Step_7_0_update_master_table.py) |
| `bioacoustic_qc_not_run` | Es liegt kein verwendbares kompaktes Bioakustik-QC vor. | [Step_7_0_update_master_table.py:615](../../scripts/Step_7_0_update_master_table.py) |
| `bioacoustic_result_missing` | Fuer diese Master-ID fehlt ein QC-Ergebnis. | [Step_7_0_update_master_table.py:651](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | Kein verwendbares kompaktes Inventar vorhanden. | [Step_7_0_update_master_table.py:709](../../scripts/Step_7_0_update_master_table.py) |
| `missing_file` | Erwartete Datei fehlt. | [Step_7_0_update_master_table.py:752](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | Kein verwendbares kompaktes Inventar vorhanden. | [Step_7_0_update_master_table.py:791](../../scripts/Step_7_0_update_master_table.py) |
| `missing_file` | Erwartete Datei fehlt. | [Step_7_0_update_master_table.py:831](../../scripts/Step_7_0_update_master_table.py) |
| `missing_raster` | Keine erwarteten HOSTRADA-Raster vorhanden. | [Step_7_0_update_master_table.py:864](../../scripts/Step_7_0_update_master_table.py) |
| `all_nodata` | Mindestens ein QC-Band besteht nur aus NoData. | [Step_7_0_update_master_table.py:871](../../scripts/Step_7_0_update_master_table.py) |
| `unexpected_shape` | QC meldet ein nicht quadratisches Raster. | [Step_7_0_update_master_table.py:873](../../scripts/Step_7_0_update_master_table.py) |
| `raster_structure_warning` | QC meldet konstante oder reine NoData-Zeilen/-Spalten. | [Step_7_0_update_master_table.py:876](../../scripts/Step_7_0_update_master_table.py) |
| `raster_qc_read_error_{type(exc).__name__}` | Raster-QC-Datei konnte nicht gelesen werden. | [Step_7_0_update_master_table.py:879](../../scripts/Step_7_0_update_master_table.py) |
| `qc_not_run` | Raster vorhanden, aber QC-Ergebnis fehlt. | [Step_7_0_update_master_table.py:881](../../scripts/Step_7_0_update_master_table.py) |
| `timestamp_missing_or_invalid` | Mindestens ein benoetigter Zeitwert im Master fehlt oder ist ungueltig. | [Step_7_0_update_master_table.py:1364](../../scripts/Step_7_0_update_master_table.py) |
| `coordinates_missing_or_invalid` | Master-Koordinaten fehlen oder liegen ausserhalb gueltiger WGS84-Grenzen. | [Step_7_0_update_master_table.py:1366](../../scripts/Step_7_0_update_master_table.py) |
| `{prefix}_missing` | Die benannte Datendomaene fehlt fuer diese Aufnahme. | [Step_7_0_update_master_table.py:1371](../../scripts/Step_7_0_update_master_table.py) |
| `{prefix}_issue` | Die benannte Datendomaene ist vorhanden, meldet aber Probleme. | [Step_7_0_update_master_table.py:1373](../../scripts/Step_7_0_update_master_table.py) |
| `grid_100m_missing_majority_formation` | Keine 100-m-Mehrheitsformation; das bedeutet nicht zwingend fehlende Grid-ID. | [Step_7_0_update_master_table.py:1375](../../scripts/Step_7_0_update_master_table.py) |
| `grid_10m_missing_majority_formation` | Keine 10-m-Mehrheitsformation; das bedeutet nicht zwingend fehlende Grid-ID. | [Step_7_0_update_master_table.py:1377](../../scripts/Step_7_0_update_master_table.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `not_started` | `compact.empty` | [Step_7_0_update_master_table.py:613](../../scripts/Step_7_0_update_master_table.py) |
| `majority_formation_status_10m` | `Ausgabe in add_10m_formation` | [Step_7_0_update_master_table.py:1164](../../scripts/Step_7_0_update_master_table.py) |
| `validated` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1288](../../scripts/Step_7_0_update_master_table.py) |
| `has_issues` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1289](../../scripts/Step_7_0_update_master_table.py) |
| `missing` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1295](../../scripts/Step_7_0_update_master_table.py) |
| `partial` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1381](../../scripts/Step_7_0_update_master_table.py) |
| `not_started` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1397](../../scripts/Step_7_0_update_master_table.py) |
| `manual_review_required` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1398](../../scripts/Step_7_0_update_master_table.py) |
| `approved` | `Ausgabe in add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1401](../../scripts/Step_7_0_update_master_table.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Step 1 clean metadata is missing or empty: {status_dir / 'dawnchorus_metadata_clean.csv'}` | `clean.empty` | [Step_7_0_update_master_table.py:306](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: Run the core pipeline first: an existing master is required.` | `previous.empty` | [Step_7_0_update_master_table.py:681](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: Expected HOSTRADA raster resolution_m=100 for the master table, got {resolution}.` | `resolution != 100` | [Step_7_0_update_master_table.py:854](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: The INSPIRE grid has no CRS.` | `not info['crs']` | [Step_7_0_update_master_table.py:953](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: FORMATION_10M_UNREADABLE: {path}` | `except Exception` | [Step_7_0_update_master_table.py:1132](../../scripts/Step_7_0_update_master_table.py) |
| `FileNotFoundError: Master update ID file not found: {args.ids_file}` | `not args.ids_file.is_file()` | [Step_7_0_update_master_table.py:1577](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: FORMATION_10M_MISSING: {ten_path}; existing master retained.` | `ten_path and (not Path(ten_path).is_file())` | [Step_7_0_update_master_table.py:1591](../../scripts/Step_7_0_update_master_table.py) |
| `ValueError: Proximity thresholds must be finite and positive` | `not all((math.isfinite(v) and v > 0 for v in (radius, seconds, cluster_radius, cluster_seconds)))` | [spatiotemporal_duplicates.py:27](../../scripts/spatiotemporal_duplicates.py) |
| `ValueError: Cluster thresholds must include duplicate thresholds` | `radius > cluster_radius or seconds > cluster_seconds` | [spatiotemporal_duplicates.py:29](../../scripts/spatiotemporal_duplicates.py) |
| `ValueError: Cluster radius cannot exceed half Earth's circumference` | `cluster_radius > math.pi * EARTH_RADIUS_M` | [spatiotemporal_duplicates.py:31](../../scripts/spatiotemporal_duplicates.py) |
| `ValueError: Proximity input must contain unique recording IDs` | `len(set(ids)) != len(ids)` | [spatiotemporal_duplicates.py:34](../../scripts/spatiotemporal_duplicates.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `execution_phase() == 'bioacoustics'` | [Step_7_0_update_master_table.py:1572](../../scripts/Step_7_0_update_master_table.py) |
| `0` | `except ValueError` | [Step_7_0_update_master_table.py:1596](../../scripts/Step_7_0_update_master_table.py) |
| `0` | `Ausgabe in main` | [Step_7_0_update_master_table.py:1702](../../scripts/Step_7_0_update_master_table.py) |
| `1` | `except Exception` | [Step_7_0_update_master_table.py:1705](../../scripts/Step_7_0_update_master_table.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->

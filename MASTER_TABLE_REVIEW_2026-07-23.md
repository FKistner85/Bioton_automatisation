# Mastertable Review

Stand: 2026-07-23

Gepruefte Datei:

```text
C:/Users/Frede/OneDrive/Documents/Bio_O_Ton_Data_Master.csv
```

## Kurzbefund

Die Tabelle hat aktuell:

```text
Zeilen: 107896
Spalten: 18
ID-Duplikate: 0
```

Aktuelle Spalten:

```text
dawn_chorus_id
datetime_local
date
time
time_source
lat
lon
localtimes_source_raw
datetime_source_raw
grid_id
in_map
in_lrt
weather_data_exists
weather_problem
sound_exist
sound_problem
photo_exist
photo_problem
```

## Auffaelligkeiten

- `dawn_chorus_id` ist eindeutig und vollstaendig.
- `datetime_local`, `time_source`, `datetime_source_raw` und `grid_id` fehlen bei jeweils 2 IDs.
- `localtimes_source_raw` fehlt bei 3290 IDs, was plausibel ist, weil diese wahrscheinlich ueber `datetime_source_raw` kommen.
- `weather_problem` ist komplett leer (`100% NaN`) und aktuell nicht informativ.
- `photo_exist` und `photo_problem` sind wegen fehlender Werte als `object` statt sauber bool/nullable bool gespeichert.
- `photo_problem` enthaelt nur `False` oder `NaN`; echte Bildprobleme werden aktuell nicht sichtbar abgebildet.
- `in_map` und `in_lrt` haben exakt dieselbe Verteilung. Das sollte fachlich geprueft werden: Entweder ist das korrekt gekoppelt, oder eine der Spalten ist redundant/irrefuehrend.
- Sentinel-2 fehlt komplett.
- LRT-/Formation-Informationen fehlen als fachliche Zielvariablen, obwohl Step 2 diese erzeugt.
- Es gibt keine explizite Spalte, ob der lokale Zeitstempel korrigiert/geaendert wurde.

## Aktuelle Abdeckung

```text
in_map True:               8582
in_lrt True:               8582
weather_data_exists True: 11025
sound_exist True:        107050
sound_problem True:         311
photo_exist True:         10843
photo_problem True:           0
```

## Empfohlenes finales Mastertable-Schema

### 1. Identitaet

```text
dawn_chorus_id
```

Pflicht, eindeutig, keine Duplikate.

### 2. Zeit

```text
datetime_local
date
time
timezone
datetime_utc
timestamp_source
timestamp_changed
timestamp_change_reason
datetime_source_raw
localtimes_source_raw
```

Empfehlung:

- `timestamp_changed`: `True/False`, ob der finale lokale Zeitstempel gegenueber dem Rohwert angepasst wurde.
- `timestamp_change_reason`: z.B. `timezone_normalized`, `localtimes_preferred`, `datetime_fallback`, `missing_raw`.
- Rohspalten koennen in der finalen Tabelle bleiben, wenn Provenienz wichtig ist; sonst in eine Diagnose-/Auditdatei auslagern.

### 3. Raum / Grid / LRT

```text
lat
lon
grid_id
in_grid
in_lrt
lrt_code
conservation_status
majority_formation
majority_formation_status
majority_value
second_value
majority_delta
majority_disputed
n_formations
n_lrts
```

Empfehlung:

- `in_map` in `in_grid` umbenennen.
- `in_lrt` klar definieren: Punkt direkt in LRT-Polygon oder Gridzelle hat LRT-Majority?
- Majority-Felder aus Step 2_1/2_2 aufnehmen, weil sie fuer Analysen zentral sind.

### 4. Audio

```text
sound_exists
sound_has_issues
sound_issue_codes
sound_path
sound_duration_seconds
sound_format
```

Empfehlung:

- Finaltable: kompakte Felder.
- Detailfelder wie Codec, Sample Rate, Decode-Details bleiben besser im Audio-Inventory.

### 5. Foto

```text
photo_exists
photo_has_issues
photo_issue_codes
photo_path
photo_width
photo_height
photo_format
```

Empfehlung:

- `photo_exist`/`photo_problem` in saubere nullable booleans umwandeln.
- Wenn `photo_exists == False`, dann `photo_has_issues` besser `NA`, nicht `False`, weil keine Datei geprueft wurde.

### 6. Sentinel-2

```text
sentinel_exists
sentinel_has_issues
sentinel_quality_score
sentinel_path
sentinel_width_px
sentinel_height_px
sentinel_band_count
sentinel_issue_codes
```

Pflicht fuer das finale Produkt, sobald Step 4 regulaer eingebunden ist.

### 7. Wetter

```text
weather_exists
weather_has_issues
weather_issue_codes
weather_path
weather_expected_rows
weather_actual_rows
weather_nan_fraction
```

Empfehlung:

- `weather_problem` ersetzen durch `weather_has_issues`.
- Wenn noch kein Weather-Inventory existiert, mindestens aus Step 5_2 `_recording_status` und CSV-Dateiexistenz ableiten.

### 8. Pipeline-/QC-Status

```text
pipeline_run_id
mastertable_created_utc
mastertable_schema_version
record_ready_for_analysis
record_blocking_issue_codes
```

Empfehlung:

- `record_ready_for_analysis` kann z.B. `True` sein, wenn Mindestanforderungen erfuellt sind:
  - valide ID
  - valide Zeit
  - valide Koordinaten/Grid
  - Audio vorhanden und ohne kritische Issues
  - optionale Medien/Wetter/Sentinel je nach Analyseziel vorhanden oder bewusst nicht erforderlich

## Spalten, die im finalen Produkt vermutlich zu technisch sind

Diese Spalten sind wichtig fuer Provenienz, aber koennten in eine separate Audit-Tabelle:

```text
localtimes_source_raw
datetime_source_raw
```

Wenn du maximale Nachvollziehbarkeit in einer einzigen Mastertable willst, koennen sie bleiben. Fuer eine saubere Analyse-Mastertable wuerde ich sie eher in `mastertable_timestamp_audit.csv` auslagern und nur `timestamp_changed` plus `timestamp_change_reason` behalten.

## Spalten, die aktuell fehlen

Prioritaet hoch:

```text
timestamp_changed
timestamp_change_reason
datetime_utc
timezone
sentinel_exists
sentinel_has_issues
sentinel_quality_score
weather_has_issues
photo_has_issues als nullable boolean
sound_has_issues als nullable boolean
majority_formation
majority_formation_status
record_ready_for_analysis
record_blocking_issue_codes
mastertable_schema_version
mastertable_created_utc
```

## Empfohlene naechste Umsetzung

Ein neuer Step sollte die finale Tabelle aus den bestehenden Step-Outputs bauen:

```text
scripts/Step_6_0_build_final_mastertable.py
```

Input:

```text
outputs/step_1_metadata/dawnchorus_metadata_clean.csv
outputs/step_2_2/DawnChorus_LRT_Grid_Assignment.csv
outputs/step_3_0_a_audio_inventory/audio_inventory_compact.csv
outputs/step_3_0_b_photo_inventory/photo_inventory_compact.csv
outputs/step_4_0_Sentinel2_inventory/sentinel2_inventory_compact.csv
outputs/step_5_2_weather_download/_recording_status/*.json
PointData/Weather/Hostrada/weather_<id>.csv
```

Output:

```text
outputs/step_6_0_final_mastertable/Bio_O_Ton_Final_Mastertable.csv
outputs/step_6_0_final_mastertable/Bio_O_Ton_Final_Mastertable.parquet
outputs/step_6_0_final_mastertable/mastertable_quality_report.md
outputs/step_6_0_final_mastertable/mastertable_quality_report.json
```

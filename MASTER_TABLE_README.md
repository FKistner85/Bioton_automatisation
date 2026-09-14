# Bio-O-Ton Master Table Reference

This reference defines the final ID-level table written by [`scripts/Step_7_0_update_master_table.py`](scripts/Step_7_0_update_master_table.py). The implementation's `MASTER_COLUMNS` list is the authoritative output order; the current version is `2026-08-04-mastertable-v4` and contains 99 columns.

## Products and row model

```text
Bio_O_Ton_Master.csv
Bio_O_Ton_Master.parquet
Bio_O_Ton_Master_summary.json
outputs/step_0_control/status_events.csv
```

The master table has exactly one row per unique `dawn_chorus_id`. The CSV and Parquet contain the same ordered columns. The summary JSON records creation/update metadata and aggregate readiness/status counts. The append-only event CSV records additions, deletions, and changes to tracked status/readiness fields.

[`schemas/master_table.schema.json`](schemas/master_table.schema.json) is the machine-readable validation schema for required/core fields and permits the writer's additional derived fields. For the complete output surface and column order, use the writer's `MASTER_COLUMNS` list and this reference.

The LRT sensitivity analysis additionally writes:

```text
Bio_O_Ton_Formation_Variants.csv
Bio_O_Ton_Formation_Variants.parquet
Bio_O_Ton_Formation_Variants_summary.json
Bio_O_Ton_Variant_Summary.csv
Bio_O_Ton_Variant_Temporal_Summary.csv
```

That normalized table contains one row per `dawn_chorus_id` and `lrt_variant`. The main master table remains one row per ID and uses the configured primary variant, currently `no_K_post2017_threshold_50`, for its detailed 100 m/10 m fields.

## Source products

| Domain | Main source consumed by Step 7.0 |
|---|---|
| Metadata/time/GPS | `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`, `dawnchorus_metadata_log.csv`, and `metadata_source_fingerprints.csv` |
| Primary 100 m formation and direct LRT hits | `outputs/step_2_variants/<primary_suffix>/step_2_2/DawnChorus_LRT_Grid_Assignment_<primary_suffix>.csv` |
| Primary 10 m formation | `outputs/step_2_variants/<primary_suffix>/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode_<primary_suffix>.parquet` |
| Formation-variant coverage | `outputs/Bio_O_Ton_Formation_Variants.parquet` and `variant_index.json` |
| Audio | Step-3 audio compact/detailed inventories and audio retry log |
| Photos | Step-3 photo compact/detailed inventories and photo retry log |
| Sentinel-2 | Step-4 compact/detailed inventory plus configured score CSV |
| HOSTRADA point weather | `outputs/step_5_1_weather_inventory/weather_inventory_compact.csv` |
| HOSTRADA 100 m rasters | Step-5.4 raster tree and Step-5.5 quality outputs |
| Bioacoustics | Step-6.5 recording summary and Step-6.6 compact QC |

The master table deliberately condenses these sources. File-level, segment-level, model-level, raster-level, and detailed failure information remains in the corresponding step outputs.

## Column definitions

### Identity and provenance

| Column | Definition |
|---|---|
| `mastertable_schema_version` | Master-table row version. Current constant: `2026-08-04-mastertable-v4`. |
| `workflow_run_id` | Shared workflow ID that most recently updated the row. Outside an orchestrated run, the writer's fallback run ID is used. |
| `dawn_chorus_id` | Unique numeric Dawn Chorus recording ID. It is normalized to a digit string and is the table's primary key. |
| `source_fingerprint` | SHA-256 fingerprint from Step 1 over the source fields relevant to the ID. It supports changed-record detection. |
| `record_added_to_mastertable_utc` | UTC time when the ID was first inserted. Preserved during later automatic updates. |
| `record_updated_in_mastertable_utc` | UTC time of the latest automatic update of this row. |

### Time and coordinates

| Column | Definition |
|---|---|
| `datetime_local` | Cleaned local recording timestamp from Step 1, including its UTC offset when available. |
| `datetime_utc` | `datetime_local` converted to UTC and formatted as `YYYY-MM-DDTHH:MM:SSZ`. |
| `date_local` | Local calendar date derived from `datetime_local`. |
| `time_local` | Local wall-clock time derived from `datetime_local`; the local offset is not applied twice. |
| `timestamp_source` | Source selected by Step 1, such as `localtimes` or `datetime`. |
| `timestamp_changed` | `True` when Step 1 normalized, converted, or reinterpreted the source timestamp. |
| `timestamp_change_reason` | Step-1 explanation of the timestamp conversion/normalization. |
| `lat` | Cleaned WGS84 latitude; valid range is -90 to 90. |
| `lon` | Cleaned WGS84 longitude; valid range is -180 to 180. |

### Status fields

Canonical domain and row statuses use values from the project status model, including `not_started`, `validated`, `missing`, `has_issues`, `partial`, `failed`, `not_applicable`, `manual_review_required`, and `approved` where applicable. The master writer derives the following status columns rather than copying arbitrary free text:

| Column | Definition |
|---|---|
| `metadata_status` | `validated` when both local/UTC timestamps and coordinates are valid; otherwise `has_issues`. |
| `sound_status` | `validated` when audio exists without issues, `missing` when absent, otherwise `has_issues`. |
| `photo_status` | `validated` when a photo exists without issues, `missing` when absent, otherwise `has_issues`. |
| `sentinel_status` | `validated` when Sentinel-2 data exists without technical issues, `missing` when absent, otherwise `has_issues`. |
| `weather_point_status` | `validated` when point weather exists without issues, `missing` when absent, otherwise `has_issues`. |
| `formation_100m_status` | `missing` without a grid assignment, `has_issues` when assigned but lacking a majority formation, otherwise `validated`. |
| `formation_10m_status` | `missing` without a derived 10 m assignment, `has_issues` when assigned but lacking a majority formation, otherwise `validated`. |
| `bioacoustic_status` | Step-6 compact QC result, normally `validated`, `partial`, `failed`, or `missing`. |

### Audio and photos

| Column | Definition |
|---|---|
| `sound_exists` | At least one audio file for the ID was found by the audio inventory. |
| `sound_has_issues` | The audio inventory or download retry log reports a problem for the ID. |
| `sound_issue_codes` | Pipe-separated compact audio causes such as `missing_file`, `duration_unavailable`, or `sound_missing_audio_url`. |
| `sound_status` | Canonical audio status; derivation is listed under [Status fields](#status-fields). |
| `photo_exists` | At least one photo file for the ID was found by the photo inventory. |
| `photo_has_issues` | The photo inventory or download retry log reports a problem for the ID. |
| `photo_issue_codes` | Pipe-separated compact photo causes such as `missing_file`, `image_verify_failed`, or `photo_missing_photo_url`. |
| `photo_status` | Canonical photo status; derivation is listed under [Status fields](#status-fields). |

### Sentinel-2

| Column | Definition |
|---|---|
| `sentinel_exists` | At least one Sentinel-2 GeoTIFF for the ID was inventoried. |
| `sentinel_has_issues` | The inventory or score join reports a technical problem. A low score alone is not a technical issue. |
| `sentinel_quality_score` | Optional quality score joined from the configured `S2_Scores.csv`. Scores are not treated as calibrated technical pass/fail thresholds by the master writer. |
| `sentinel_issue_codes` | Pipe-separated causes such as `missing_file`, `quality_score_missing`, or `all_pixels_nodata`. |
| `sentinel_status` | Canonical Sentinel-2 status; derivation is listed under [Status fields](#status-fields). |

### Weather

| Column | Definition |
|---|---|
| `weather_point_exists` | The Step-5.1 compact inventory reports a non-empty `weather_<id>.csv`. |
| `weather_point_has_issues` | Point weather has missing columns/values, implausible values, wrong row count/interval, or a read error. |
| `weather_point_issue_codes` | Pipe-separated HOSTRADA point-weather causes such as `missing_file`, `missing_value`, or `unexpected_row_count`. |
| `weather_point_status` | Canonical point-weather status; the master writer reuses Step-5.1 QC rather than rereading all weather files. |
| `weather_raster_hostrada_100m_exists` | Required products are present in the configured 100 m raster output tree. This is a global state copied to each row. |
| `weather_raster_hostrada_100m_has_issues` | Global raster state reports missing products, NoData problems, QC gaps, or structural warnings. |
| `weather_raster_hostrada_100m_issue_codes` | Pipe-separated global causes such as `missing_raster`, `qc_not_run`, or `all_nodata`. |

There is intentionally no 10 m weather-raster column. Optional 100 m weather rasters do not block `ready_for_general_analysis` or ordinary formation readiness.

### 100 m formation

| Column | Definition |
|---|---|
| `grid_100m_id` | Authoritative INSPIRE 100 m grid cell assigned to the recording point by Step 2.2, whether or not the cell has a majority formation. |
| `grid_100m_assignment_exists` | `True` when a 100 m grid ID is available. |
| `grid_100m_has_majority_formation` | `True` when the assigned cell has a majority formation. |
| `majority_formation_100m` | Formation with the largest area share in the assigned 100 m cell. |
| `majority_formation_status_100m` | Most frequent A/B/C conservation status inside the majority formation. K contributes to formation totals but is not selected as the majority formation status. |
| `majority_value_100m` | Majority-formation share in integer centi-percent; `10000` means 100.00%. |
| `second_value_100m` | Second-largest formation share in integer centi-percent. |
| `majority_delta_100m` | Difference between majority and second place in integer centi-percent. |
| `majority_disputed_100m` | `True` when `majority_delta_100m <= 200`, i.e. at most two percentage points. Null when a comparison cannot be computed. |
| `formation_100m_status` | Canonical 100 m status; derivation is listed under [Status fields](#status-fields). |

### Direct LRT intersections

These fields describe direct point-in-polygon hits against the cleaned primary LRT source. They are stricter than assignment to a grid cell whose area overlaps an LRT.

| Column | Definition |
|---|---|
| `inside_lrt_polygon` | `True` when the recording point lies in at least one cleaned LRT polygon. |
| `lrt_polygon_count` | Number of directly intersected LRT polygons. |
| `lrt_code_count` | Number of distinct LRT codes among direct hits. |
| `lrt_formation_count` | Number of distinct formation values among direct hits. |
| `lrt_status_count` | Number of distinct conservation-status values among direct hits. |
| `lrt_mapping_year_count` | Number of distinct mapping years among direct hits. |
| `lrt_codes` | Pipe-separated distinct LRT codes from direct hits. |
| `lrt_formations` | Pipe-separated distinct formations from direct hits. |
| `lrt_conservation_statuses` | Pipe-separated distinct conservation statuses from direct hits. |
| `lrt_mapping_years` | Pipe-separated distinct mapping years from direct hits. |

### 10 m formation

| Column | Definition |
|---|---|
| `grid_10m_id` | Susi-compatible 10 m identifier derived from the assigned INSPIRE 100 m ID and the point's EPSG:3035 position, whether or not the cell has a majority formation. |
| `grid_10m_assignment_exists` | `True` when a 10 m grid ID could be derived. |
| `grid_10m_has_majority_formation` | `True` when the 10 m product contains a majority formation for the derived cell. |
| `majority_formation_10m` | Formation with the largest share in the 10 m cell. |
| `majority_formation_status_10m` | Most frequent A/B/C conservation status inside the 10 m majority formation. |
| `majority_value_10m` | Majority share in integer centi-percent. |
| `second_value_10m` | Second-largest share in integer centi-percent. |
| `majority_delta_10m` | Difference between first and second place in integer centi-percent. |
| `majority_disputed_10m` | `True` when `majority_delta_10m <= 200`; null when unavailable. |
| `formation_10m_status` | Canonical 10 m status; derivation is listed under [Status fields](#status-fields). |

### Cross-resolution and variant coverage

| Column | Definition |
|---|---|
| `formation_100m_10m_agree` | `True` only when both majority formations are present and equal. |
| `formation_status_100m_10m_agree` | `True` only when both majority-formation statuses are present and equal. |
| `formation_primary_variant` | Configured LRT suffix whose detailed values populate the main master row. |
| `formation_variant_count_expected` | Variant count from `variant_index.json`; zero when the index is absent/unreadable. |
| `formation_variants_with_100m_majority` | Number of variant rows for the ID with a 100 m majority formation. |
| `formation_variants_with_10m_majority` | Number of variant rows for the ID with a 10 m majority formation. |
| `formation_variant_products_complete` | Global flag copied to every row: all expected variants have both 100 m and 10 m products, and the actual variant count equals the expected non-zero count. |

### Bioacoustics

| Column | Definition |
|---|---|
| `bioacoustic_status` | Canonical outcome from Step-6 QC. |
| `bioacoustic_has_issues` | `True` when required model coverage is incomplete or inference/QC reports failure. |
| `bioacoustic_issue_codes` | Pipe-separated causes such as `required_models_incomplete` or `model_inference_failed`. |
| `bioacoustic_models_expected` | Pipe-separated models planned for the ID. |
| `bioacoustic_models_complete` | Pipe-separated models successfully completed for the ID. |
| `bioacoustic_required_models_complete` | `True` when every model configured with `required: true` completed. |
| `bioacoustic_inference_version` | Version of the Step-6 output/inference transformation. |
| `bioacoustic_species_count` | Number of distinct, non-implausible aggregated taxa across models. This is not a confirmed species count. |
| `bird_species_count` | Number of aggregated taxa grouped as birds. |
| `nonbird_species_count` | Number of aggregated taxa not grouped as birds. |
| `bioacoustic_max_confidence` | Highest normalized score in the recording aggregation. Scores from different models are not necessarily calibrated against one another. |
| `top_species_scientific` | Scientific name of the highest-ranked aggregated taxon. |
| `top_species_model_support` | Number of models that reported the top taxon above the configured threshold. |

### Readiness flags

| Column | Exact intent |
|---|---|
| `ready_for_general_analysis` | Valid local/UTC time and coordinates; audio exists without issues; point weather exists without issues; Sentinel-2 exists without technical issues. Photos, formation, raster weather, and bioacoustics do not block it. |
| `ready_for_formation_analysis_100m` | General readiness plus a 100 m assignment and majority formation. |
| `ready_for_direct_lrt_analysis` | General readiness plus `inside_lrt_polygon = True`. |
| `ready_for_formation_weather_raster_analysis_100m` | 100 m formation readiness plus present, issue-free HOSTRADA 100 m rasters. |
| `ready_for_formation_analysis_10m` | General readiness plus a 10 m assignment and majority formation. |
| `ready_for_multimodal_analysis` | General readiness plus a present, issue-free photo. |
| `ready_for_bioacoustic_analysis` | Audio exists without issues, `bioacoustic_status = validated`, and all required bioacoustic models are complete. This flag is intentionally independent of weather, Sentinel-2, photos, and formation. |

### Issue-code and status conventions

| Column | Definition |
|---|---|
| `record_blocking_issue_codes` | Pipe-separated summary of missing/invalid time, coordinates, sound, point weather, Sentinel-2, photo, and missing 100 m/10 m majority formations. The field is a navigation aid; domain logs contain the full evidence. |

Issue-code fields use stable, lowercase, pipe-separated tokens:

```text
missing_file|missing_value|unexpected_row_count
```

When errors originate in free-text detail/retry logs, Step 7.0 normalizes them to compact tokens. File names, HTTP codes, raster statistics, decode traces, and other evidence remain in the detailed domain products.

### Record and release status

| Column | Definition |
|---|---|
| `record_status` | Starts as `partial`; becomes `validated` when general, 100 m formation, and 10 m formation readiness are all true; becomes `has_issues` when metadata is problematic and sound, point weather, and Sentinel-2 are all missing/problematic. |
| `release_status` | Automatically `not_started`, or `manual_review_required` for technically validated rows. A previously manual `approved` value is preserved. Automatic processing never creates a new approval. |
| `manual_review_comment` | Free-text manual review note preserved across automatic updates. |
| `manual_reviewed_by` | Reviewer name/identifier preserved across automatic updates. |
| `manual_reviewed_utc` | Manual review time preserved across automatic updates. |

## Incremental update behavior

The orchestrator serializes master updates. With `--ids-file`, Step 7.0 rebuilds only listed IDs, replaces those rows, and preserves every unaffected row. A run without `--ids-file` rebuilds the complete current ID set. Global grid, variant, or raster changes intentionally use a full update.

Writes are protected by a file lock on Linux and use temporary-file replacement for the CSV and JSON. The Parquet file is compressed with Zstandard and also replaced atomically when the writer succeeds. If optional Parquet writing fails, the CSV remains the canonical successful table output and the summary records no Parquet path.

The first-insertion time and manual review fields are carried forward from the previous CSV. `release_status = approved` is preserved; other technical/release fields are recalculated.

## Status event history

`outputs/step_0_control/status_events.csv` contains:

| Field | Meaning |
|---|---|
| `event_utc` | Event creation time. |
| `workflow_run_id` | Workflow that observed the change. |
| `dawn_chorus_id` | Affected ID. |
| `field` | `record_lifecycle` or a tracked status/readiness field. |
| `previous_value` | Value before the update. |
| `current_value` | Value after the update. |

Full updates record added and deleted IDs; incremental updates record additions and tracked changes but do not infer deletions outside their selected ID set. Tracked changes include canonical domain statuses, `record_status`, `release_status`, the main readiness flags, and `record_blocking_issue_codes`.

## Execution

The normal pipeline schedules Step 7.0 automatically after relevant domains and always writes a final snapshot. To rebuild it manually on HoreKa:

```bash
bash run_master_table_update.sh
```

To update only selected IDs directly:

```bash
.venv/bin/python scripts/Step_7_0_update_master_table.py \
  --config config.horeka.json \
  --ids-file /path/to/ids.csv
```

The ID file is read through the common ID-list helper and must exist. For end-to-end execution, locking, manifests, validation, and release behavior, return to the [root README](README.md#end-to-end-workflow).

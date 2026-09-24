# Step 7_0 - Final Master Table

## Current Operation (2026-09-23)

Direct Slurm submission serializes intermediate updates. The tmux/hybrid controller collects dependencies and writes one final master. The bioacoustics phase updates only bioacoustic fields and their readiness. Core writes schema v6 with 104 columns including five advisory proximity/duplicate flags. A bioacoustics-only update retains an existing older row schema. Full rules are in the master reference.


## Purpose

Step 7_0 creates a compact ID-level master table for each `dawn_chorus_id`.
It combines the most important status fields from metadata, 100m/10m formation
products, direct LRT intersections, audio, photos, Sentinel-2, HOSTRADA point
weather/raster status, bioacoustic QC, readiness, and manual release state.

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
outputs/step_6_5_bioacoustic_recording_summary/recording_summary.csv
outputs/step_6_6_bioacoustic_quality_control/bioacoustic_qc_compact.csv
```

## Output

```text
Bio_O_Ton_Master.csv
Bio_O_Ton_Master.parquet
Bio_O_Ton_Master_summary.json
outputs/step_0_control/status_events.csv
Bio_O_Ton_Formation_Variants.csv
Bio_O_Ton_Formation_Variants.parquet
Bio_O_Ton_Variant_Summary.csv
Bio_O_Ton_Variant_Temporal_Summary.csv
```

The output files are written directly below `Data_automatisation_skripts/outputs`.
Step 7_1 creates the normalized variant table; Step 7_0 reads it to add compact
coverage and completeness counts.

## Dependencies

The central Slurm orchestrator submits a serial `bio_master_*` job after each
relevant Step 2, Step 3, Step 4, Step 5 and Step 6 result. ID-specific steps
use `--ids-file`: only those rows are replaced or removed when absent from clean
metadata; all other master rows are preserved. A full update adopts the complete
current clean-metadata ID set. A valid header-only input produces an empty master;
a missing input aborts the update. Deletions are logged for partial updates too.
Global grid or raster products trigger a full update. The final
master job runs before `bio_validate`.

## Notes

The master table does not replace the detailed logs. It only condenses their
most important ID-level information. All 104 columns and their exact readiness
rules are defined in the [master-table reference](../../MASTER_TABLE_README.md).
Canonical domain statuses, the source fingerprint, workflow run ID, and
preserved manual review fields are stored in the master table; status changes
are written to the event log.

`datetime_local` now stores the German clock without an offset (`YYYY-MM-DD HH:MM:SS`,
schema v6). UTC is derived from the aware Step-1 product before removing that offset.
A focused local refresh marks preserved weather/Sentinel results for rechecking
when their relevant recording date changes. It does not regenerate those products.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `recording_date_changed_recheck_required` | Local recording date changed; recheck retained weather/Sentinel products. | [Step_7_0_update_master_table.py:460](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | No usable compact inventory is available. | [Step_7_0_update_master_table.py:517](../../scripts/Step_7_0_update_master_table.py) |
| `bioacoustic_qc_not_run` | No usable compact bioacoustic QC is available. | [Step_7_0_update_master_table.py:615](../../scripts/Step_7_0_update_master_table.py) |
| `bioacoustic_result_missing` | This master ID has no matching QC result. | [Step_7_0_update_master_table.py:651](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | No usable compact inventory is available. | [Step_7_0_update_master_table.py:709](../../scripts/Step_7_0_update_master_table.py) |
| `missing_file` | Expected file is missing. | [Step_7_0_update_master_table.py:752](../../scripts/Step_7_0_update_master_table.py) |
| `inventory_not_run` | No usable compact inventory is available. | [Step_7_0_update_master_table.py:791](../../scripts/Step_7_0_update_master_table.py) |
| `missing_file` | Expected file is missing. | [Step_7_0_update_master_table.py:831](../../scripts/Step_7_0_update_master_table.py) |
| `missing_raster` | Expected HOSTRADA rasters are absent. | [Step_7_0_update_master_table.py:864](../../scripts/Step_7_0_update_master_table.py) |
| `all_nodata` | At least one QC band contains only NoData. | [Step_7_0_update_master_table.py:871](../../scripts/Step_7_0_update_master_table.py) |
| `unexpected_shape` | QC reports a nonsquare raster. | [Step_7_0_update_master_table.py:873](../../scripts/Step_7_0_update_master_table.py) |
| `raster_structure_warning` | QC reports constant or all-NoData rows/columns. | [Step_7_0_update_master_table.py:876](../../scripts/Step_7_0_update_master_table.py) |
| `raster_qc_read_error_{type(exc).__name__}` | Raster QC file could not be read. | [Step_7_0_update_master_table.py:879](../../scripts/Step_7_0_update_master_table.py) |
| `qc_not_run` | Raster exists but QC result is missing. | [Step_7_0_update_master_table.py:881](../../scripts/Step_7_0_update_master_table.py) |
| `timestamp_missing_or_invalid` | A required master timestamp is missing or invalid. | [Step_7_0_update_master_table.py:1364](../../scripts/Step_7_0_update_master_table.py) |
| `coordinates_missing_or_invalid` | Master coordinates are missing or outside valid WGS84 bounds. | [Step_7_0_update_master_table.py:1366](../../scripts/Step_7_0_update_master_table.py) |
| `{prefix}_missing` | The named data domain is missing for the recording. | [Step_7_0_update_master_table.py:1371](../../scripts/Step_7_0_update_master_table.py) |
| `{prefix}_issue` | The named data domain exists but reports issues. | [Step_7_0_update_master_table.py:1373](../../scripts/Step_7_0_update_master_table.py) |
| `grid_100m_missing_majority_formation` | No 100 m majority formation; this does not necessarily mean no grid ID. | [Step_7_0_update_master_table.py:1375](../../scripts/Step_7_0_update_master_table.py) |
| `grid_10m_missing_majority_formation` | No 10 m majority formation; this does not necessarily mean no grid ID. | [Step_7_0_update_master_table.py:1377](../../scripts/Step_7_0_update_master_table.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `not_started` | `compact.empty` | [Step_7_0_update_master_table.py:613](../../scripts/Step_7_0_update_master_table.py) |
| `majority_formation_status_10m` | `Emitted by add_10m_formation` | [Step_7_0_update_master_table.py:1164](../../scripts/Step_7_0_update_master_table.py) |
| `validated` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1288](../../scripts/Step_7_0_update_master_table.py) |
| `has_issues` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1289](../../scripts/Step_7_0_update_master_table.py) |
| `missing` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1295](../../scripts/Step_7_0_update_master_table.py) |
| `partial` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1381](../../scripts/Step_7_0_update_master_table.py) |
| `not_started` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1397](../../scripts/Step_7_0_update_master_table.py) |
| `manual_review_required` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1398](../../scripts/Step_7_0_update_master_table.py) |
| `approved` | `Emitted by add_agreement_and_ready_flags` | [Step_7_0_update_master_table.py:1401](../../scripts/Step_7_0_update_master_table.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
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

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `execution_phase() == 'bioacoustics'` | [Step_7_0_update_master_table.py:1572](../../scripts/Step_7_0_update_master_table.py) |
| `0` | `except ValueError` | [Step_7_0_update_master_table.py:1596](../../scripts/Step_7_0_update_master_table.py) |
| `0` | `Emitted by main` | [Step_7_0_update_master_table.py:1702](../../scripts/Step_7_0_update_master_table.py) |
| `1` | `except Exception` | [Step_7_0_update_master_table.py:1705](../../scripts/Step_7_0_update_master_table.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

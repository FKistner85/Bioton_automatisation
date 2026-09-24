# Step 4 Sentinel-2 Mirror And Inventory (EN)

## Purpose
Mirrors external Sentinel-2 Drive files and inventories GeoTIFFs.

## Script
`scripts/Step_4_1_Sentinel2_download.py, scripts/Step_4_0_Sentinel2_inventory.py`

## Inputs
- `Google Drive token.json`
- `PointData/S2`
- `PointData/S2_Scores.csv`

The score-table identifier is configured through
`sentinel2_inventory.score_id_column`. The inventory also recognises the
case-insensitive aliases `id`, `DC_id`, `dawn_chorus_id`, and `recording_id`.

## Outputs
- `PointData/S2/*.tif`
- `outputs/step_4_0_Sentinel2_inventory/*`
- `outputs/step_4_1_sentinel2_download/*`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_4_1_sentinel2_mirror`, `step_4_0_sentinel2_inventory`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `sentinel2_download`, `sentinel2_inventory`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_4_1_Sentinel2_download.py --config config.horeka.json`
- `python scripts/Step_4_0_Sentinel2_inventory.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
The Drive log, file size and modification time control incremental processing.

## Quality Control
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical run statuses are defined in `scripts/common.py`; `schemas/status_model.json` defines status-event fields.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `score_rows_with_invalid_id:{invalid_id_count}` | Score file contains rows with invalid IDs. | [Step_4_0_Sentinel2_inventory.py:222](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `duplicate_score_rows:{row_count}` | Multiple score rows for the same ID. | [Step_4_0_Sentinel2_inventory.py:275](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `non_numeric_or_missing_scores:{missing_numeric_count}` | Score values are nonnumeric or missing. | [Step_4_0_Sentinel2_inventory.py:280](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `scores_outside_0_1:{invalid_range_count}` | Numeric Sentinel scores lie outside 0 to 1. | [Step_4_0_Sentinel2_inventory.py:285](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `quality_score_missing` | No score is available for the recording. | [Step_4_0_Sentinel2_inventory.py:290](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `no_valid_quality_score` | No valid Sentinel score among existing rows. | [Step_4_0_Sentinel2_inventory.py:293](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `unexpected_raster_driver:{dataset.driver}` | Raster driver is not GTiff. | [Step_4_0_Sentinel2_inventory.py:358](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `invalid_dimensions:{dataset.width}x{dataset.height}` | Raster/image width or height is invalid. | [Step_4_0_Sentinel2_inventory.py:363](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `no_raster_bands` | Raster contains no bands. | [Step_4_0_Sentinel2_inventory.py:368](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `missing_crs` | Raster has no coordinate reference system. | [Step_4_0_Sentinel2_inventory.py:371](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `identity_geotransform` | Raster has an identity transform; check georeferencing. | [Step_4_0_Sentinel2_inventory.py:374](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `non_finite_bounds` | Raster bounds contain NaN or infinite values. | [Step_4_0_Sentinel2_inventory.py:387](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `invalid_bounds` | Raster bounds do not define a valid extent. | [Step_4_0_Sentinel2_inventory.py:393](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `raster_read_failed:{type(exc).__name__}:{exc}` | Raster could not be opened or read. | [Step_4_0_Sentinel2_inventory.py:448](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `all_pixels_nodata` | All inspected raster pixels are NoData. | [Step_4_0_Sentinel2_inventory.py:470](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `contains_nan_values:{nan_values}` | Raster contains NaN values. | [Step_4_0_Sentinel2_inventory.py:473](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `contains_infinite_values:{infinite_values}` | Raster contains infinite values. | [Step_4_0_Sentinel2_inventory.py:478](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `constant_raster:value={global_min}` | All valid raster values are identical; check plausibility. | [Step_4_0_Sentinel2_inventory.py:483](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `filename_does_not_contain_id_before_tif_extension` | TIFF filename does not supply the expected recording ID. | [Step_4_0_Sentinel2_inventory.py:524](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `source_stat_failed:{type(exc).__name__}:{exc}` | Filesystem stat failed for the source file. | [Step_4_0_Sentinel2_inventory.py:532](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `empty_file` | Existing file has zero bytes. | [Step_4_0_Sentinel2_inventory.py:574](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `duplicate_tif_files_for_id:{len(id_rows)}` | Multiple TIFF files are assigned to the same recording. | [Step_4_0_Sentinel2_inventory.py:948](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `quality_score_missing` | No score is available for the recording. | [Step_4_0_Sentinel2_inventory.py:969](../../scripts/Step_4_0_Sentinel2_inventory.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `skipped_existing_immutable` | `dc_id in immutable_ids` | [sentinel2_gee.py:666](../../scripts/sentinel2_gee.py) |
| `completed_existing_task` | `state == 'COMPLETED'` | [sentinel2_gee.py:683](../../scripts/sentinel2_gee.py) |
| `ready` | `Emitted by run_gee_drive_exports` | [sentinel2_gee.py:721](../../scripts/sentinel2_gee.py) |
| `score_only` | `score_only` | [sentinel2_gee.py:748](../../scripts/sentinel2_gee.py) |
| `score_only` | `bool(getattr(args, 'score_only', False))` | [sentinel2_gee.py:815](../../scripts/sentinel2_gee.py) |
| `skipped_existing` | `ok` | [sentinel2_gee.py:837](../../scripts/sentinel2_gee.py) |
| `downloaded` | `ok` | [sentinel2_gee.py:847](../../scripts/sentinel2_gee.py) |
| `validation_failed` | `not (ok)` | [sentinel2_gee.py:850](../../scripts/sentinel2_gee.py) |
| `download_failed` | `except Exception` | [sentinel2_gee.py:854](../../scripts/sentinel2_gee.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {path}` | `not path.is_file()` | [Step_4_0_Sentinel2_inventory.py:104](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `TypeError: 'sentinel2_inventory' must be a JSON object.` | `not isinstance(section, dict)` | [Step_4_0_Sentinel2_inventory.py:112](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `NotADirectoryError: Sentinel-2 source directory not found: {source_dir}` | `not source_dir.is_dir()` | [Step_4_0_Sentinel2_inventory.py:123](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `ValueError: Missing Dawn Chorus ID column in Sentinel-2 score CSV. Tried {[candidate for candidate in candidates if candidate]}. Available columns: {columns}` | `Emitted by resolve_score_id_column` | [Step_4_0_Sentinel2_inventory.py:166](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `FileNotFoundError: Sentinel-2 score CSV not found: {score_csv}` | `not score_csv.is_file()` | [Step_4_0_Sentinel2_inventory.py:184](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `ValueError: Missing required columns in Sentinel-2 score CSV: {sorted(missing_columns)}. Available columns: {df.columns.tolist()}` | `missing_columns` | [Step_4_0_Sentinel2_inventory.py:198](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `KeyError: Missing sentinel2_download section in config.` | `'sentinel2_download' not in config` | [Step_4_1_Sentinel2_download.py:48](../../scripts/Step_4_1_Sentinel2_download.py) |
| `KeyError: No ID column found in Sentinel-2 metadata CSV: {metadata_csv}` | `id_column is None` | [Step_4_1_Sentinel2_download.py:133](../../scripts/Step_4_1_Sentinel2_download.py) |
| `TimeoutError: Completed GEE exports not visible in Drive folder {folder_id}: {sample}` | `time.monotonic() >= deadline` | [Step_4_1_Sentinel2_download.py:192](../../scripts/Step_4_1_Sentinel2_download.py) |
| `RuntimeError: Google Drive credentials/token missing or interactive auth disabled` | `service is None` | [Step_4_1_Sentinel2_download.py:442](../../scripts/Step_4_1_Sentinel2_download.py) |
| `RuntimeError: --score-only requires sentinel2_download.gee_drive_export_enabled=true` | `args.score_only` | [Step_4_1_Sentinel2_download.py:500](../../scripts/Step_4_1_Sentinel2_download.py) |
| `KeyError: Missing sentinel2_cleaning section in config.` | `'sentinel2_cleaning' not in config` | [Step_4_2_clean_sentinel2.py:20](../../scripts/Step_4_2_clean_sentinel2.py) |
| `KeyError: No Dawn Chorus ID column found in {path}` | `id_column is None` | [sentinel2_gee.py:78](../../scripts/sentinel2_gee.py) |
| `KeyError: Metadata must contain lat and lon/lng columns: {path}` | `'lat' not in frame or not ('lon' in frame or 'lng' in frame)` | [sentinel2_gee.py:80](../../scripts/sentinel2_gee.py) |
| `KeyError: Metadata must contain datetime or datetime_utc: {path}` | `datetime_column is None` | [sentinel2_gee.py:86](../../scripts/sentinel2_gee.py) |
| `KeyError: Score file must contain an ID column and score: {path}` | `column is None or 'score' not in frame` | [sentinel2_gee.py:153](../../scripts/sentinel2_gee.py) |
| `KeyError: Incoming score rows must contain DC_id` | `'DC_id' not in update` | [sentinel2_gee.py:198](../../scripts/sentinel2_gee.py) |
| `requests.HTTPError: Earth Engine HTTP {response.status_code}` | `response.status_code in {429, 500, 502, 503, 504}` | [sentinel2_gee.py:332](../../scripts/sentinel2_gee.py) |
| `RuntimeError: GEE download failed for {target.name}: {last_error}` | `Emitted by _download_image` | [sentinel2_gee.py:342](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE service-account key not found: {key_path}` | `not key_path.is_file()` | [sentinel2_gee.py:379](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: No GEE service-account key configured and stored Earth Engine credentials are unavailable` | `except Exception` | [sentinel2_gee.py:390](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: No user OAuth token configured for legacy Earth Engine Drive exports` | `not token_value` | [sentinel2_gee.py:402](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token not found: {token_path}` | `not token_path.is_file()` | [sentinel2_gee.py:407](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Cannot read GEE export OAuth token: {token_path}` | `except (OSError, json.JSONDecodeError)` | [sentinel2_gee.py:414](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Invalid GEE export OAuth token: {token_path}` | `not isinstance(token_payload, dict)` | [sentinel2_gee.py:416](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token lacks required scopes: {missing}` | `granted and (not required_scopes.issubset(granted))` | [sentinel2_gee.py:440](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: GEE export OAuth token has no refresh token` | `not credentials.refresh_token` | [sentinel2_gee.py:443](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored_chunk` | [sentinel2_gee.py:491](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: earthengine-api is not installed` | `except ImportError` | [sentinel2_gee.py:584](../../scripts/sentinel2_gee.py) |
| `TimeoutError: Timed out waiting for legacy Sentinel-2 Drive exports (queued={len(queue)}, active={len(running)})` | `time.monotonic() >= export_deadline` | [sentinel2_gee.py:733](../../scripts/sentinel2_gee.py) |
| `RuntimeError: {failed} legacy Sentinel-2 Drive export task(s) failed` | `failed` | [sentinel2_gee.py:757](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: Direct GEE raster download is disabled until parity with the legacy export is verified` | `not bool(settings.get('gee_direct_download_verified', False))` | [sentinel2_gee.py:773](../../scripts/sentinel2_gee.py) |
| `GeeUnavailable: earthengine-api is not installed` | `except ImportError` | [sentinel2_gee.py:779](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored_chunk` | [sentinel2_gee.py:796](../../scripts/sentinel2_gee.py) |
| `RuntimeError: Earth Engine score response has no DC_id column` | `'DC_id' not in scored` | [sentinel2_gee.py:806](../../scripts/sentinel2_gee.py) |
| `RuntimeError: {failed} Sentinel-2 GEE tile downloads failed` | `failed` | [sentinel2_gee.py:857](../../scripts/sentinel2_gee.py) |
| `FileNotFoundError: {label} missing: {path}` | `not path.is_file()` | [sentinel_credentials_preflight.py:16](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: {label} is not valid JSON: {path}` | `except Exception` | [sentinel_credentials_preflight.py:20](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: {label} must contain a JSON object: {path}` | `not isinstance(value, dict)` | [sentinel_credentials_preflight.py:22](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Missing Sentinel credential setting: {setting}` | `not value` | [sentinel_credentials_preflight.py:35](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE service-account key has the wrong structure` | `service_key.get('type') != 'service_account' or not service_key.get('client_email')` | [sentinel_credentials_preflight.py:84](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE user export token has no refresh_token` | `not export_token.get('refresh_token')` | [sentinel_credentials_preflight.py:88](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: GEE user export token lacks Earth Engine or Drive scope` | `export_scopes and (not required_export_scopes.issubset(export_scopes))` | [sentinel_credentials_preflight.py:95](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Drive OAuth client has the wrong structure` | `not any((key in drive_credentials for key in ('installed', 'web')))` | [sentinel_credentials_preflight.py:101](../../tools/sentinel_credentials_preflight.py) |
| `RuntimeError: Drive read-only token has no refresh_token` | `not drive_token.get('refresh_token')` | [sentinel_credentials_preflight.py:104](../../tools/sentinel_credentials_preflight.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `Emitted by main` | [Step_4_0_Sentinel2_inventory.py:1235](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `1` | `except Exception` | [Step_4_0_Sentinel2_inventory.py:1242](../../scripts/Step_4_0_Sentinel2_inventory.py) |
| `0` | `acquisition_mode in {'auto', 'gee_direct'}` | [Step_4_1_Sentinel2_download.py:370](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `args.score_only` | [Step_4_1_Sentinel2_download.py:489](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `Emitted by main` | [Step_4_1_Sentinel2_download.py:670](../../scripts/Step_4_1_Sentinel2_download.py) |
| `1` | `except Exception` | [Step_4_1_Sentinel2_download.py:680](../../scripts/Step_4_1_Sentinel2_download.py) |
| `0` | `Emitted by main` | [Step_4_2_clean_sentinel2.py:86](../../scripts/Step_4_2_clean_sentinel2.py) |
| `1` | `except Exception` | [Step_4_2_clean_sentinel2.py:89](../../scripts/Step_4_2_clean_sentinel2.py) |
| `0` | `not bool(settings.get('gee_drive_export_enabled', False))` | [sentinel_credentials_preflight.py:55](../../tools/sentinel_credentials_preflight.py) |
| `0` | `Emitted by main` | [sentinel_credentials_preflight.py:112](../../tools/sentinel_credentials_preflight.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

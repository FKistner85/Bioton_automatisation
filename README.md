# Bio-O-Ton Data Pipeline

Bio-O-Ton is a restartable data-processing pipeline for Dawn Chorus recordings. It combines cleaned recording metadata, habitat-formation products at 100 m and 10 m, media inventories and downloads, Sentinel-2 data, HOSTRADA weather, bioacoustic model results, validation, and visual reports. Production runs use LSDF storage and Slurm on HoreKa; a Windows orchestrator is available for controlled local execution.

This document reflects the implementation and default configuration checked on **2026-08-26**. Paths and operational defaults come from [`config.horeka.json`](config.horeka.json), the executable step registry is [`pipeline_steps.json`](pipeline_steps.json), and the final table is written by [`scripts/Step_7_0_update_master_table.py`](scripts/Step_7_0_update_master_table.py).

## Master table at a glance

The main result is one row per unique `dawn_chorus_id` in:

```text
/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/
├── Bio_O_Ton_Master.csv
├── Bio_O_Ton_Master.parquet
└── Bio_O_Ton_Master_summary.json
```

The CSV is the portable exchange format, the compressed Parquet file is intended for analysis, and the JSON file contains row counts, readiness totals, status distributions, and update metadata. The current schema version is `2026-08-04-mastertable-v4`. Detailed definitions, derivation rules, issue-code conventions, and source products are in the [master-table reference](MASTER_TABLE_README.md).

The compact dictionary below covers **all 99 columns written by Step 7_0**. Related fields are grouped to keep the overview readable; every group links to its full definition.

| Column(s) | Short description | Details |
|---|---|---|
| `mastertable_schema_version` | Version of the row contract. | [Identity and provenance](MASTER_TABLE_README.md#identity-and-provenance) |
| `workflow_run_id` | Workflow that most recently updated the row. | [Identity and provenance](MASTER_TABLE_README.md#identity-and-provenance) |
| `dawn_chorus_id` | Unique numeric recording identifier and primary key. | [Identity and provenance](MASTER_TABLE_README.md#identity-and-provenance) |
| `source_fingerprint` | SHA-256 fingerprint of relevant source fields. | [Identity and provenance](MASTER_TABLE_README.md#identity-and-provenance) |
| `datetime_local`, `datetime_utc`, `date_local`, `time_local` | Clean local/UTC recording time and convenient date/time components. | [Time and coordinates](MASTER_TABLE_README.md#time-and-coordinates) |
| `timestamp_source`, `timestamp_changed`, `timestamp_change_reason` | Origin and normalization history of the timestamp. | [Time and coordinates](MASTER_TABLE_README.md#time-and-coordinates) |
| `lat`, `lon` | Cleaned WGS84 recording coordinates. | [Time and coordinates](MASTER_TABLE_README.md#time-and-coordinates) |
| `record_added_to_mastertable_utc`, `record_updated_in_mastertable_utc` | First insertion and most recent row-update times. | [Identity and provenance](MASTER_TABLE_README.md#identity-and-provenance) |
| `metadata_status` | Canonical validity status for time and coordinates. | [Status fields](MASTER_TABLE_README.md#status-fields) |
| `sound_exists`, `sound_has_issues`, `sound_issue_codes`, `sound_status` | Audio presence, QC result, compact causes, and canonical status. | [Audio and photos](MASTER_TABLE_README.md#audio-and-photos) |
| `photo_exists`, `photo_has_issues`, `photo_issue_codes`, `photo_status` | Photo presence, QC result, compact causes, and canonical status. | [Audio and photos](MASTER_TABLE_README.md#audio-and-photos) |
| `sentinel_exists`, `sentinel_has_issues`, `sentinel_quality_score`, `sentinel_issue_codes`, `sentinel_status` | Sentinel-2 presence, technical QC, optional score, causes, and status. | [Sentinel-2](MASTER_TABLE_README.md#sentinel-2) |
| `weather_point_exists`, `weather_point_has_issues`, `weather_point_issue_codes`, `weather_point_status` | Per-recording HOSTRADA file presence, QC, causes, and status. | [Weather](MASTER_TABLE_README.md#weather) |
| `weather_raster_hostrada_100m_exists`, `weather_raster_hostrada_100m_has_issues`, `weather_raster_hostrada_100m_issue_codes` | Global availability and QC state of optional 100 m weather rasters. | [Weather](MASTER_TABLE_README.md#weather) |
| `grid_100m_id`, `grid_100m_assignment_exists`, `grid_100m_has_majority_formation` | Assigned 100 m cell and availability of its majority formation. | [100 m formation](MASTER_TABLE_README.md#100-m-formation) |
| `inside_lrt_polygon`, `lrt_polygon_count` | Whether and how often the point directly intersects cleaned LRT polygons. | [Direct LRT intersections](MASTER_TABLE_README.md#direct-lrt-intersections) |
| `lrt_code_count`, `lrt_formation_count`, `lrt_status_count`, `lrt_mapping_year_count` | Counts of distinct attributes among direct polygon hits. | [Direct LRT intersections](MASTER_TABLE_README.md#direct-lrt-intersections) |
| `lrt_codes`, `lrt_formations`, `lrt_conservation_statuses`, `lrt_mapping_years` | Aggregated attributes of directly intersected polygons. | [Direct LRT intersections](MASTER_TABLE_README.md#direct-lrt-intersections) |
| `majority_formation_100m`, `majority_formation_status_100m` | Dominant 100 m formation and its dominant conservation status. | [100 m formation](MASTER_TABLE_README.md#100-m-formation) |
| `majority_value_100m`, `second_value_100m`, `majority_delta_100m`, `majority_disputed_100m` | Dominance metrics in centi-percent and the two-percentage-point dispute flag. | [100 m formation](MASTER_TABLE_README.md#100-m-formation) |
| `formation_100m_status` | Canonical 100 m assignment/formation status. | [100 m formation](MASTER_TABLE_README.md#100-m-formation) |
| `grid_10m_id`, `grid_10m_assignment_exists`, `grid_10m_has_majority_formation` | Derived 10 m cell and availability of its majority formation. | [10 m formation](MASTER_TABLE_README.md#10-m-formation) |
| `majority_formation_10m`, `majority_formation_status_10m` | Dominant 10 m formation and its dominant conservation status. | [10 m formation](MASTER_TABLE_README.md#10-m-formation) |
| `majority_value_10m`, `second_value_10m`, `majority_delta_10m`, `majority_disputed_10m` | 10 m dominance metrics in centi-percent and dispute flag. | [10 m formation](MASTER_TABLE_README.md#10-m-formation) |
| `formation_10m_status` | Canonical 10 m assignment/formation status. | [10 m formation](MASTER_TABLE_README.md#10-m-formation) |
| `formation_100m_10m_agree`, `formation_status_100m_10m_agree` | Agreement between 100 m and 10 m formation and status. | [Cross-resolution checks](MASTER_TABLE_README.md#cross-resolution-and-variant-coverage) |
| `formation_primary_variant` | LRT variant supplying detailed formation fields to the main row. | [Variant coverage](MASTER_TABLE_README.md#cross-resolution-and-variant-coverage) |
| `formation_variant_count_expected`, `formation_variants_with_100m_majority`, `formation_variants_with_10m_majority`, `formation_variant_products_complete` | Expected variants, per-ID coverage, and global product completeness. | [Variant coverage](MASTER_TABLE_README.md#cross-resolution-and-variant-coverage) |
| `bioacoustic_status`, `bioacoustic_has_issues`, `bioacoustic_issue_codes` | Canonical Step-6 outcome and compact failure causes. | [Bioacoustics](MASTER_TABLE_README.md#bioacoustics) |
| `bioacoustic_models_expected`, `bioacoustic_models_complete`, `bioacoustic_required_models_complete` | Planned/completed models and required-model completeness. | [Bioacoustics](MASTER_TABLE_README.md#bioacoustics) |
| `bioacoustic_inference_version` | Version of the inference/output transformation. | [Bioacoustics](MASTER_TABLE_README.md#bioacoustics) |
| `bioacoustic_species_count`, `bird_species_count`, `nonbird_species_count` | Aggregated model-predicted taxon counts; not confirmed observations. | [Bioacoustics](MASTER_TABLE_README.md#bioacoustics) |
| `bioacoustic_max_confidence`, `top_species_scientific`, `top_species_model_support` | Highest normalized score, top-ranked taxon, and supporting-model count. | [Bioacoustics](MASTER_TABLE_README.md#bioacoustics) |
| `ready_for_general_analysis` | Metadata, audio, point weather, and Sentinel-2 are technically usable. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `ready_for_formation_analysis_100m`, `ready_for_formation_analysis_10m` | General readiness plus a majority formation at the named resolution. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `ready_for_direct_lrt_analysis` | General readiness plus a direct cleaned-LRT polygon hit. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `ready_for_formation_weather_raster_analysis_100m` | 100 m formation readiness plus clean optional HOSTRADA rasters. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `ready_for_multimodal_analysis` | General readiness plus a technically valid photo. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `ready_for_bioacoustic_analysis` | Valid audio plus successful required bioacoustic models; independent of weather/formation. | [Readiness](MASTER_TABLE_README.md#readiness-flags) |
| `record_blocking_issue_codes` | Pipe-separated reasons that block one or more readiness paths. | [Issues and statuses](MASTER_TABLE_README.md#issue-code-and-status-conventions) |
| `record_status`, `release_status` | Overall technical row status and separate manual release state. | [Release model](MASTER_TABLE_README.md#record-and-release-status) |
| `manual_review_comment`, `manual_reviewed_by`, `manual_reviewed_utc` | Preserved manual review metadata. | [Release model](MASTER_TABLE_README.md#record-and-release-status) |

## Quick start on HoreKa

Run all commands from the repository root. The recommended entry point is the persistent hybrid controller:

```bash
bash run_horeka.sh add_new_ids
```

It starts a detached `tmux` session on the HoreKa login node, creates the run plan and pipeline lock, submits only planned compute work to Slurm, waits for the submitted jobs, and then runs final validation and HTML report generation locally with one CPU before releasing the lock.

Monitor it with:

```bash
tmux ls
tmux attach -t <session-name>
squeue -u "$USER"
```

Before the first data run, create both environments:

```bash
bash bootstrap_env.sh
bash bootstrap_bacpipe_env.sh
```

The core bootstrap prefers `micromamba`, `mamba`, or `conda` and falls back to `python3 -m venv`. Its default target is `.venv`. Bioacoustics uses the separate `.venv_bacpipe` environment. A core interpreter may be supplied through `PYTHON`; a Bacpipe interpreter may be supplied through `BIOOTON_BACPIPE_PYTHON`.

### Run modes

| Mode | Command | Meaning |
|---|---|---|
| Incremental production | `bash run_horeka.sh add_new_ids` | Processes new, changed, and previously problematic IDs and invalidated global products. This is the normal run. |
| Logical full rebuild | `bash run_horeka.sh from_scratch` | Recomputes current IDs and core global steps with `--force`; original source files and downloads are not deleted. Incomplete full-run generations resume from successful step markers. |
| Functionality test | `bash run_horeka.sh functionality_test` | Runs fast import, config, schema, syntax, and regression checks locally through the controller. |
| Formation comparison | `bash run_horeka.sh formation_compare` | Submits the formation-product comparison as a Slurm job. |
| Safe submission preview | `bash run_horeka.sh add_new_ids --local-test` | Runs controller-side planning/preflights and prints the Slurm jobs that would be submitted; no Slurm work, final validation, or reports are executed. |

Useful controller options:

```bash
bash run_horeka.sh add_new_ids --session bioton_update
bash run_horeka.sh add_new_ids --foreground
bash run_horeka.sh add_new_ids --update --branch main
```

`--update` explicitly runs `git pull --ff-only` through [`update_horeka_from_git.sh`](update_horeka_from_git.sh); without it, the checked-out commit is used unchanged.

## End-to-end workflow

The production path is:

```text
run_horeka.sh
  -> tools/horeka_controller.py
     -> acquire pipeline lock
     -> tools/plan_pipeline_run.py
     -> submit_bio_o_ton_horeka.sh
        -> planned Slurm DAG (Steps 1-7)
        -> final Step 7_0 master-table snapshot
     -> wait for all submitted Slurm jobs
     -> tools/final_validation_report.py
     -> tools/generate_pipeline_visual_reports.py
     -> release pipeline lock
```

Most Slurm edges use `afterany`. Downstream jobs therefore start after their inputs stop, even if an upstream job failed, and can record missing/partial products instead of leaving `DependencyNeverSatisfied` jobs behind. Bioacoustic stages that cannot produce a meaningful result after failure use `afterok` where required. The master table, final validation, and visual report are designed to expose the resulting state.

### Pipeline step catalog

| Step | Purpose | Main implementation | Detailed English documentation |
|---|---|---|---|
| Control | Run planning, locking, manifests, and full-rebuild generation state. | `tools/plan_pipeline_run.py`, `tools/pipeline_lock.py`, `tools/run_with_manifest.py` | [Pipeline control](Readmes/pipeline_control/README_EN.md) |
| 1 | Normalize timestamps/coordinates and maintain per-domain fingerprints. | `scripts/Step_1_metadata_extraction.py` | [Step 1](Readmes/step_1_metadata/README_EN.md) |
| 2.0 | Clean the configured primary LRT source. | `scripts/Step_2_0_clean_lrts.py` | [Step 2.0](Readmes/step_2_0_lrt_cleaning/README_EN.md) |
| 2.1 | Overlay LRT polygons with the 100 m grid and compute formation/status shares. | `scripts/Step_2_1_merge_lrts_and_grid.py` | [Step 2.1](Readmes/step_2_1_100m_formation_status/README_EN.md) |
| 2.2 | Assign recording points to 100 m cells and direct LRT polygons. | `scripts/Step_2_2_assign_points_to_lrt_grid.py` | [Step 2.2](Readmes/step_2_2_point_assignment/README_EN.md) |
| 2.3 | Aggregate 100 m products to 1 km, 5 km, and 10 km. | `scripts/Step_2_3_generate_remaining_grid_products.py` | [Step 2.3](Readmes/step_2_3_grid_aggregation/README_EN.md) |
| 2.4 | Derive Susi-compatible 10 m formation/status products. | `scripts/Step_2_4_generate_10m_formation_status_products.py` | [Step 2.4](Readmes/step_2_4_10m_formation_status/README_EN.md) |
| 2 variants | Run Steps 2.0-2.4 independently for every `All_Bundeslander_*.gpkg`. | `tools/step2_variants.py` | [Step-2 variants](Readmes/step_2_variants/README_EN.md) |
| 3.0/3.1 | Inventory, QC, download, and re-inventory audio and photos. | `scripts/Step_3_0_*`, `scripts/Step_3_1_*` | [Step 3](Readmes/step_3_media/README_EN.md) |
| 4.1/4.0 | Mirror Sentinel-2 GeoTIFFs from Google Drive/GEE outputs, then inventory/QC LSDF files. | `scripts/Step_4_1_Sentinel2_download.py`, `scripts/Step_4_0_Sentinel2_inventory.py` | [Step 4](Readmes/step_4_sentinel2/README_EN.md) |
| 5.1/5.2 | Inventory and generate per-recording HOSTRADA weather time series. | `scripts/Step_5_1_Weather_inventory.py`, `scripts/Step_5_2_download_weather_data.py` | [Step 5.2](Readmes/step_5_2_weather/README_EN.md) |
| 5.3 | Mirror HOSTRADA monthly NetCDF source files. | `scripts/Step_5_3_download_hostrada_monthly.py` | [Step 5.3](Readmes/step_5_3_hostrada_monthly/README_EN.md) |
| 5.4 | Convert variable/year combinations to tiled 100 m rasters. | `tools/run_hostrada_raster_all.py`, `scripts/Step_5_4_prepare_hostrada_rasters.py` | [Step 5.4](Readmes/step_5_4_hostrada_rasters/README_EN.md) |
| 5.5 | Recursively inventory and QC HOSTRADA raster products. | `scripts/Step_5_5_check_hostrada_raster_products.py` | [Step 5.5](Readmes/step_5_5_hostrada_raster_qc/README_EN.md) |
| 6.0-6.6 | Preflight models, prepare work, infer, normalize, filter, aggregate, and QC bioacoustics. | `scripts/Step_6_*.py` | [Step 6](Readmes/step_6_bioacoustics/README_EN.md) |
| 7.0 | Atomically update the main ID-level master table and append status events. | `scripts/Step_7_0_update_master_table.py` | [Step 7.0](Readmes/step_7_0_master_table/README_EN.md), [column reference](MASTER_TABLE_README.md) |
| 7.1 | Build normalized ID-by-LRT-variant tables and summaries. | `scripts/Step_7_1_update_formation_variant_table.py` | [Step-2 variants](Readmes/step_2_variants/README_EN.md) |
| Validation | Validate current-run manifests, required artifacts, and configured readiness rules. | `tools/final_validation_report.py` | [Validation and comparison](Readmes/validation_and_comparison/README_EN.md) |
| 9 | Generate static per-step HTML dashboards. | `tools/generate_pipeline_visual_reports.py` | [Step 9](Readmes/step_9_visual_reports/README_EN.md) |

The [English documentation index](Readmes/README_INDEX.md) provides the same step links in a shorter list.

## Incremental planning and invalidation

Every data workflow receives one `workflow_run_id`. The planner compares the Dawn Chorus source, per-domain fingerprints, current step state, inventory baselines, configured global inputs, and the previous master table. It writes:

```text
outputs/step_0_control/run_plans/<workflow_run_id>/run_plan.json
outputs/step_0_control/run_plans/<workflow_run_id>/metadata_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/point_assignment_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/audio_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/photo_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/sentinel_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/weather_ids.csv
outputs/step_0_control/run_plans/<workflow_run_id>/bioacoustic_ids.csv
```

Key invalidation behavior:

| Change or condition | Work scheduled |
|---|---|
| New ID or changed time/GPS | Metadata, point assignment, point weather, and coordinate-dependent products for that ID. |
| Changed audio URL/fingerprint | Audio retry state is reset; download, post-inventory, and bioacoustic work are reconsidered. |
| Changed photo URL/fingerprint | Photo retry state is reset and the photo path is reconsidered. |
| Changed LRT source | Cleaning and all dependent 100 m, point-assignment, aggregation, and 10 m formation products. |
| Changed grid source | Grid-dependent formation products and point assignment. |
| Changed Sentinel source metadata | The corresponding Drive file is mirrored again based on file ID, MD5, modified time, and size. |
| Previous missing/issue state | The affected ID/domain is retried by the next incremental plan. |
| Healthy, unchanged inventory baseline | Expensive recursive inventory/download work may be skipped. |
| `from_scratch` | Logical recomputation of current data without deleting sources or original downloads. |

An interrupted full rebuild is tracked as a generation:

```text
outputs/step_0_control/full_rebuild/current.json
outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json
```

A later `from_scratch` submission of the same incomplete generation queues only steps without successful completion markers.

## Checkpoints, batching, and master-table updates

Long-running steps persist restart state rather than relying on a single all-or-nothing job:

| Area | Resume mechanism |
|---|---|
| Step 2.1 | Overlay chunk checkpoints. |
| Step 2.4 | 10 m Parquet chunks and batch state. |
| Step 3.1 | Persistent retry CSVs, atomic downloads, and `progress.json`. |
| Step 4.1 | Drive/GEE metadata logs and batch state. |
| Step 5.1 | Reuse of unchanged, error-free weather QC rows. |
| Step 5.2 | Per-ID files/state, Slurm shards, verification job, and `progress.json`. |
| Step 5.3 | Existing monthly NetCDF files. |
| Step 5.4 | Per-tile status files and array verification. |
| Step 5.5 | Reuse of unchanged, error-free raster QC rows. |
| Step 6.2 | Per-model/per-shard inference state and batch checkpoints. |

Step 7.0 is serialized and uses an atomic file replacement plus a write lock. ID-scoped upstream stages pass `--ids-file`, replacing only affected master rows; global formation or raster changes trigger a full refresh. In direct, non-hybrid Slurm operation, audio, photo, and point-weather scripts may also request an intermediate master update every **5,000 completed IDs** according to `config.horeka.json`. The hybrid controller disables these in-step updates and submits one dependency-aware final master job.

## Formation products and variants

The primary LRT variant is currently `no_K_post2017_threshold_50`, sourced from:

```text
Biodiversity_data/Bundeslander/All_Bundeslander/
  All_Bundeslander_no_K_post2017_threshold_50.gpkg
```

Formation and LRT shares in Susi-compatible 100 m/10 m products are integer centi-percent values: `10000` means 100.00%. Formation totals include A/B/C/K. The majority formation status is selected within the majority formation from A/B/C only. A result is marked disputed when `majority_delta <= 200`, i.e. the leading two formations differ by at most two percentage points.

Run every available LRT variant as an isolated sensitivity branch with:

```bash
bash submit_step2_variants_horeka.sh add_new_ids
```

Use `from_scratch` as the argument to force all variant stages. Outputs are isolated under `outputs/step_2_variants/<suffix>/`; normalized results are written to:

```text
outputs/Bio_O_Ton_Formation_Variants.csv
outputs/Bio_O_Ton_Formation_Variants.parquet
outputs/Bio_O_Ton_Formation_Variants_summary.json
outputs/Bio_O_Ton_Variant_Summary.csv
outputs/Bio_O_Ton_Variant_Temporal_Summary.csv
```

The optional public-LRT workflow is separate from the main DAG:

```bash
bash run_public_lrt_products.sh
bash run_public_lrt_products.sh --force
```

It runs Steps 2.5 and 2.6 using `public_lrt_cleaning` and `public_lrt_grid_merge` from the configuration.

## Media, Sentinel-2, and weather downloads

Only domain downloads are written outside `outputs`:

| Product | Source | LSDF target |
|---|---|---|
| Audio | `audio` URL in the Dawn Chorus source table | `PointData/SoundRecordings/<id>_audio.<ext>` |
| Photo | `photo` URL in the source table | `PointData/Images_SoundRecordings/<id>_photo.<ext>` |
| Sentinel-2 | Configured Google Drive folder populated by the GEE export path | `PointData/S2/<Drive-filename>.tif` |
| Point weather | DWD Open Data HOSTRADA | `PointData/Weather/Hostrada/weather_<id>.csv` |

Sentinel credentials are checked before a planned Step 4.1 run. Unattended HoreKa execution requires prepared non-interactive credentials/token files; setup is described in [`HOREKA_GEE_SECRET_SETUP_DE.md`](HOREKA_GEE_SECRET_SETUP_DE.md) (German operational note). Manual mirroring and score validation are available through:

```bash
bash run_sentinel2_mirror.sh
bash run_sentinel_score_validation.sh
```

Step 5.2 currently requests 10 preceding days plus the recording day, yielding an expected 264 hourly rows with temperature, cloud cover, relative humidity, downwelling radiation, wind direction, and wind speed. It uses up to eight Slurm shards with at most four concurrent tasks by default.

### Optional HOSTRADA raster workflow

The area-wide Steps 5.3-5.5 are disabled by default with `hostrada_raster_products.enabled: false`. They are intended for deliberate, usually annual updates and do not block general or normal 100 m formation readiness. When present and clean, they enable `ready_for_formation_weather_raster_analysis_100m`.

Set `hostrada_raster_products.enabled` to `true` for a planned pipeline run, or run targeted maintenance commands:

```bash
bash run_hostrada_raster_year.sh Ta 2017
bash run_hostrada_raster_quality_check.sh
```

Supported variables are `Ta`, `Rh`, `Radiation`, `CloudCover`, `Winddirection`, and `Windspeed`. The Step-5.4 Slurm array defaults to two concurrent tasks, each with 8 CPUs and 32 GB:

```bash
BIOOTON_STEP54_MAX_CONCURRENT_TASKS=1 bash run_horeka.sh add_new_ids
```

## Bioacoustics

Bioacoustics is enabled by default and uses Bacpipe `1.3.1`. CPU inference is the default; GPU resources are optional. The configured required classifier models are BirdNET, Perch v2, AudioProtoPNet, and ConvNeXt BirdSet. Insect66 and NatureBeats are staged as optional embedding models. Predictions are model outputs, not confirmed species observations.

Step 6 performs:

```text
6.0 model/checkpoint preflight
 -> 6.1 valid-audio worklist
 -> 6.2 model x shard embeddings/inference array and verification
 -> 6.3 normalized species predictions
 -> 6.4 Germany taxonomy/season filtering
 -> 6.5 per-recording and recording-species aggregation
 -> 6.6 completeness and quality control
```

The default is 16 shards per model, at most four concurrent inference tasks, 16 CPUs and 48 GB per task. Override resources only after checking model memory and LSDF I/O, for example:

```bash
BIOOTON_BIOACOUSTICS_CPUS=16 \
BIOOTON_BIOACOUSTICS_MEMORY=48G \
bash run_horeka.sh add_new_ids
```

See the [Step-6 reference](Readmes/step_6_bioacoustics/README_EN.md) for models, schemas, checkpoints, and interpretation limits.

## Status, validation, release, and reports

Every wrapped step writes a manifest to:

```text
outputs/step_0_manifests/<step_name>/<step_run_id>.json
```

Manifests include workflow/step run IDs, state, timing, Slurm context, Python/package versions, input fingerprints, parameters, log paths, and results. Slurm logs use one UTC submission stamp:

```text
outputs/step_0_slurm_logs/<YYYYMMDDTHHMMSSZ>_<job_name>_<job_id>.out
outputs/step_0_slurm_logs/<YYYYMMDDTHHMMSSZ>_<job_name>_<job_id>.err
```

Array logs additionally contain array job/task IDs. Controller state is stored under `outputs/step_0_control/controllers/`.

Step 7 appends ID lifecycle and tracked status/readiness changes to:

```text
outputs/step_0_control/status_events.csv
```

Final validation examines only manifests from the current workflow and checks required artifacts plus the configured readiness policy. Defaults are report-only, require general/100 m/10 m readiness checks, do not require weather rasters or bioacoustic readiness, and never approve records automatically (`automatic_release: false`). Reports are written to:

```text
outputs/step_9_validation/final_validation_<timestamp>.json
outputs/step_9_validation/final_validation_<timestamp>.md
outputs/step_9_visual_reports/index.html
```

Run the two post-processing stages manually when needed:

```bash
bash run_final_validation_report.sh
.venv/bin/python tools/generate_pipeline_visual_reports.py --config config.horeka.json
```

## Locking, recovery, and safe reruns

The atomic directory lock prevents two writing workflows from running concurrently. Check it with:

```bash
PYTHON="$(bash bootstrap_env.sh | tail -n 1)"
"$PYTHON" tools/pipeline_lock.py --config config.horeka.json status
```

If the controller is interrupted, it intentionally leaves Slurm jobs and the lock untouched. Inspect `tmux`, `squeue`, `sacct`, controller state, and logs first. Force-release only after confirming that no writer remains:

```bash
"$PYTHON" tools/pipeline_lock.py --config config.horeka.json release --force
```

The detailed recovery checklist is in [`HOREKA_RECOVERY_RUNBOOK_DE.md`](HOREKA_RECOVERY_RUNBOOK_DE.md) (German operational runbook). Direct Slurm entry points remain available for recovery/backward compatibility:

```bash
bash slurm_functionality_test.sh
bash slurm_add_new_ids.sh
bash slurm_from_scratch.sh
bash slurm_compare_formation_status.sh
```

These bypass the persistent hybrid controller and call `submit_bio_o_ton_horeka.sh` directly. In this mode, final validation, visual reports, and lock release are themselves Slurm jobs.

For a temporary checkpoint test, cap all requested pipeline walltimes:

```bash
BIOOTON_PIPELINE_TIME_OVERRIDE=00:30:00 bash slurm_add_new_ids.sh
```

## Local Windows workflow

The local orchestrator can run `add_new_ids`, `from_scratch`, or `functionality_test` on Windows while mounting LSDF, generating a path-adjusted configuration, optionally bootstrapping existing HoreKa outputs, and publishing successful outputs back to LSDF.

1. Copy/edit `scripts_local_run/local.settings.example.json` as `scripts_local_run/local.settings.json`.
2. Verify the LSDF host/user, mount drive, local workspace/environment directories, CPU limits, and publication settings.
3. Start from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts_local_run\run_pipeline_local.ps1 -Mode functionality_test
powershell -ExecutionPolicy Bypass -File scripts_local_run\run_pipeline_local.ps1 -Mode add_new_ids
```

Use `-CpuOnly` to disable CUDA preference, `-RefreshHorekaOutputs` to refresh the local baseline, and `-SkipLsdfPublish` to keep successful outputs local. The current local design keeps HOSTRADA raster work on HoreKa (`hostrada_execution: "horeka_only"`). Full local setup, storage/offloading, resume, and publishing behavior is documented in [`scripts_local_run/README.md`](scripts_local_run/README.md) (currently German).

## Configuration and resource overrides

`config.horeka.json` is the production source of paths, thresholds, worker limits, model definitions, and output locations. Do not embed secrets in it; `.secrets/` is ignored. Common runtime overrides include:

| Variable | Default | Purpose |
|---|---:|---|
| `BIOOTON_PARTITION` | `cpuonly` | Core Slurm partition. |
| `BIOOTON_ACCOUNT` | empty | Optional Slurm account. |
| `BIOOTON_STEP2_CPUS` | `16` | Step 2.0/2.1 CPUs. |
| `BIOOTON_STEP3_DOWNLOAD_CPUS` | `16` | Media download CPUs. |
| `BIOOTON_STEP41_CPUS` | `1` | Sentinel mirror CPUs. |
| `BIOOTON_WEATHER_SHARD_COUNT` | config: `8` | Maximum weather shard count. |
| `BIOOTON_WEATHER_MAX_CONCURRENT_TASKS` | config: `4` | Concurrent weather array tasks. |
| `BIOOTON_STEP54_CPUS` | `8` | CPUs per HOSTRADA raster task. |
| `BIOOTON_STEP54_MEMORY` | `32G` | Memory per HOSTRADA raster task. |
| `BIOOTON_STEP54_MAX_CONCURRENT_TASKS` | `2` | Concurrent HOSTRADA raster tasks. |
| `BIOOTON_BIOACOUSTICS_CPUS` | `16` | CPUs per bioacoustic task. |
| `BIOOTON_BIOACOUSTICS_MEMORY` | `48G` | Memory per bioacoustic task. |
| `BIOOTON_BIOACOUSTICS_PARTITION` | core partition | Bioacoustic partition. |
| `BIOOTON_BIOACOUSTICS_GRES` | empty | Optional GPU GRES such as `gpu:1`. |
| `BIOOTON_MASTER_CPUS` | `2` | Master-table job CPUs. |

## Tests and machine-readable contracts

Run the maintained regression suite with:

```bash
bash run_tests.sh
```

The suite covers run planning, locks, manifests, changed-ID handling, incremental upserts, checkpoints, media/weather selection, formation scaling and variants, Sentinel logic, bioacoustics, master-table history, reports, and source integrity. Formal JSON Schema Draft 2020-12 files live in [`schemas/`](schemas/); the master row schema is [`schemas/master_table.schema.json`](schemas/master_table.schema.json).

Before uploading or deploying a changed pipeline package, at minimum run:

```bash
bash run_tests.sh
bash run_horeka.sh functionality_test
bash run_horeka.sh add_new_ids --local-test
```

The last command validates planning and submission construction without consuming Slurm resources.

## Repository map

```text
config.horeka.json              production paths and defaults
pipeline_steps.json             machine-readable step/dependency registry
schemas/                        JSON contracts for rows, manifests, plans, and inventories
scripts/                        data-processing steps
tools/                          planning, orchestration, validation, reporting, and maintenance
scripts_local_run/              Windows/LSDF local runner
Readmes/                        per-step English and German documentation
reference_data/                 maintained taxonomy/reference inputs
tests/                          regression and integrity tests
submit_bio_o_ton_horeka.sh      Slurm DAG constructor
run_horeka.sh                   recommended persistent controller entry point
```

For Git deployment conventions, see [`GITHUB_WORKFLOW.md`](GITHUB_WORKFLOW.md) (currently German). The repository layout is intentionally stable because production configuration and HoreKa deployment paths depend on it.

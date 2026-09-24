# Step 1 Metadata Extraction (EN)

## Purpose
Normalises Dawn Chorus IDs, coordinates and time fields.

## Script
`scripts/Step_1_metadata_extraction.py`

## Inputs
- `PointData/dawn-chorus-soundscape.csv`

## Outputs
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `outputs/step_1_metadata/dawnchorus_metadata_log.csv`

## Dependencies And Invalidation
Logical step contracts are recorded in `pipeline_steps.json` under `step_1_metadata`. The central run planner passes only affected IDs and schedules global work only for changed inputs, result-relevant config or missing outputs.

## Configuration
Result-relevant settings are centralised in `config.horeka.json`: `dawn_chorus_csv`, `status_dir`, `metadata_extraction`. Data paths and scientific thresholds come from the configuration. Slurm resource defaults and BIOOTON_* overrides are resolved by the launcher and optional cluster profile.

Step 1 processes only rows whose configured country column matches the
configured target country (by default, `country = Germany`). The step fails if
the country column is absent. If a previously processed ID changes to another
country, it is removed from the Step 1 outputs and therefore cannot appear in
the next master-table update.

## Execution
`bash slurm_add_new_ids.sh` starts the incremental core phase; `bash slurm_from_scratch.sh` rebuilds the core. Step 6 starts separately with `bash slurm_bioacoustics.sh`. An isolated technical direct run is available with:
- `python scripts/Step_1_metadata_extraction.py --config config.horeka.json`

## Batch And Parallel Execution
`SLURM_CPUS_PER_TASK` limits effective parallelism. The step uses no more processes/workers than configured. IDs or chunks have unique status/checkpoint keys, while the global pipeline lock prevents concurrent writing workflows.

## Checkpoint/Resume
New IDs are added incrementally; `from_scratch` uses `--force`.

## Quality Control
Output existence alone is not treated as validity. Compact and detailed logs, batch status files and the run manifest record validation and failures. `bash run_final_validation_report.sh` creates the final gate; formation products can additionally be compared with `bash slurm_compare_formation_status.sh`.

## Status, Manifests And Master Table
The Slurm orchestrator writes a manifest under `outputs/step_0_manifests/<step>/<step_run_id>.json` containing the `workflow_run_id`, inputs, parameters, runtime, logs and outputs. Step 7 summarises ID-level results in the master table while technical detail remains in step logs. Canonical run statuses are defined in `scripts/common.py`; `schemas/status_model.json` defines status-event fields.

## Typical Failures
Missing inputs or configuration sections terminate the step with a non-zero exit code. Per-ID data problems are recorded where possible in detail/retry logs as `missing`, `has_issues` or `failed`. After a timeout, resubmit the same mode; valid checkpoints are reused.

## German recording-time policy (2026-09-16)

`localtimes` is authoritative when nonempty: preserve its local clock and apply
Europe/Berlin DST rules. Only missing local values use `datetime` as an instant
and convert it to Europe/Berlin. A datetime without an offset is assumed UTC and
explicitly flagged; no such rows occur in the audited September input.
Malformed/nonexistent local clocks and unresolved autumn folds remain invalid;
there is no silent fallback or one-hour shift. A valid local offset, otherwise a
matching UTC reference, resolves the autumn fold. Conflicting UTC references and
non-German local offsets are logged, while the local clock remains authoritative.
`coordinate_check` is only a WGS84 / broad Germany rectangle plausibility check,
not a country-border or timezone-polygon test.

The clean intermediate `datetime` retains the correct +01:00/+02:00 offset.
The master `datetime_local` stores only the German clock, without an offset.
Planner and extraction share fingerprints. A policy change invalidates metadata,
weather and Sentinel planning. The first migration therefore revisits existing IDs,
not only newly added IDs. A scoped extraction never acknowledges untouched IDs.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `datetime_timezone_missing_assumed_utc` | datetime has no offset and is interpreted as UTC, with a warning. | [recording_time.py:56](../../scripts/recording_time.py) |
| `localtimes_unparseable` | Nonempty localtimes cannot be parsed; no silent UTC fallback. | [recording_time.py:64](../../scripts/recording_time.py) |
| `nonexistent_localtime` | Local clock falls in the skipped spring hour and remains invalid. | [recording_time.py:74](../../scripts/recording_time.py) |
| `ambiguous_localtime_unresolved` | Repeated autumn hour cannot be resolved by offset/UTC; timestamp stays invalid. | [recording_time.py:91](../../scripts/recording_time.py) |
| `localtimes_offset_mismatch` | Supplied local offset disagrees with Europe/Berlin; local clock remains authoritative. | [recording_time.py:93](../../scripts/recording_time.py) |
| `utc_reference_unavailable` | No usable UTC reference for cross-checking. | [recording_time.py:95](../../scripts/recording_time.py) |
| `datetime_missing_or_unparseable` | With no local clock supplied, datetime is also unusable. | [recording_time.py:99](../../scripts/recording_time.py) |
| `utc_local_conflict` | UTC reference conflicts with local clock; localtimes remains authoritative. | [recording_time.py:110](../../scripts/recording_time.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `within_broad_germany_bounds` | `Emitted by build_outputs` | [Step_1_metadata_extraction.py:115](../../scripts/Step_1_metadata_extraction.py) |
| `outside_broad_germany_bounds` | `Emitted by build_outputs` | [Step_1_metadata_extraction.py:116](../../scripts/Step_1_metadata_extraction.py) |
| `invalid_wgs84_coordinates` | `Emitted by build_outputs` | [Step_1_metadata_extraction.py:117](../../scripts/Step_1_metadata_extraction.py) |
| `invalid` | `Emitted by resolve_recording_time` | [recording_time.py:111](../../scripts/recording_time.py) |
| `warning` | `Emitted by resolve_recording_time` | [recording_time.py:111](../../scripts/recording_time.py) |
| `validated` | `Emitted by resolve_recording_time` | [recording_time.py:111](../../scripts/recording_time.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_1_metadata_extraction.py:52](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Missing required Dawn Chorus column: id` | `'id' not in source.columns` | [Step_1_metadata_extraction.py:155](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Missing required Dawn Chorus country column: {country_column}` | `country_column not in source.columns` | [Step_1_metadata_extraction.py:157](../../scripts/Step_1_metadata_extraction.py) |
| `FileNotFoundError: IDs file not found: {path}` | `not path.is_file()` | [Step_1_metadata_extraction.py:256](../../scripts/Step_1_metadata_extraction.py) |
| `KeyError: No dawn_chorus_id/id column in {path}` | `Emitted by read_ids_file` | [Step_1_metadata_extraction.py:265](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: This pipeline requires country Germany and timezone Europe/Berlin` | `timezone != DEFAULT_TIMEZONE or country_value != 'Germany'` | [Step_1_metadata_extraction.py:332](../../scripts/Step_1_metadata_extraction.py) |
| `FileNotFoundError: Dawn Chorus CSV not found: {input_csv}` | `not input_csv.is_file()` | [Step_1_metadata_extraction.py:344](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Germany recordings require timezone Europe/Berlin` | `timezone != GERMAN_TIMEZONE` | [recording_time.py:48](../../scripts/recording_time.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `1` | `except Exception` | [Step_1_metadata_extraction.py:445](../../scripts/Step_1_metadata_extraction.py) |
| `0` | `Emitted by main` | [Step_1_metadata_extraction.py:483](../../scripts/Step_1_metadata_extraction.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->

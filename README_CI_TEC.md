# Master table

ci-tec | internal README | 13.10.2026 | Master schema v7 (normative PDF revised 13.10.2026)

Use **Bio_O_Ton_Master.csv**, one row per recording. No separate ci-tec table is required. This is the latest recorded inventory, not a guarantee that processing is finished. Original metadata source: dawn-chorus-soundscape.csv.

| Column | Meaning |
|---|---|
| `dawn_chorus_id` | Recording ID. |
| `lon`, `lat` | WGS84 coordinates in decimal degrees. |
| `grid_100m_id`, `grid_10m_id` | Assigned grid cells. A grid ID does not imply that LRT formation data are available. |
| `datetime_local` | German local date and clock time in Europe/Berlin, stored without a timezone suffix. Its origin is recorded separately in timestamp_source. |
| `datetime_utc` | UTC instant derived from the chosen Europe/Berlin recording clock; `datetime` values mislabeled +00:00 are first localized to Germany. |
| `timestamp_source` | Exact values: localtimes for an explicitly supplied local clock; datetime for the source fallback. The zero-offset datetime label can be misleading; see time repair policy below. |
| `time_has_issues` | False for structurally valid, QC-checked recording times regardless of `timestamp_source`; True for invalid, missing, ambiguous or conflicting times. |
| `duration_seconds` | Checked audio duration in seconds; null if unavailable. |
| `inside_lrt_polygon` | Recording point lies within an included LRT polygon. |
| `grid_100m_has_majority_formation`, `grid_10m_has_majority_formation` | Majority formation is available for this cell; different from a direct point/LRT intersection. |

Grid embeddings, the LRT GeoPackage and grid reference data are separate products. Recording/bioacoustic flags do not certify their completeness.

## Recording time: source and German clock

The original Dawn Chorus column is named **localtimes** (the supplied local time). **Only when this field is absent, empty or whitespace-only** does Step 1 use **datetime** as a fallback. Website spot-checks on 13 October 2026 showed that the zero-offset (`Z` / `+00:00`) annotation on these fallback values labels a **German wall clock**; their clock components must be localized to **Europe/Berlin without first shifting the hour**. A nonzero offset is still treated as an actual offset-aware instant. Local time is exported without suffix as `YYYY-MM-DD HH:MM:SS` (normative attached PDF). For the reviewed zero-offset class, source-wide consistency was checked across 3,288 recordings, with 14 independent website spot-checks; valid corrected fallbacks are not flagged solely for source provenance. DST gaps and unresolved folds are invalid and not guessed.

Examples without localtimes: `2025-01-15T06:00:00Z` becomes `2025-01-15 06:00:00` (UTC `05:00Z`); `2025-07-15T06:00:00Z` becomes `2025-07-15 06:00:00` (UTC `04:00Z`). The original local calendar day is retained for these mislabeled zero-offset clocks.

When localtimes is supplied, its local clock retains priority and is interpreted as German time. These recordings are unchanged by the fallback rule. A nonempty but invalid or unresolved localtimes value is flagged; it is not silently replaced with datetime. Source conflicts remain visible in the Step-1 time log.

**Historical audit superseded (28.09.2026):** its assertion that all 3,288 `datetime` fallbacks were correctly UTC-converted was contradicted by 14 manual Dawn Chorus website checks on 13.10.2026. The v4 QC policy preserves the displayed clock for affected zero-offset fallbacks, applies German DST to derive real UTC, and leaves actual validation conflicts flagged. This source-wide algorithm check is not a website validation of every recording. Re-run the time audit and downstream date-dependent QC before publishing a new master.

## Clean-data filters from the normative 13 October PDF

Apply the filters needed by your analysis:

```text
time_has_issues=False
sound_exists=True
duration_seconds >= 40
sound_has_issues=False
weather_point_exists=True
weather_point_has_issues=False
sentinel_exists=True
sentinel_has_issues=False
```

The 40-second threshold is an analysis choice and can be replaced. Domain flags
do not automatically invalidate the entire recording. For training in cells with
a majority formation add `grid_100m_has_majority_formation=True`; for direct
point-in-LRT training add `inside_lrt_polygon=True`. Grid IDs alone certify neither.

## Recording-time confidence and weather use

**Use weather data only for recordings with** `time_has_issues=False`, as specified in the revised normative PDF. `timestamp_source` records the origin (localtimes/datetime) and is never by itself a reason to set the quality flag. The 3,288 zero-offset datetime fallbacks in the supplied Germany export passed deterministic timezone/DST and source-to-output validation; 14 examples were independently checked against the website. Some `localtimes` records contain genuine cross-field contradictions and remain flagged; no claim is made that every source recording was individually website-verified.

This source restriction supplements weather availability and quality checks. In schema v7, combined readiness flags include it. It does not automatically exclude the recording from audio-only work, and the audio-only bioacoustic readiness flag remains independent of time confidence. Recordings and stored files remain in the shared master.

## Availability and issues

**_exists**: `True` means the corresponding files were recorded as present on LSDF. These flags describe the recorded inventory, not a live file check.

**_has_issues**: `True` means a problem or missing required data/check results. It can be `True` whether `_exists` is `True` or `False`.

Empty means no check result is available.

**_issue_codes** gives the reason. Multiple codes are separated by a pipe; details may follow a colon. **_has_issues is not a severity level or a universal exclusion rule.** Rules below concern the affected file/domain, not automatically the entire recording. Unknown codes or a True issue flag without codes require review.

| Columns | Data |
|---|---|
| `sound_exists`, `sound_has_issues` | Audio file and audio checks. |
| `sentinel_exists`, `sentinel_has_issues` | Sentinel-2 files and technical checks. |
| `weather_point_exists`, `weather_point_has_issues` | Weather file for the recording and its checks. |

Sound examples:

- `True / False`: file found, no issues reported.
- `True / True`: file found, but a technical property or decoding check failed.
- `False / True`: file missing.

## Sound codes and suggested use

| sound_issue_codes | Meaning / consequence |
|---|---|
| `duration_not_60s` | Outside 59-61 seconds. **Information**; decide in application-specific preprocessing. Not a general exclusion. |
| `missing_file` | File absent: unavailable. |
| `empty_file`, `no_audio_stream_found`, `no_audio_frames_decoded` | No usable audio in the checked file: exclude that file pending repair. |
| `pyav_decode_failed`, `invalid_or_missing_sample_rate`, `invalid_or_missing_channel_count`, `invalid_duration`, `duration_unavailable` | Technical check failed or a property could not be established: hold for review. Does not prove the original source is permanently corrupt. |
| `multiple_audio_streams` | Select the intended stream before use. |
| `filename_does_not_match_<id>_audio_pattern` | File-to-ID association needs clarification. |
| `source_stat_failed`, `copy_failed`, `WinError` | Access/copy problem; investigate connection and download before concluding source corruption. |

**PDF audio filter:** sound_exists=True, duration_seconds >= 40, sound_has_issues=False. A pure duration_not_60s note does not set the issue flag. Shorter or longer files can be usable; change the duration threshold for your analysis. Technical codes still require review.

## Point weather codes and suggested use

Expected window: ten preceding complete German calendar days plus the recording day, hourly. Normally 264 rows; across spring DST 263, across autumn DST 265. The repeated local autumn hour is valid; a timezone-free timestamp alone cannot distinguish its two UTC instants.

| weather_point_issue_codes | Meaning / consequence |
|---|---|
| `missing_file` | No weather file. Cause is not established by this code. |
| `missing_value` | At least one required value is missing. **Information only:** this code alone does not set weather_point_has_issues. Check variables/hours needed by the application; do not fill values blindly. |
| `recording_date_changed_recheck_required` | Recording date changed while previous results were retained. Temporal association is unconfirmed: hold until rechecked. |
| `unexpected_time_interval` | Full timestamp sequence and multiplicities differ from the expected window. May mean missing, extra or shifted hours. Correct DST transitions are accepted by the current inventory. **Check/correct before use.** |
| `unexpected_time_window`, `unexpected_row_count` | Wrong boundaries or row count: check/correct before use. |
| `duplicate_datetime` | More repeats than allowed by the expected window, not the legitimate repeated autumn hour. Check/correct before use. |
| `missing_required_column`, `missing_datetime_column`, `unparseable_datetime`, `invalid_metadata_datetime` | Structure or time basis is unreliable: hold until clarified. |
| `empty_file`, `read_error` | Empty or unreadable; an exception suffix may follow read_error. File currently unusable. |
| `implausible_value` | Temperature/humidity range check failed. Investigate values and source before deciding usability. |

**PDF weather filter:** time_has_issues=False, weather_point_exists=True and weather_point_has_issues=False. This permits missing_value as an informational code; verify the variables/hours your analysis needs. A stricter application can additionally require no codes. Additional time/structure errors remain blocking.

## Sentinel

| Code / field | Meaning / consequence |
|---|---|
| Sentinel: `missing_file`, `score_without_tif` | Image missing; a score does not replace it. |
| Sentinel: `too_cloudy_sentinel_not_available` | Quality score is exactly 0: too cloudy, Sentinel data unavailable for use. The numeric score stays 0; sentinel_has_issues=True. sentinel_exists still reports physical file presence. |
| Sentinel: `quality_score_missing` | Image may exist, but its quality assessment is missing. |
| Sentinel: `empty_file`, `raster_read_failed` | Image empty or unreadable: exclude pending repair. |
| `inventory_not_run`, `qc_not_run` | Check results unavailable; not equivalent to passing QC. |

Weather and Sentinel do not automatically exclude a recording from audio/LRT-only work. Photos are not a filter criterion for the stated ci-tec priorities.

## Processing completion is separate from quality

**is_final does not currently exist.** ready_for_general_analysis is not a ci-tec release flag: it requires validated time plus unflagged sound, weather and Sentinel together. It does not enforce an analysis-specific audio duration threshold; apply duration_seconds >= 40 separately for the PDF clean filter.

Completion requires finished processing and checks for the required products, a specified input/code version and no outstanding repairs. Missing data and suitability remain separate. A permanent release applies only to a frozen version; later versions can reveal new errors. The shared master retains all rows.

## Sentinel date migration safety (v3)

A recording whose effective UTC **calendar date** has changed must not silently reuse an old Sentinel scene selected under the earlier date. The master marks `sentinel_has_issues=True` and adds `recording_date_changed_recheck_required` to `sentinel_issue_codes`. This warning persists until the scene is independently regenerated/reviewed and an operator supplies an **explicit** `master_table.sentinel_time_rechecked_ids_csv` CSV containing `dawn_chorus_id,reviewed` with `reviewed=True` for the verified recordings. Never treat a successful mirror of an old tile as confirmation of a newly chosen GEE scene. The 13.10.2026 PDF's Sentinel clean filters remain unchanged.

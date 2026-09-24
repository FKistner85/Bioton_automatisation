# Master table

ci-tec | README | 24.09.2026

Use **Bio_O_Ton_Master.csv**, one row per recording. No separate ci-tec table is required. This is the latest recorded inventory, not a guarantee that processing is finished. Original metadata source: dawn-chorus-soundscape.csv.

| Column | Meaning |
|---|---|
| `dawn_chorus_id` | Recording ID. |
| `lon`, `lat` | WGS84 coordinates in decimal degrees. |
| `grid_100m_id`, `grid_10m_id` | Assigned grid cells. A grid ID does not imply that LRT formation data are available. |
| `datetime_local` | German local date and clock time, with summer/winter time accounted for. No timezone suffix. Example: `2025-03-01 16:03:00`. |
| `inside_lrt_polygon` | Recording point lies within an included LRT polygon. |
| `grid_100m_has_majority_formation`, `grid_10m_has_majority_formation` | Majority formation is available for this cell; different from a direct point/LRT intersection. |

Grid embeddings, the LRT GeoPackage and grid reference data are separate products. Recording/bioacoustic flags do not certify their completeness.

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
| `weather_raster_hostrada_100m_exists`, `weather_raster_hostrada_100m_has_issues` | HOSTRADA raster collection and its checks. These flags describe the whole collection and repeat for every recording. |

Sound examples:

- `True / False`: file found, no issues reported.
- `True / True`: file found, but for example its duration is outside 59-61 seconds.
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

**Proposed audio filter:** sound_exists=True and either sound_has_issues=False with no codes, or duration_not_60s as the only code. Do not overlook additional codes. This is a proposed usage rule for agreement, not an existing release approval.

## Point weather codes and suggested use

Expected window: ten preceding complete German calendar days plus the recording day, hourly. Normally 264 rows; across spring DST 263, across autumn DST 265. The repeated local autumn hour is valid; a timezone-free timestamp alone cannot distinguish its two UTC instants.

| weather_point_issue_codes | Meaning / consequence |
|---|---|
| `missing_file` | No weather file. Cause is not established by this code. |
| `missing_value` | At least one required value is missing. **Potentially usable in part**: check variables/hours needed by the application. Do not fill values blindly. |
| `recording_date_changed_recheck_required` | Recording date changed while previous results were retained. Temporal association is unconfirmed: hold until rechecked. |
| `unexpected_time_interval` | Full timestamp sequence and multiplicities differ from the expected window. May mean missing, extra or shifted hours. Correct DST transitions are accepted by the current inventory. **Check/correct before use.** |
| `unexpected_time_window`, `unexpected_row_count` | Wrong boundaries or row count: check/correct before use. |
| `duplicate_datetime` | More repeats than allowed by the expected window, not the legitimate repeated autumn hour. Check/correct before use. |
| `missing_required_column`, `missing_datetime_column`, `unparseable_datetime`, `invalid_metadata_datetime` | Structure or time basis is unreliable: hold until clarified. |
| `empty_file`, `read_error` | Empty or unreadable; an exception suffix may follow read_error. File currently unusable. |
| `implausible_value` | Temperature/humidity range check failed. Investigate values and source before deciding usability. |

**Strict weather filter:** weather_point_exists=True and weather_point_has_issues=False with no codes. **Optional partial-data filter:** permit missing_value as the only code, then check required values yourself. Do not permit additional time/structure errors. New recordings do not necessarily lack files, and old recordings do not necessarily have NaN files.

## Grid weather and Sentinel

| Code / field | Meaning / consequence |
|---|---|
| `weather_raster_hostrada_100m_*` | Collection-wide status repeated across recordings. Many flagged rows do not mean that many independently corrupt raster files. |
| `missing_raster`, `all_nodata` | Raster missing or containing only NoData: affected product unavailable. |
| `unexpected_shape`, `raster_structure_warning`, `raster_qc_read_error`, `qc_not_run` | Raster structure/check needs review in the detailed raster QC. |
| Sentinel: `missing_file`, `score_without_tif` | Image missing; a score does not replace it. |
| Sentinel: `quality_score_missing` | Image may exist, but its quality assessment is missing. |
| Sentinel: `empty_file`, `raster_read_failed` | Image empty or unreadable: exclude pending repair. |
| `inventory_not_run`, `qc_not_run` | Check results unavailable; not equivalent to passing QC. |

Weather and Sentinel do not automatically exclude a recording from audio/LRT-only work. Photos are not a filter criterion for the stated ci-tec priorities.

## Processing completion is separate from quality

**is_final does not currently exist.** ready_for_general_analysis is not a ci-tec release flag: it requires unflagged sound, weather and Sentinel together and also rejects pure duration warnings.

For agreement: completion should mean that processing and checks for the required products and a specified input/code version are finished, with no outstanding repair. Missing data and application suitability remain separate questions. An irreversible True is only defensible for a frozen, versioned release. A new data version must be able to expose newly discovered errors. No rows are removed from the shared master under the proposed rules.

## Abstimmung mit ci-tec: bitte bestätigen

**Vorschläge, noch keine bestätigte Freigabe.** Gemeinsame Datei: **Bio_O_Ton_Master.csv**. Ein Ausschluss betrifft zunächst den jeweiligen Datenbereich, nicht automatisch die gesamte Aufnahme.

| Entscheidung | Vorschlag zur Bestätigung |
|---|---|
| 1. Audio auswählen | `sound_exists=True`; keine Issues oder ausschließlich `duration_not_60s`. Dauerabweichung ist ein Hinweis. Leere, nicht dekodierbare oder technisch ungeklärte Audiodateien bis zur Klärung ausschließen. |
| 2. Wetter mit Lücken | `missing_value` als einzigen Code anwendungsspezifisch zulassen: benötigte Variablen und Stunden prüfen. Alternativ nur vollständig ungeflaggtes Wetter nutzen. Keine automatische Auffüllung. |
| 3. Zeit- und Strukturfehler | `unexpected_time_interval`, `unexpected_time_window`, `unexpected_row_count`, `duplicate_datetime`, `recording_date_changed_recheck_required` und Lese-/Strukturfehler bis zur Korrektur ausschließen. Korrekte Sommer-/Winterzeitwechsel sind kein Fehler. Fehlende Dateien sind nicht verfügbar. |
| 4. Benötigte Produkte und Abschluss | Für reine Audio-/LRT-Auswertung fehlendes Wetter oder Sentinel nicht pauschal ausschließen; Fotos sind kein Auswahlkriterium. LRT-Zuordnung separat prüfen. Abschluss pro benötigtem Produkt und festgelegter Version definieren; kein pauschales `is_final`. |

**Zusammengeführter Stand vom 24.09.2026:** 111.866 Aufnahmen; 6.430 mit 100-m-Mehrheitsformation, 1.154 direkt innerhalb eines LRT-Polygons und 2.211 mit 10-m-Mehrheitsformation. Aufnahmezeiten bleiben unverändert in deutscher Ortszeit. Beim Punktwetter tragen 2.615 Aufnahmen ausschließlich `missing_value`; die zuvor gemeldeten Wetter-Zeitfehler sind in diesem geprüften Stand bereinigt. Fehlende Werte bleiben fehlend.

Offene Festlegung für ci-tec: Welche Wettervariablen und Stunden müssen für die konkrete Auswertung vollständig sein? Die oben erläuterten Issue-Codes bleiben erhalten; es wird keine zweite gefilterte Master erzeugt.

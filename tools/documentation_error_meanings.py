"""Reviewed meanings of diagnostic tokens; suffixes carry runtime details."""
_DATA = """
HTTPError:|HTTP-Download fehlgeschlagen; Suffix enthaelt Status und Servermeldung. Retry-Regeln beachten.|HTTP download failed; suffix contains status and server message. Follow retry policy.
WinError |Vom Inventar als Windows-/Netztransportproblem eingestuft; Mount/Verbindung pruefen statt Dateidefekt anzunehmen.|Classified by inventory as a Windows/network transport problem; inspect mount/connectivity rather than assuming corrupt media.
all_nodata|Mindestens ein QC-Band besteht nur aus NoData.|At least one QC band contains only NoData.
all_pixels_nodata|Alle geprueften Rasterpixel sind NoData.|All inspected raster pixels are NoData.
ambiguous_localtime_unresolved|Doppelte Herbststunde ohne eindeutigen Offset/UTC-Abgleich; Zeitpunkt bleibt ungueltig.|Repeated autumn hour cannot be resolved by offset/UTC; timestamp stays invalid.
bacpipe_ensure_models_exist_unavailable|Bacpipe bietet die erwartete Checkpoint-Bereitstellung nicht an.|Expected Bacpipe checkpoint provisioning API is unavailable.
bacpipe_import_failed|Bacpipe konnte nicht importiert werden.|Bacpipe could not be imported.
bacpipe_version_mismatch|Installierte und konfigurierte Bacpipe-Version unterscheiden sich.|Installed and configured Bacpipe versions differ.
bioacoustic_qc_not_run|Es liegt kein verwendbares kompaktes Bioakustik-QC vor.|No usable compact bioacoustic QC is available.
bioacoustic_result_missing|Fuer diese Master-ID fehlt ein QC-Ergebnis.|This master ID has no matching QC result.
constant_raster|Alle gueltigen Rasterwerte sind identisch; Plausibilitaet pruefen.|All valid raster values are identical; check plausibility.
contains_infinite_values|Raster enthaelt unendliche Werte.|Raster contains infinite values.
contains_nan_values|Raster enthaelt NaN-Werte.|Raster contains NaN values.
coordinates_missing_or_invalid|Master-Koordinaten fehlen oder liegen ausserhalb gueltiger WGS84-Grenzen.|Master coordinates are missing or outside valid WGS84 bounds.
copy_failed|Dateikopie ist fehlgeschlagen.|File copy failed.
copy_size_mismatch|Dateigroessen von Quelle und Kopie stimmen nicht ueberein.|Source and copied file sizes differ.
copy_verification_failed|Die Kontrolle nach dem Kopieren ist fehlgeschlagen.|Verification after copying failed.
datetime_missing_or_unparseable|Ohne lokale Zeit ist auch datetime nicht nutzbar.|With no local clock supplied, datetime is also unusable.
datetime_timezone_missing_assumed_utc|datetime hat keinen Offset und wird als UTC interpretiert; Warnung bleibt sichtbar.|datetime has no offset and is interpreted as UTC, with a warning.
destination_missing_after_copy|Zieldatei fehlt nach dem Kopierversuch.|Destination is missing after the copy attempt.
duplicate_datetime|Mehr Zeitstempelduplikate als im lokalen DST-Fenster zulaessig.|More duplicate timestamps than allowed by the local DST window.
duplicate_score_rows|Mehrere Score-Zeilen fuer dieselbe ID.|Multiple score rows for the same ID.
duplicate_tif_files_for_id|Mehrere TIFF-Dateien sind derselben Aufnahme zugeordnet.|Multiple TIFF files are assigned to the same recording.
duplicate_valid_audio_for_id|Weitere valide Audiodatei fuer dieselbe ID; nur die ausgewaehlte Datei kommt in die Worklist.|Extra valid audio for an ID; only the selected file enters the worklist.
duration_not_|Audiodauer liegt ausserhalb Zielwert plus/minus Toleranz; Werte stehen im Code.|Audio duration is outside target plus/minus tolerance; values are included.
duration_unavailable|Audiodauer konnte nicht bestimmt werden.|Audio duration could not be determined.
empty_file|Vorhandene Datei hat null Bytes.|Existing file has zero bytes.
failed_ids=|Shard-State enthaelt fehlgeschlagene IDs.|Shard state contains failed IDs.
filename_does_not_contain_id_before_tif_extension|TIFF-Dateiname liefert keine erwartete Aufnahme-ID.|TIFF filename does not supply the expected recording ID.
filename_does_not_match_<id>_audio_pattern|Audio-Dateiname entspricht nicht dem erwarteten ID-Muster.|Audio filename does not match the expected ID pattern.
filename_does_not_match_<id>_photo_pattern|Foto-Dateiname entspricht nicht dem erwarteten ID-Muster.|Photo filename does not match the expected ID pattern.
filename_does_not_match_weather_id_pattern|Wetter-Dateiname entspricht nicht dem erwarteten ID-Muster.|Weather filename does not match the expected ID pattern.
grid_100m_missing_majority_formation|Keine 100-m-Mehrheitsformation; das bedeutet nicht zwingend fehlende Grid-ID.|No 100 m majority formation; this does not necessarily mean no grid ID.
grid_10m_missing_majority_formation|Keine 10-m-Mehrheitsformation; das bedeutet nicht zwingend fehlende Grid-ID.|No 10 m majority formation; this does not necessarily mean no grid ID.
identity_geotransform|Raster besitzt nur die Identitaetstransformation; Georeferenzierung pruefen.|Raster has an identity transform; check georeferencing.
image_verify_failed|Pillow-Dateipruefung fehlgeschlagen.|Pillow image verification failed.
implausible_value|Mindestens ein Wert verletzt konfigurierte Plausibilitaetsgrenzen.|At least one value violates configured plausibility limits.
invalid_bounds|Rastergrenzen haben keine gueltige raeumliche Ausdehnung.|Raster bounds do not define a valid extent.
invalid_dimensions|Raster-/Bildbreite oder -hoehe ist ungueltig.|Raster/image width or height is invalid.
invalid_duration|Ermittelte Audiodauer ist nicht positiv.|Determined audio duration is not positive.
invalid_metadata_datetime|Aufnahmezeit aus Metadaten ist fuer das Wetterfenster ungueltig.|Metadata recording time is invalid for the weather window.
invalid_or_missing_channel_count|Audiokanalzahl fehlt oder ist nicht positiv.|Audio channel count is missing or nonpositive.
invalid_or_missing_sample_rate|Samplingrate fehlt oder ist nicht positiv.|Sample rate is missing or nonpositive.
inventory_issue|Worklist verwirft Audio; Detailgruende aus dem Inventar fehlen.|Worklist rejects audio without more specific inventory details.
inventory_not_run|Kein verwendbares kompaktes Inventar vorhanden.|No usable compact inventory is available.
localtimes_offset_mismatch|Mitgelieferter lokaler Offset passt nicht zu Europe/Berlin; lokale Uhrzeit bleibt massgeblich.|Supplied local offset disagrees with Europe/Berlin; local clock remains authoritative.
localtimes_unparseable|Nichtleere localtimes ist unlesbar; kein stiller UTC-Fallback.|Nonempty localtimes cannot be parsed; no silent UTC fallback.
master_missing_column|Aktivierte Readiness-Pruefung benoetigt eine fehlende Master-Spalte.|An enabled readiness check requires a missing master column.
master_table_missing_or_empty|Masterdatei fehlt oder ist leer.|Master file is missing or empty.
master_table_read_error|Masterdatei konnte nicht gelesen werden.|Master file could not be read.
missing_audio_url|Fuer den Audio-Download fehlt eine URL.|Audio download URL is missing.
missing_crs|Raster hat kein Koordinatenreferenzsystem.|Raster has no coordinate reference system.
missing_datetime_column|Wetter-CSV enthaelt keine datetime-Spalte.|Weather CSV has no datetime column.
missing_file|Erwartete Datei fehlt.|Expected file is missing.
missing_photo_url|Fuer den Foto-Download fehlt eine URL.|Photo download URL is missing.
missing_raster|Keine erwarteten HOSTRADA-Raster vorhanden.|Expected HOSTRADA rasters are absent.
missing_required_column|Mindestens eine konfigurierte Pflichtspalte fehlt.|At least one configured required column is missing.
missing_rows=|Erwartete Work-Keys sind im Shard nicht abgeschlossen.|Expected work keys are not completed in the shard.
missing_state|Erwartete Shard-State-Datei fehlt oder ist nicht nutzbar.|Expected shard state file is missing or unusable.
missing_value|Werte fehlen; massgeblich ist die jeweilige Pruefung bzw. NaN-Toleranz.|Values are missing; the specific check or NaN tolerance determines failure.
model_checkpoint_dir_not_accessible|Checkpoint-Verzeichnis hat nicht die benoetigten Zugriffsrechte.|Checkpoint directory lacks required access permissions.
model_inference_failed|Mindestens ein Modell meldet einen Inferenzfehler fuer die ID.|At least one model reports an inference failure for the ID.
multiple_audio_streams|Datei enthaelt mehrere Audiostreams.|File contains multiple audio streams.
no_audio_frames_decoded|Decoder lieferte keine Audioframes.|Decoder returned no audio frames.
no_audio_stream_found|Kein Audiostream in der Datei gefunden.|No audio stream found in the file.
no_raster_bands|Raster enthaelt keine Baender.|Raster contains no bands.
no_valid_quality_score|Kein gueltiger Sentinel-Score in den vorhandenen Zeilen.|No valid Sentinel score among existing rows.
non_finite_bounds|Rastergrenzen enthalten NaN oder unendliche Werte.|Raster bounds contain NaN or infinite values.
non_numeric_or_missing_scores|Scorewerte sind nicht numerisch oder fehlen.|Score values are nonnumeric or missing.
nonexistent_localtime|Lokale Uhrzeit faellt in die uebersprungene Fruehlingsstunde; bleibt ungueltig.|Local clock falls in the skipped spring hour and remains invalid.
pixel_load_failed|Bildheader lesbar, aber Pixel konnten nicht geladen werden.|Image pixels could not be loaded after header inspection.
pyav_decode_failed|PyAV konnte Audio nicht vollstaendig decodieren.|PyAV could not decode the audio successfully.
qc_not_run|Raster vorhanden, aber QC-Ergebnis fehlt.|Raster exists but QC result is missing.
quality_score_missing|Fuer die Aufnahme liegt kein Score vor.|No score is available for the recording.
raster_qc_read_error_|Raster-QC-Datei konnte nicht gelesen werden.|Raster QC file could not be read.
raster_read_failed|Raster konnte nicht geoeffnet oder gelesen werden.|Raster could not be opened or read.
raster_structure_warning|QC meldet konstante oder reine NoData-Zeilen/-Spalten.|QC reports constant or all-NoData rows/columns.
read_error|Datendatei konnte nicht gelesen werden; Exception-Typ steht im Suffix.|Data file could not be read; suffix identifies exception type.
recording_date_changed_recheck_required|Lokales Aufnahmedatum geaendert; erhaltene Wetter-/Sentinel-Ergebnisse erneut pruefen.|Local recording date changed; recheck retained weather/Sentinel products.
required_model_initialisation_failed|Pflichtmodell bzw. unter require_all_models jedes Modell kann nicht initialisiert werden.|Required model, or any model under require_all_models, cannot initialise.
required_models_incomplete|Mindestens ein Pflichtmodell ist fuer die Aufnahme nicht abgeschlossen.|At least one required model is incomplete for the recording.
score_rows_with_invalid_id|Scoredatei enthaelt Zeilen ohne gueltige ID.|Score file contains rows with invalid IDs.
scores_outside_0_1|Numerische Sentinel-Scores liegen ausserhalb 0 bis 1.|Numeric Sentinel scores lie outside 0 to 1.
shard_count_mismatch|Gespeicherte und konfigurierte Shardzahl unterscheiden sich.|Stored and configured shard counts differ.
source_stat_failed|Quelldatei konnte nicht per Dateisystem-Stat abgefragt werden.|Filesystem stat failed for the source file.
state=|Shard-State hat nicht den erwarteten Status complete.|Shard state is not the expected complete status.
task_error|Shard-State enthaelt einen Fehler des gesamten Tasks.|Shard state contains a task-level error.
timestamp_missing_or_invalid|Mindestens ein benoetigter Zeitwert im Master fehlt oder ist ungueltig.|A required master timestamp is missing or invalid.
torch_import_failed|PyTorch konnte nicht importiert werden.|PyTorch could not be imported.
unexpected_raster_driver|Rasterformat ist nicht GTiff.|Raster driver is not GTiff.
unexpected_row_count|Zeilenzahl entspricht nicht dem erwarteten Wetterfenster.|Row count does not match the expected weather window.
unexpected_shape|QC meldet ein nicht quadratisches Raster.|QC reports a nonsquare raster.
unexpected_time_interval|Zeitstempel einschliesslich ihrer Haeufigkeit entsprechen nicht dem vollstaendigen erwarteten lokalen Wetterfenster. Korrekte Sommer-/Winterzeitwechsel sind erlaubt; Code allein unterscheidet fehlende, zusaetzliche und verschobene Stunden nicht.|Timestamps and their multiplicities do not match the complete expected local weather window. Correct DST transitions are allowed; this code alone does not distinguish missing, extra or shifted hours.
unexpected_time_window|Zeitstempel decken nicht das berechnete lokale Wetterfenster ab.|Timestamps do not cover the calculated local weather window.
unparseable_datetime|Zeitstempel in der Datendatei sind nicht parsebar.|Timestamps in the data file cannot be parsed.
utc_local_conflict|UTC-Referenz widerspricht der lokalen Uhr; localtimes bleibt massgeblich.|UTC reference conflicts with local clock; localtimes remains authoritative.
utc_reference_unavailable|Keine nutzbare UTC-Referenz fuer den Gegencheck.|No usable UTC reference for cross-checking.
{column}_not_ready|Unter strikter Readiness-Policy sind Zeilen fuer diese Anforderung nicht bereit.|Under strict readiness policy, rows do not meet this requirement.
{prefix}_missing|Die benannte Datendomaene fehlt fuer diese Aufnahme.|The named data domain is missing for the recording.
{prefix}_issue|Die benannte Datendomaene ist vorhanden, meldet aber Probleme.|The named data domain exists but reports issues.
{type(|Originaler Exception-Typ und Meldung; kein eigener statischer Fehlercode.|Original exception type and message; not a separate fixed code.
"""
MEANINGS = [line.split("|", 2) for line in _DATA.strip().splitlines()]


def meaning(code, language):
    for prefix, de, en in sorted(MEANINGS, key=lambda item: len(item[0]), reverse=True):
        if code.startswith(prefix):
            return de if language == "DE" else en
    raise KeyError(f"Undocumented diagnostic meaning: {code}")

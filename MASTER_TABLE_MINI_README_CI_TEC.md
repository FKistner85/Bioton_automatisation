# Master table - Mini-README for ci-tec

## ID, location and time

ID, coordinates and time originate in PointData/dawn-chorus-soundscape.csv. Step 1 writes dawnchorus_metadata_clean.csv, which supplies these fields to the master table.

| Column | Meaning and format | Source / generation |
|---|---|---|
| dawn_chorus_id | Recording ID; integer stored as text. Example: 12345. | Source id, normalised to an integer ID. |
| lon / lat | WGS84 longitude / latitude (EPSG:4326), decimal degrees. Examples: lon 13.405; lat 52.52. | Source lng / lat, converted to numbers; lng is renamed lon. |
| grid_100m_id | 100 m grid cell; text. Example: 100mN6283E1192. | Point-in-polygon assignment using InspireGrid/Vector_Data/grid.gpkg. Read from DawnChorus_LRT_Grid_Assignment_no_K_post2017.csv. |
| grid_10m_id | 10 m grid cell; text. Example: 10mN62830E11920. | Calculated from grid_100m_id and lon/lat transformed to EPSG:3035. The 10 m position within the parent cell determines the ID; failed calculations stay empty. |
| datetime_local | German local date/time without suffix, `YYYY-MM-DD HH:MM:SS`, e.g. `2024-05-01 04:00:00`. | Step 1 localized timestamp; see precedence below. |
| date_local / time_local | Local date / clock time, without timezone. Formats: YYYY-MM-DD / HH:MM:SS. Examples: 2024-05-01 / 04:00:00. | Extracted from datetime_local without shifting the clock. |

## How local time is selected

Step 1 prioritizes `localtimes`; if a nonempty local clock is invalid it is flagged, not silently replaced. If `localtimes` is empty and `datetime` bears the misleading source `Z`/`+00:00` label, interpret its wall clock in Europe/Berlin before deriving real UTC. Valid nonzero-offset fallbacks follow their actual offset. Ambiguous or nonexistent German daylight-saving clocks are invalid; no fold is guessed. The PDF of 13.10.2026 is authoritative for the master format.

Source `datetime=2024-05-01T04:00:00Z` (without localtimes) becomes `datetime_local=2024-05-01 04:00:00`, while `datetime_utc=2024-05-01T02:00:00Z`. The `+02:00` zone offset appears only in the internal Step-1 metadata record.

For a display without timezone, combine date_local and time_local: 2024-05-01 04:00:00. `datetime_local` is stored WITHOUT the offset, exactly as required by the attached PDF.

## Availability and issues

All flags are booleans: True or False (for example, sound_exists=True and sound_has_issues=False).

_exists reports availability, not quality. _has_issues reports detected problems or missing data/check results. These flags cover media, satellite imagery, weather, grid assignments and bioacoustic results.

### sound_exists / sound_has_issues

Exists: ID is in audio_inventory_compact.csv. Issues: its issue flag, errors in audio_inventory_detailed.csv or audio_download_retry_log.csv, or missing inventory/record. Audio inventory source: PointData/SoundRecordings/.

### photo_exists / photo_has_issues

Same rules for photos, using photo_inventory_compact.csv, photo_inventory_detailed.csv and photo_download_retry_log.csv. Photo inventory source: PointData/Images_SoundRecordings/.

### sentinel_exists / sentinel_has_issues

Exists: inventory reports TIFF records for the ID. Issues: inventory checks, detailed errors or missing results. Sources: sentinel2_inventory_compact.csv and sentinel2_inventory_detailed.csv, built from PointData/S2/ and PointData/S2_Scores.csv.

### weather_point_exists / weather_point_has_issues

Exists: inventory reports a weather file for the ID. Issues: inventory flag, issue codes or missing results. Source: weather_inventory_compact.csv, built by checking PointData/Weather/Hostrada/weather_*.csv against dawnchorus_metadata_clean.csv.

### weather_raster_hostrada_100m_exists /weather_raster_hostrada_100m_has_issues

Exists: step_5_4_hostrada_raster_products/ contains a .tif or .tiff. Issues: missing rasters/QC, QC read errors, all-NoData, shape or structure warnings. QC file: step_5_5_hostrada_raster_quality_check/hostrada_raster_quality.csv. Both flags apply to the whole raster collection and repeat for every ID.

### grid_100m_assignment_exists / grid_10m_assignment_exists

True when the corresponding grid_100m_id / grid_10m_id is non-null; otherwise False. Sources are the assignment file / calculation described on page 1. A 10 m assignment does not require a matching formation product.

### bioacoustic_has_issues

Issue flag read from bioacoustic_qc_compact.csv (Step 6.6); missing QC or a missing recording result also gives True.

Filenames and locations follow config.horeka.json. PointData/ and InspireGrid/ are relative to /lsdf/kit/ipf/projects/Bio-O-Ton/. Generated CSVs are in the corresponding step directories under Data_automatisation_skripts/outputs/.

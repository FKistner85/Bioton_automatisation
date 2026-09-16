# Master table

ci-tec | README

Selected columns in `Bio_O_Ton_Master_CI_TEC.csv`. One row per recording. Original metadata source: `dawn-chorus-soundscape.csv`.

| Column | Meaning |
|---|---|
| `dawn_chorus_id` | Recording ID. |
| `lon`, `lat` | WGS84 coordinates in decimal degrees. |
| `grid_100m_id`, `grid_10m_id` | Assigned grid cells. A grid ID does not imply that LRT formation data are available. |
| `datetime_local` | German local date and clock time, with summer/winter time accounted for. No timezone suffix. Example: `2025-03-01 16:03:00`. |

## Availability and issues

**_exists**: `True` means the corresponding files were recorded as present on LSDF. These flags describe the recorded inventory, not a live file check.

**_has_issues**: `True` means a problem or missing required data/check results. It can be `True` whether `_exists` is `True` or `False`.

Empty means no check result is available.

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

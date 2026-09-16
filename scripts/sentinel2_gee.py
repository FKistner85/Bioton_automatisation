"""Earth Engine-backed Sentinel-2 scoring and direct tile acquisition.

The Earth Engine expressions in this module intentionally mirror the
``UpdateSentinel.ipynb`` method.  Imports for Earth Engine are lazy so that
the pipeline's pure selection and score-file utilities remain testable on a
machine without the Earth Engine client installed.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCORE_COLUMNS = [
    "DC_id",
    "score",
    "best_index",
    "best_time",
    "n_candidates",
]
S2_BANDS = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12",
]


class GeeUnavailable(RuntimeError):
    """Raised when GEE cannot be used and an automatic fallback is allowed."""


@dataclass(frozen=True)
class AcquisitionResult:
    scored: int
    score_rows_written: int
    downloaded: int
    skipped_existing: int
    failed: int


@dataclass(frozen=True)
class DriveExportResult:
    scored: int
    score_rows_written: int
    exports_started: int
    exports_completed: int
    skipped_existing: int
    failed: int
    expected_drive_ids: frozenset[str]


def normalise_id(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "" if pd.isna(numeric) else str(int(numeric))


def read_metadata(path: Path) -> pd.DataFrame:
    """Read the canonical Step-1 metadata output or a compatible CSV."""
    frame = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    if len(frame.columns) == 1:
        alternate = pd.read_csv(path, sep=";", low_memory=False, encoding="utf-8-sig")
        if len(alternate.columns) > 1:
            frame = alternate
    id_column = next(
        (column for column in ("dawn_chorus_id", "id", "recording_id") if column in frame),
        None,
    )
    if id_column is None:
        raise KeyError(f"No Dawn Chorus ID column found in {path}")
    if "lat" not in frame or not ("lon" in frame or "lng" in frame):
        raise KeyError(f"Metadata must contain lat and lon/lng columns: {path}")
    datetime_column = next(
        (column for column in ("datetime", "datetime_utc") if column in frame),
        None,
    )
    if datetime_column is None:
        raise KeyError(f"Metadata must contain datetime or datetime_utc: {path}")
    result = frame.copy()
    result["DC_id"] = result[id_column].map(normalise_id)
    result["lat"] = pd.to_numeric(result["lat"], errors="coerce")
    result["lon"] = pd.to_numeric(result["lon"], errors="coerce") if "lon" in result else pd.to_numeric(result["lng"], errors="coerce")
    result["datetime_utc"] = pd.to_datetime(
        result[datetime_column], errors="coerce", utc=True, format="mixed"
    )
    result = result[(result["DC_id"] != "") & result["lat"].notna() & result["lon"].notna() & result["datetime_utc"].notna()]
    return result.drop_duplicates("DC_id", keep="last").reset_index(drop=True)


def read_id_file(path: Path | None) -> set[str]:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return set()
    frame = pd.read_csv(path, low_memory=False, dtype=str)
    column = next((name for name in ("dawn_chorus_id", "DC_id", "id") if name in frame), None)
    if column is None:
        return set()
    return {value for value in frame[column].map(normalise_id) if value}


def eligible_metadata(
    metadata: pd.DataFrame,
    *,
    now: datetime | None = None,
    max_age_days: int = 28,
    lookback_days: int | None = 70,
) -> pd.DataFrame:
    """Apply the notebook's delayed update window without changing its method."""
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    newest = pd.Timestamp(reference - timedelta(days=max_age_days))
    mask = metadata["datetime_utc"] <= newest
    if lookback_days is not None:
        oldest = pd.Timestamp(reference - timedelta(days=lookback_days))
        mask &= metadata["datetime_utc"] >= oldest
    return metadata.loc[mask].copy()


def select_ids(
    metadata: pd.DataFrame,
    requested_ids: Iterable[str] | None,
    *,
    now: datetime | None = None,
    max_age_days: int = 28,
    lookback_days: int | None = 70,
) -> pd.DataFrame:
    eligible = eligible_metadata(
        metadata,
        now=now,
        max_age_days=max_age_days,
        lookback_days=lookback_days,
    )
    requested = {normalise_id(value) for value in (requested_ids or ()) if normalise_id(value)}
    if requested:
        eligible = eligible[eligible["DC_id"].isin(requested)]
    return eligible.reset_index(drop=True)


def read_scores(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame(columns=SCORE_COLUMNS)
    frame = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    column = next((name for name in ("DC_id", "dawn_chorus_id", "id") if name in frame), None)
    if column is None or "score" not in frame:
        raise KeyError(f"Score file must contain an ID column and score: {path}")
    frame = frame.copy()
    frame["DC_id"] = frame[column].map(normalise_id)
    return frame[frame["DC_id"] != ""].drop_duplicates("DC_id", keep="last")


def atomic_write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    os.replace(temporary, path)


def write_acquisition_log(path: Path, rows: list[dict[str, Any]]) -> None:
    """Replace the single GEE acquisition log atomically."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = sorted({key for row in rows for key in row})
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def read_acquisition_log(path: Path) -> dict[str, dict[str, Any]]:
    """Read the single task log, keeping its most recent row per DC_id."""
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            normalise_id(row.get("DC_id")): row
            for row in csv.DictReader(handle)
            if normalise_id(row.get("DC_id"))
        }


def upsert_scores(path: Path, incoming: pd.DataFrame) -> int:
    """Atomically upsert one canonical score row per DC_id."""
    if incoming.empty:
        return 0
    update = incoming.copy()
    if "DC_id" not in update:
        raise KeyError("Incoming score rows must contain DC_id")
    update["DC_id"] = update["DC_id"].map(normalise_id)
    update = update[update["DC_id"] != ""].drop_duplicates("DC_id", keep="last")
    previous = read_scores(path)
    previous = previous[~previous["DC_id"].isin(set(update["DC_id"]))]
    columns = list(dict.fromkeys([*previous.columns.tolist(), *update.columns.tolist()]))
    merged = pd.concat([previous.reindex(columns=columns), update.reindex(columns=columns)], ignore_index=True)
    merged = merged.sort_values("DC_id", key=lambda values: values.map(normalise_id), kind="stable")
    atomic_write_csv(path, merged)
    return len(update)


def _box_utm32(ee, point, half: int = 500):
    geometry = point.geometry().transform("EPSG:3035", 1)
    xy = geometry.coordinates()
    x = ee.Number(xy.get(0))
    y = ee.Number(xy.get(1))
    return ee.Geometry.Rectangle(
        [x.subtract(half), y.subtract(half), x.add(half), y.add(half)],
        "EPSG:3035",
        False,
    )


def build_dc_best(ee, metadata: pd.DataFrame):
    """Build the unchanged score expression from UpdateSentinel.ipynb."""
    if metadata.empty:
        return None
    min_date = (metadata["datetime_utc"].min() - pd.Timedelta(days=10)).date()
    max_date = (metadata["datetime_utc"].max() + pd.Timedelta(days=1)).date()
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(ee.Date(min_date.isoformat()), ee.Date(max_date.isoformat()))
        .select(["B2", "SCL"])
    )
    features = [
        ee.Feature(
            ee.Geometry.Point([float(row.lon), float(row.lat)]),
            {
                "datetime": ee.Date.fromYMD(int(row.datetime_utc.year), int(row.datetime_utc.month), int(row.datetime_utc.day)).millis(),
                "DC_id": row.DC_id,
            },
        )
        for row in metadata.itertuples(index=False)
    ]
    points = ee.FeatureCollection(features)

    def add_weight_band(image):
        scl = image.select("SCL")
        weight = ee.Image(1.0)
        weight = weight.where(scl.eq(8), 0.0)
        weight = weight.where(scl.eq(9), 0.0)
        weight = weight.where(scl.eq(10), 0.8)
        weight = weight.where(scl.eq(3), 0.8)
        weight = weight.where(scl.eq(1), 0.0)
        weight = weight.where(image.select("B2").mask().Not(), 0.0)
        return image.addBands(weight.rename("weight"))

    def add_score(image, box):
        score = image.select("weight").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=box, scale=20, maxPixels=1e8,
        ).get("weight")
        return image.set("score", score)

    def pick_best(point):
        date = ee.Date(point.get("datetime"))
        box = _box_utm32(ee, point, 500)
        candidates = (
            collection.filterDate(date.advance(-10, "day"), date)
            .filterBounds(box)
            .map(add_weight_band)
        )
        scored = candidates.limit(10).map(lambda image: add_score(image, box)).sort("score", False)
        has = scored.size().gt(0)
        best = ee.Image(scored.first())
        return point.set({
            "best_index": ee.Algorithms.If(has, best.get("system:index"), None),
            "best_time": ee.Algorithms.If(has, best.get("system:time_start"), None),
            "score": ee.Algorithms.If(has, best.get("score"), None),
            "n_candidates": candidates.size(),
        })

    return points.map(pick_best), collection


def iter_score_chunks(ee, metadata: pd.DataFrame, chunk_size: int = 0):
    """Yield unchanged DC_best evaluations in bounded API-sized chunks.

    Chunking only limits client/API request size.  Each chunk uses the same
    collection, date window, cloud weights and reducers as the notebook.
    """
    if metadata.empty:
        return
    size = int(chunk_size or len(metadata))
    size = max(1, size)
    for start in range(0, len(metadata), size):
        dc_best, _ = build_dc_best(ee, metadata.iloc[start : start + size].copy())
        if dc_best is None:
            continue
        scored = ee.data.computeFeatures(
            {"expression": dc_best, "fileFormat": "PANDAS_DATAFRAME"}
        )
        if not isinstance(scored, pd.DataFrame):
            scored = pd.DataFrame(scored)
        yield scored


def compute_scores(ee, metadata: pd.DataFrame, chunk_size: int = 0) -> pd.DataFrame:
    """Evaluate the unchanged DC_best expression, optionally in chunks."""
    frames = list(iter_score_chunks(ee, metadata, chunk_size=chunk_size))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCORE_COLUMNS)


def _download_image(ee, image, target: Path, settings: dict[str, Any]) -> None:
    import requests

    params = {
        "bands": S2_BANDS,
        "region": image.geometry(1, "EPSG:3035", False),
        "dimensions": [101, 101],
        "crs": "EPSG:3035",
        "format": "GEO_TIFF",
        "filePerBand": False,
    }
    url = image.getDownloadURL(params)
    timeout = int(settings.get("gee_download_timeout_seconds", 180))
    retries = int(settings.get("gee_download_retries", 4))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"Earth Engine HTTP {response.status_code}")
            response.raise_for_status()
            temporary.write_bytes(response.content)
            os.replace(temporary, target)
            return
        except Exception as exc:  # bounded retry for transient GEE/network failures
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(30.0, 2.0 ** attempt))
    raise RuntimeError(f"GEE download failed for {target.name}: {last_error}")


def validate_tile(path: Path, settings: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    try:
        import rasterio
        with rasterio.open(path) as dataset:
            array = dataset.read()
            valid = np.isfinite(array)
            values = array[valid]
            stats = {
                "bands": dataset.count,
                "height": dataset.height,
                "width": dataset.width,
                "crs": "" if dataset.crs is None else str(dataset.crs),
                "nodata": dataset.nodata,
                "valid_pixels": int(values.size),
                "invalid_pixels": int((~valid).sum()),
            }
            ok = (
                dataset.count == int(settings.get("expected_bands", 12))
                and dataset.height == int(settings.get("expected_height", 101))
                and dataset.width == int(settings.get("expected_width", 101))
                and values.size > 0
                and float(values.std()) != 0.0
            )
            return ok, stats
    except Exception as exc:
        return False, {"error": repr(exc)}


def _gee_credentials(ee, settings: dict[str, Any], project: str):
    key_value = os.environ.get("BIOOTON_GEE_SERVICE_ACCOUNT_KEY", "").strip()
    key_value = key_value or str(settings.get("gee_service_account_key_path", "")).strip()
    if key_value:
        key_path = Path(key_value).expanduser()
        if not key_path.is_file():
            raise GeeUnavailable(f"GEE service-account key not found: {key_path}")
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            key_path,
            scopes=["https://www.googleapis.com/auth/earthengine"],
        )
        ee.Initialize(credentials=credentials, project=project)
        return
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        raise GeeUnavailable(
            "No GEE service-account key configured and stored Earth Engine credentials are unavailable"
        ) from exc


def _gee_export_user_credentials(ee, settings: dict[str, Any], project: str):
    """Initialize EE as the Drive-owning user for legacy export tasks only."""
    token_value = os.environ.get("BIOOTON_GEE_EXPORT_TOKEN", "").strip()
    token_value = token_value or str(
        settings.get("gee_export_oauth_token_path", "")
    ).strip()
    if not token_value:
        raise GeeUnavailable(
            "No user OAuth token configured for legacy Earth Engine Drive exports"
        )
    token_path = Path(token_value).expanduser()
    if not token_path.is_file():
        raise GeeUnavailable(f"GEE export OAuth token not found: {token_path}")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        token_payload = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeeUnavailable(f"Cannot read GEE export OAuth token: {token_path}") from exc
    if not isinstance(token_payload, dict):
        raise GeeUnavailable(f"Invalid GEE export OAuth token: {token_path}")

    # ``ee.Authenticate`` stores only the refresh token, redirect URI and
    # scopes.  Google ``authorized_user`` files additionally contain the
    # OAuth client metadata.  Accept both formats and use the official Earth
    # Engine client defaults when that metadata is intentionally absent.
    credentials = Credentials(
        token=None,
        refresh_token=token_payload.get("refresh_token"),
        token_uri=token_payload.get("token_uri", ee.oauth.TOKEN_URI),
        client_id=token_payload.get("client_id", ee.oauth.CLIENT_ID),
        client_secret=token_payload.get("client_secret", ee.oauth.CLIENT_SECRET),
        scopes=token_payload.get("scopes", ee.oauth.SCOPES),
        quota_project_id=token_payload.get(
            "quota_project_id", token_payload.get("project")
        ),
    )
    required_scopes = {
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/drive",
    }
    granted = set(credentials.scopes or ())
    if granted and not required_scopes.issubset(granted):
        missing = ", ".join(sorted(required_scopes - granted))
        raise GeeUnavailable(f"GEE export OAuth token lacks required scopes: {missing}")
    if not credentials.valid:
        if not credentials.refresh_token:
            raise GeeUnavailable("GEE export OAuth token has no refresh token")
        credentials.refresh(Request())
        temporary = token_path.with_suffix(token_path.suffix + ".tmp")
        temporary.write_text(credentials.to_json(), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, token_path)
    ee.Initialize(credentials=credentials, project=project)


def _selected_metadata(settings: dict[str, Any], args: Any) -> pd.DataFrame:
    """Load the delayed, run-plan-limited metadata without an empty-file fallback."""
    ids_path = getattr(args, "ids_file", None)
    requested = read_id_file(ids_path)
    # An explicitly supplied but empty run-plan file means "no IDs".  It must
    # never silently expand to every eligible historical recording.
    if ids_path is not None and not requested:
        return pd.DataFrame()
    return select_ids(
        read_metadata(Path(settings["metadata_csv"])),
        requested,
        max_age_days=int(settings.get("gee_max_age_days", 28)),
        lookback_days=settings.get("gee_lookback_days", 70),
    )


def _score_and_persist(
    ee,
    metadata: pd.DataFrame,
    score_path: Path,
    *,
    pipeline_batch_size: int,
    score_chunk_size: int,
):
    """Yield one fully scored outer pipeline batch and persist every API chunk."""
    batch_size = max(1, int(pipeline_batch_size or len(metadata) or 1))
    for batch_start in range(0, len(metadata), batch_size):
        metadata_batch = metadata.iloc[batch_start : batch_start + batch_size].copy()
        scored_frames: list[pd.DataFrame] = []
        written = 0
        for scored_chunk in iter_score_chunks(
            ee,
            metadata_batch,
            chunk_size=score_chunk_size,
        ):
            if "DC_id" not in scored_chunk:
                raise RuntimeError("Earth Engine score response has no DC_id column")
            incoming_chunk = scored_chunk.reindex(
                columns=[column for column in SCORE_COLUMNS if column in scored_chunk.columns]
            ).copy()
            written += upsert_scores(score_path, incoming_chunk)
            scored_frames.append(scored_chunk)
        scored = (
            pd.concat(scored_frames, ignore_index=True)
            if scored_frames
            else pd.DataFrame(columns=SCORE_COLUMNS)
        )
        yield metadata_batch, scored, written


def _legacy_drive_task(ee, metadata_row: Any, score_row: Any, folder_name: str):
    """Create the exact Export.image.toDrive task used by UpdateSentinel.ipynb."""
    point = ee.Feature(
        ee.Geometry.Point([float(metadata_row.lon), float(metadata_row.lat)]),
        {"DC_id": score_row.DC_id},
    )
    collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").select(S2_BANDS)
    image = ee.Image(
        collection.filter(ee.Filter.eq("system:index", score_row.best_index)).first()
    )
    image = (
        image.unmask(-9999, sameFootprint=False)
        .clip(_box_utm32(ee, point, 501))
        .set({"DC_id": score_row.DC_id})
    )
    description = f"S2tile_{score_row.DC_id}"
    return ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder=folder_name,
        region=image.geometry(1, "EPSG:3035", False),
        dimensions="101x101",
        crs="EPSG:3035",
        maxPixels=1e13,
        formatOptions={"noData": -9999},
        skipEmptyTiles=True,
    )


def _task_status(task: Any) -> dict[str, Any]:
    status = task.status()
    return status if isinstance(status, dict) else {}


def _active_ee_task_count(ee) -> int:
    active = {"READY", "RUNNING"}
    return sum(
        str(_task_status(task).get("state", "")).upper() in active
        for task in ee.batch.Task.list()
    )


def _existing_export_tasks(ee) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Return the most useful existing task per immutable S2 description."""
    result: dict[str, tuple[Any, dict[str, Any]]] = {}
    priority = {"RUNNING": 4, "READY": 3, "COMPLETED": 2, "FAILED": 1, "CANCELLED": 0}
    for task in ee.batch.Task.list():
        status = _task_status(task)
        task_config = getattr(task, "config", {}) or {}
        description = str(
            status.get("description", "") or task_config.get("description", "")
        )
        if not description.startswith("S2tile_"):
            continue
        state = str(status.get("state", "")).upper()
        old = result.get(description)
        if old is None or priority.get(state, -1) > priority.get(
            str(old[1].get("state", "")).upper(), -1
        ):
            result[description] = (task, status)
    return result


def run_gee_drive_exports(
    config: dict[str, Any],
    args: Any,
    *,
    existing_ids: Iterable[str] = (),
) -> DriveExportResult:
    """Score all new IDs and run the unchanged legacy Drive exports.

    Outer batches are sequential.  Within each batch only a bounded number of
    Earth Engine tasks may be READY/RUNNING.  Existing Drive or LSDF IDs are
    immutable and are never submitted again, regardless of ``--force``.
    """
    settings = config["sentinel2_download"]
    try:
        import ee
    except ImportError as exc:
        raise GeeUnavailable("earthengine-api is not installed") from exc

    metadata = _selected_metadata(settings, args)
    if metadata.empty:
        return DriveExportResult(0, 0, 0, 0, 0, 0, frozenset())

    project = str(settings.get("gee_project", "bio-o-ton-gee"))
    _gee_credentials(ee, settings, project)
    score_path = Path(
        settings.get(
            "score_csv",
            config.get("sentinel2_inventory", {}).get("score_csv", "S2_Scores.csv"),
        )
    )
    log_path = Path(
        settings.get(
            "gee_drive_export_log_csv",
            settings.get("gee_log_csv", "gee_drive_export_log.csv"),
        )
    )
    pipeline_batch_size = int(settings.get("gee_pipeline_batch_size", 500))
    score_chunk_size = int(settings.get("gee_score_chunk_size", 100))
    max_active = max(1, int(settings.get("gee_drive_max_active_tasks", 20)))
    poll_seconds = max(1, int(settings.get("gee_drive_poll_seconds", 20)))
    timeout_seconds = max(1, int(settings.get("gee_drive_timeout_seconds", 21600)))
    folder_name = str(settings.get("gee_drive_folder_name", "S2"))
    immutable_ids = {normalise_id(value) for value in existing_ids if normalise_id(value)}
    log_by_id = read_acquisition_log(log_path)
    known_tasks: dict[str, tuple[Any, dict[str, Any]]] | None = None

    total_scored = total_written = started = completed = skipped = failed = 0
    expected_drive_ids: set[str] = set()
    score_only = bool(getattr(args, "score_only", False))
    # Apply one deadline to the complete export run. Resetting it for every
    # outer batch allowed a nominal 10-hour limit to grow into multi-day jobs.
    export_deadline = time.monotonic() + timeout_seconds

    for metadata_batch, scored, written in _score_and_persist(
        ee,
        metadata,
        score_path,
        pipeline_batch_size=pipeline_batch_size,
        score_chunk_size=score_chunk_size,
    ):
        total_scored += len(scored)
        total_written += written
        if score_only:
            continue
        if scored.empty:
            continue
        # Drive exports must run as the Drive-owning user. Service accounts
        # have no personal Drive storage quota even when a folder is shared.
        _gee_export_user_credentials(ee, settings, project)
        if known_tasks is None:
            known_tasks = _existing_export_tasks(ee)
        good = scored.copy()
        good["DC_id"] = good["DC_id"].map(normalise_id)
        good["score_numeric"] = pd.to_numeric(good.get("score"), errors="coerce")
        good = good[
            good["score_numeric"].gt(0)
            & good["best_index"].notna()
            & good["DC_id"].ne("")
        ]
        metadata_by_id = {
            row.DC_id: row for row in metadata_batch.itertuples(index=False)
        }
        queue: list[tuple[Any, Any]] = []
        running: dict[str, tuple[Any, Any]] = {}

        for score_row in good.itertuples(index=False):
            dc_id = score_row.DC_id
            expected_drive_ids.add(dc_id)
            description = f"S2tile_{dc_id}"
            base_log = {
                "DC_id": dc_id,
                "description": description,
                "score": score_row.score_numeric,
                "best_index": score_row.best_index,
                "updated_utc": datetime.now(timezone.utc).isoformat(),
            }
            if dc_id in immutable_ids:
                skipped += 1
                log_by_id[dc_id] = {**base_log, "status": "skipped_existing_immutable"}
                continue
            previous_task = known_tasks.get(description)
            if previous_task is not None:
                task, status = previous_task
                state = str(status.get("state", "")).upper()
                if state in {"READY", "RUNNING"}:
                    running[dc_id] = (task, score_row)
                    log_by_id[dc_id] = {
                        **base_log,
                        "status": state.lower(),
                        "task_id": status.get("id", getattr(task, "id", "")),
                    }
                    continue
                if state == "COMPLETED":
                    completed += 1
                    immutable_ids.add(dc_id)
                    log_by_id[dc_id] = {
                        **base_log,
                        "status": "completed_existing_task",
                        "task_id": status.get("id", getattr(task, "id", "")),
                    }
                    continue
            queue.append((metadata_by_id[dc_id], score_row))

        write_acquisition_log(log_path, list(log_by_id.values()))
        while queue or running:
            for dc_id, (task, score_row) in list(running.items()):
                status = _task_status(task)
                state = str(status.get("state", "UNKNOWN")).upper()
                log_by_id[dc_id] = {
                    "DC_id": dc_id,
                    "description": f"S2tile_{dc_id}",
                    "score": score_row.score_numeric,
                    "best_index": score_row.best_index,
                    "status": state.lower(),
                    "task_id": status.get("id", getattr(task, "id", "")),
                    "error_message": status.get("error_message", ""),
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                }
                if state == "COMPLETED":
                    completed += 1
                    immutable_ids.add(dc_id)
                    running.pop(dc_id)
                elif state in {"FAILED", "CANCELLED"}:
                    failed += 1
                    running.pop(dc_id)

            available = max(0, max_active - _active_ee_task_count(ee))
            for _ in range(min(available, len(queue))):
                metadata_row, score_row = queue.pop(0)
                task = _legacy_drive_task(ee, metadata_row, score_row, folder_name)
                task.start()
                started += 1
                running[score_row.DC_id] = (task, score_row)
                log_by_id[score_row.DC_id] = {
                    "DC_id": score_row.DC_id,
                    "description": f"S2tile_{score_row.DC_id}",
                    "score": score_row.score_numeric,
                    "best_index": score_row.best_index,
                    "status": "ready",
                    "task_id": getattr(task, "id", ""),
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                }
            write_acquisition_log(log_path, list(log_by_id.values()))
            if queue or running:
                if time.monotonic() >= export_deadline:
                    raise TimeoutError(
                        "Timed out waiting for legacy Sentinel-2 Drive exports "
                        f"(queued={len(queue)}, active={len(running)})"
                    )
                time.sleep(poll_seconds)

        if failed:
            break
        # The next outer batch is scored with the service account again.
        _gee_credentials(ee, settings, project)

    if score_only:
        write_acquisition_log(
            log_path,
            [
                {
                    "status": "score_only",
                    "scored": total_scored,
                    "score_rows_written": total_written,
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
    if failed:
        raise RuntimeError(f"{failed} legacy Sentinel-2 Drive export task(s) failed")
    return DriveExportResult(
        total_scored,
        total_written,
        started,
        completed,
        skipped,
        failed,
        frozenset(expected_drive_ids),
    )


def run_gee(config: dict[str, Any], args: Any) -> AcquisitionResult:
    """Score and acquire the requested IDs using Earth Engine directly."""
    settings = config["sentinel2_download"]
    if not bool(settings.get("gee_direct_download_verified", False)):
        raise GeeUnavailable(
            "Direct GEE raster download is disabled until parity with the legacy export is verified"
        )
    try:
        import ee
    except ImportError as exc:
        raise GeeUnavailable("earthengine-api is not installed") from exc
    score_path = Path(settings.get("score_csv", config.get("sentinel2_inventory", {}).get("score_csv", "S2_Scores.csv")))
    output_dir = Path(settings["output_dir"])
    log_path = Path(settings.get("gee_log_csv", settings.get("log_csv", output_dir / "gee_acquisition_log.csv")))
    metadata = _selected_metadata(settings, args)
    if metadata.empty:
        return AcquisitionResult(0, 0, 0, 0, 0)
    project = str(settings.get("gee_project", "bio-o-ton-gee"))
    _gee_credentials(ee, settings, project)
    scored_frames: list[pd.DataFrame] = []
    written = 0
    for scored_chunk in iter_score_chunks(
        ee,
        metadata,
        chunk_size=int(settings.get("gee_score_chunk_size", 0)),
    ):
        if "DC_id" not in scored_chunk:
            raise RuntimeError("Earth Engine score response has no DC_id column")
        incoming_chunk = scored_chunk.reindex(
            columns=[column for column in SCORE_COLUMNS if column in scored_chunk.columns]
        ).copy()
        written += upsert_scores(score_path, incoming_chunk)
        scored_frames.append(scored_chunk)
    scored = pd.concat(scored_frames, ignore_index=True) if scored_frames else pd.DataFrame()
    if scored.empty:
        return AcquisitionResult(0, 0, 0, 0, 0)
    if "DC_id" not in scored:
        raise RuntimeError("Earth Engine score response has no DC_id column")

    # Score-only runs are used for scale tests and for a future independent
    # score-refresh step.  They deliberately stop before any raster request;
    # the productive Sentinel path remains the legacy Drive mirror.
    if bool(getattr(args, "score_only", False)):
        write_acquisition_log(
            log_path,
            [
                {
                    "status": "score_only",
                    "scored": len(scored),
                    "score_rows_written": written,
                }
            ],
        )
        return AcquisitionResult(len(scored), written, 0, 0, 0)

    good = scored.copy()
    good["DC_id"] = good["DC_id"].map(normalise_id)
    good["score_numeric"] = pd.to_numeric(good.get("score"), errors="coerce")
    good = good[good["score_numeric"].gt(0) & good["best_index"].notna()]
    downloaded = skipped = failed = 0
    log_rows: list[dict[str, Any]] = []
    full_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").select(S2_BANDS)
    for row in good.itertuples(index=False):
        target = output_dir / f"S2tile_{row.DC_id}.tif"
        if not getattr(args, "force", False) and target.is_file():
            ok, _ = validate_tile(target, settings)
            if ok:
                skipped += 1
                log_rows.append({"DC_id": row.DC_id, "status": "skipped_existing", "path": str(target), "score": row.score_numeric, "best_index": row.best_index})
                continue
        point = ee.Feature(ee.Geometry.Point([float(metadata.loc[metadata["DC_id"] == row.DC_id, "lon"].iloc[0]), float(metadata.loc[metadata["DC_id"] == row.DC_id, "lat"].iloc[0])]), {"DC_id": row.DC_id})
        image = ee.Image(full_collection.filter(ee.Filter.eq("system:index", row.best_index)).first())
        image = image.unmask(-9999, sameFootprint=False).clip(_box_utm32(ee, point, 501)).set({"DC_id": row.DC_id})
        try:
            _download_image(ee, image, target, settings)
            ok, _ = validate_tile(target, settings)
            if ok:
                downloaded += 1
                log_rows.append({"DC_id": row.DC_id, "status": "downloaded", "path": str(target), "score": row.score_numeric, "best_index": row.best_index})
            else:
                failed += 1
                log_rows.append({"DC_id": row.DC_id, "status": "validation_failed", "path": str(target), "score": row.score_numeric, "best_index": row.best_index})
        except Exception:
            target.with_suffix(target.suffix + ".part").unlink(missing_ok=True)
            failed += 1
            log_rows.append({"DC_id": row.DC_id, "status": "download_failed", "path": str(target), "score": row.score_numeric, "best_index": row.best_index})
    write_acquisition_log(log_path, log_rows)
    if failed:
        raise RuntimeError(f"{failed} Sentinel-2 GEE tile downloads failed")
    return AcquisitionResult(len(scored), written, downloaded, skipped, failed)

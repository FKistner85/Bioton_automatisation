"""Pure tests for the GEE Sentinel selection and score persistence layer."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

from sentinel2_gee import (  # noqa: E402
    S2_BANDS,
    _gee_export_user_credentials,
    _legacy_drive_task,
    _selected_metadata,
    eligible_metadata,
    read_scores,
    select_ids,
    upsert_scores,
)
from validate_sentinel_scores import compare_score_frames  # noqa: E402


def _metadata() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DC_id": ["1", "2", "3"],
            "lat": [49.0, 49.1, 49.2],
            "lon": [8.0, 8.1, 8.2],
            "datetime_utc": pd.to_datetime(
                ["2026-07-20T05:00:00Z", "2026-08-01T05:00:00Z", "2026-06-01T05:00:00Z"],
                utc=True,
            ),
        }
    )


def test_four_week_delay_and_notebook_lookback() -> None:
    now = datetime(2026, 8, 21, tzinfo=timezone.utc)
    result = eligible_metadata(_metadata(), now=now, max_age_days=28, lookback_days=70)
    assert result["DC_id"].tolist() == ["1"]


def test_requested_ids_are_intersected_with_eligible_window() -> None:
    now = datetime(2026, 8, 21, tzinfo=timezone.utc)
    result = select_ids(_metadata(), {"1", "2", "999"}, now=now, max_age_days=28, lookback_days=70)
    assert result["DC_id"].tolist() == ["1"]


def test_score_upsert_is_single_file_and_replaces_ids(tmp_path: Path) -> None:
    path = tmp_path / "S2_Scores.csv"
    initial = pd.DataFrame(
        {
            "DC_id": ["1", "2"],
            "score": [0.2, 0.3],
            "best_index": ["old-1", "old-2"],
        }
    )
    assert upsert_scores(path, initial) == 2
    update = pd.DataFrame(
        {
            "DC_id": ["2", "3"],
            "score": [0.9, 0.7],
            "best_index": ["new-2", "new-3"],
        }
    )
    assert upsert_scores(path, update) == 2
    result = read_scores(path).set_index("DC_id")
    assert result.loc["1", "score"] == 0.2
    assert result.loc["2", "score"] == 0.9
    assert result.loc["2", "best_index"] == "new-2"
    assert result.loc["3", "score"] == 0.7
    assert len(result) == 3


def test_explicit_empty_run_plan_never_expands_to_all_metadata(tmp_path: Path) -> None:
    ids_path = tmp_path / "sentinel.csv"
    ids_path.write_text("dawn_chorus_id\n", encoding="utf-8")
    with patch("sentinel2_gee.read_metadata") as read_metadata_mock:
        selected = _selected_metadata(
            {"metadata_csv": str(tmp_path / "must_not_be_read.csv")},
            SimpleNamespace(ids_file=ids_path),
        )
    assert selected.empty
    read_metadata_mock.assert_not_called()


def test_legacy_drive_export_parameters_are_unchanged() -> None:
    ee = MagicMock()
    x = MagicMock(name="x")
    y = MagicMock(name="y")
    ee.Number.side_effect = [x, y]
    source_image = MagicMock(name="source_image")
    unmasked = MagicMock(name="unmasked")
    clipped = MagicMock(name="clipped")
    export_image = MagicMock(name="export_image")
    source_image.unmask.return_value = unmasked
    unmasked.clip.return_value = clipped
    clipped.set.return_value = export_image
    ee.Image.return_value = source_image
    task = MagicMock(name="task")
    ee.batch.Export.image.toDrive.return_value = task

    metadata_row = SimpleNamespace(DC_id="42", lon=8.4, lat=49.0)
    score_row = SimpleNamespace(DC_id="42", best_index="S2_INDEX", score_numeric=0.9)
    assert _legacy_drive_task(ee, metadata_row, score_row, "S2") is task

    ee.ImageCollection.assert_called_once_with("COPERNICUS/S2_SR_HARMONIZED")
    ee.ImageCollection.return_value.select.assert_called_once_with(S2_BANDS)
    source_image.unmask.assert_called_once_with(-9999, sameFootprint=False)
    x.subtract.assert_called_once_with(501)
    y.subtract.assert_called_once_with(501)
    x.add.assert_called_once_with(501)
    y.add.assert_called_once_with(501)
    kwargs = ee.batch.Export.image.toDrive.call_args.kwargs
    assert kwargs["image"] is export_image
    assert kwargs["description"] == "S2tile_42"
    assert kwargs["folder"] == "S2"
    assert kwargs["dimensions"] == "101x101"
    assert kwargs["crs"] == "EPSG:3035"
    assert kwargs["maxPixels"] == 1e13
    assert kwargs["formatOptions"] == {"noData": -9999}
    assert kwargs["skipEmptyTiles"] is True


def test_gee_export_credentials_accept_official_ee_token_format(
    tmp_path: Path,
) -> None:
    scopes = [
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/drive",
    ]
    token_path = tmp_path / "earthengine-token.json"
    token_path.write_text(
        json.dumps(
            {
                "redirect_uri": "http://localhost:8085",
                "refresh_token": "refresh-token",
                "scopes": scopes,
            }
        ),
        encoding="utf-8",
    )
    ee = MagicMock()
    ee.oauth.TOKEN_URI = "https://oauth2.googleapis.com/token"
    ee.oauth.CLIENT_ID = "official-ee-client"
    ee.oauth.CLIENT_SECRET = "official-ee-secret"
    ee.oauth.SCOPES = scopes
    credentials = MagicMock(valid=True, scopes=scopes)

    with patch(
        "google.oauth2.credentials.Credentials", return_value=credentials
    ) as credentials_class:
        _gee_export_user_credentials(
            ee,
            {"gee_export_oauth_token_path": str(token_path)},
            "bio-o-ton-gee",
        )

    credentials_class.assert_called_once_with(
        token=None,
        refresh_token="refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="official-ee-client",
        client_secret="official-ee-secret",
        scopes=scopes,
        quota_project_id=None,
    )
    ee.Initialize.assert_called_once_with(
        credentials=credentials,
        project="bio-o-ton-gee",
    )


def test_score_regression_comparison_requires_exact_index_and_score() -> None:
    reference = pd.DataFrame(
        {
            "DC_id": ["1", "2"],
            "score": [0.75, 1.0],
            "best_index": ["scene-a", "scene-b"],
        }
    )
    fresh = pd.DataFrame(
        {
            "DC_id": ["1", "2"],
            "score": [0.75, 0.9],
            "best_index": ["scene-a", "scene-b"],
        }
    )
    result = compare_score_frames(reference, fresh, score_atol=1e-12)
    assert result["score_match"].tolist() == [True, False]
    assert result["best_index_match"].tolist() == [True, True]
    assert result["row_match"].tolist() == [True, False]


if __name__ == "__main__":
    test_four_week_delay_and_notebook_lookback()
    test_requested_ids_are_intersected_with_eligible_window()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        test_score_upsert_is_single_file_and_replaces_ids(Path(directory))
        test_explicit_empty_run_plan_never_expands_to_all_metadata(Path(directory))
        test_gee_export_credentials_accept_official_ee_token_format(Path(directory))
    test_legacy_drive_export_parameters_are_unchanged()
    test_score_regression_comparison_requires_exact_index_and_score()
    print("test_sentinel_gee.py: OK")

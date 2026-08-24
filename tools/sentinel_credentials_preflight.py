#!/usr/bin/env python3
"""Fail before Slurm submission when unattended Sentinel credentials are incomplete."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain a JSON object: {path}")
    return value


def configured_path(
    settings: dict[str, Any],
    config_path: Path,
    setting: str,
    environment: str,
) -> Path:
    value = os.environ.get(environment, "").strip()
    value = value or str(settings.get(setting, "")).strip()
    if not value:
        raise RuntimeError(f"Missing Sentinel credential setting: {setting}")
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_path.resolve().parent / path


def token_scopes(payload: dict[str, Any]) -> set[str]:
    value = payload.get("scopes", payload.get("scope", ()))
    if isinstance(value, str):
        return set(value.split())
    return {str(item) for item in (value or ())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    settings = config["sentinel2_download"]
    if not bool(settings.get("gee_drive_export_enabled", False)):
        print("Sentinel credential preflight: GEE Drive export disabled")
        return 0

    service_key_path = configured_path(
        settings,
        args.config,
        "gee_service_account_key_path",
        "BIOOTON_GEE_SERVICE_ACCOUNT_KEY",
    )
    export_token_path = configured_path(
        settings,
        args.config,
        "gee_export_oauth_token_path",
        "BIOOTON_GEE_EXPORT_TOKEN",
    )
    drive_credentials_path = configured_path(
        settings,
        args.config,
        "credentials_path",
        "BIOOTON_DRIVE_CREDENTIALS",
    )
    drive_token_path = configured_path(
        settings,
        args.config,
        "token_path",
        "BIOOTON_DRIVE_TOKEN",
    )

    service_key = load_json(service_key_path, "GEE service-account key")
    if service_key.get("type") != "service_account" or not service_key.get("client_email"):
        raise RuntimeError("GEE service-account key has the wrong structure")

    export_token = load_json(export_token_path, "GEE user export token")
    if not export_token.get("refresh_token"):
        raise RuntimeError("GEE user export token has no refresh_token")
    export_scopes = token_scopes(export_token)
    required_export_scopes = {
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/drive",
    }
    if export_scopes and not required_export_scopes.issubset(export_scopes):
        raise RuntimeError(
            "GEE user export token lacks Earth Engine or Drive scope"
        )

    drive_credentials = load_json(drive_credentials_path, "Drive OAuth client")
    if not any(key in drive_credentials for key in ("installed", "web")):
        raise RuntimeError("Drive OAuth client has the wrong structure")
    drive_token = load_json(drive_token_path, "Drive read-only token")
    if not drive_token.get("refresh_token"):
        raise RuntimeError("Drive read-only token has no refresh_token")

    import ee  # noqa: F401
    from google.oauth2.credentials import Credentials  # noqa: F401
    from googleapiclient.discovery import build  # noqa: F401
    from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401

    print("Sentinel credential preflight: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: Sentinel credential preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

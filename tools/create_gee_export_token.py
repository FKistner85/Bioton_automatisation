#!/usr/bin/env python3
"""One-time OAuth bootstrap for unattended user-owned EE Drive exports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import ee


SCOPES = list(ee.oauth.SCOPES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ee.Authenticate(
        auth_mode="localhost",
        scopes=SCOPES,
        force=True,
        quiet=args.no_browser,
    )
    earth_engine_credentials = Path(ee.oauth.get_credentials_path())
    payload = json.loads(earth_engine_credentials.read_text(encoding="utf-8"))
    if not payload.get("refresh_token"):
        raise RuntimeError("Earth Engine returned no persistent refresh token")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, args.output)
    print(f"Stored unattended GEE export token: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

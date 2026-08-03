#!/usr/bin/env python3
"""Mount the Bio-O-Ton LSDF project on Windows using SSHFS-Win and keyring."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import keyring


def load_settings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


def find_sshfs() -> str:
    candidates = [
        shutil.which("sshfs.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "SSHFS-Win", "bin", "sshfs.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "SSHFS-Win", "bin", "sshfs.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        "SSHFS-Win wurde nicht gefunden. Installiere zuerst WinFsp und SSHFS-Win."
    )


def is_ready(root: Path) -> bool:
    return root.is_dir() and (root / "PointData").is_dir()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=30)
    args = parser.parse_args()

    if os.name != "nt":
        print("ERROR: Der lokale Mount-Helper ist fuer Windows vorgesehen.", file=sys.stderr)
        return 2

    settings = load_settings(args.settings)
    root = mount_root(settings)
    if is_ready(root):
        print(f"LSDF bereits eingebunden: {root}")
        return 0

    host = str(settings.get("lsdf_host", "os-login.lsdf.kit.edu"))
    user = str(settings.get("lsdf_user", "")).strip()
    service = str(settings.get("credential_service", "lsdf_kit"))
    remote = str(settings.get("remote_project_root", "")).strip()
    drive = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    if not user or not remote or not drive:
        raise ValueError("lsdf_user, remote_project_root und mount_drive muessen gesetzt sein.")

    password = keyring.get_password(service, user)
    if password is None:
        raise RuntimeError(
            "Kein LSDF-Passwort im Windows Credential Manager gefunden.\n"
            f"Einmalig ausfuehren: keyring.set_password('{service}', '{user}', 'DEIN_PASSWORT')"
        )

    sshfs = find_sshfs()
    command = [
        sshfs,
        f"{user}@{host}:{remote}",
        drive,
        "-o", "password_stdin",
        "-o", "reconnect",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "idmap=user",
    ]
    result = subprocess.run(
        command,
        input=password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    password = ""
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        print(f"ERROR: LSDF-Mount fehlgeschlagen: {detail}", file=sys.stderr)
        return result.returncode or 1

    deadline = time.monotonic() + max(1, args.wait_seconds)
    while time.monotonic() < deadline:
        if is_ready(root):
            print(f"LSDF verbunden: {root}")
            return 0
        time.sleep(1)
    print(f"ERROR: Mount wurde nicht rechtzeitig lesbar: {root}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


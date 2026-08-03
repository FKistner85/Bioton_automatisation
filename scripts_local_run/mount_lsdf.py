#!/usr/bin/env python3
"""Mount the Bio-O-Ton LSDF project on Windows using SSHFS-Win and keyring."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any


def load_settings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mount_root(settings: dict) -> Path:
    value = str(settings.get("mount_drive", "L:")).rstrip("\\/")
    return Path(value + "\\")


class NETRESOURCEW(ctypes.Structure):
    _fields_ = [
        ("dwScope", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("dwDisplayType", wintypes.DWORD),
        ("dwUsage", wintypes.DWORD),
        ("lpLocalName", wintypes.LPWSTR),
        ("lpRemoteName", wintypes.LPWSTR),
        ("lpComment", wintypes.LPWSTR),
        ("lpProvider", wintypes.LPWSTR),
    ]


RESOURCETYPE_DISK = 1
CONNECT_TEMPORARY = 0x00000004
NO_ERROR = 0
ERROR_ALREADY_ASSIGNED = 85
ERROR_DEVICE_ALREADY_REMEMBERED = 1202


def sshfs_unc(user: str, host: str, remote: str) -> str:
    # sshfs.r resolves PATH relative to the remote filesystem root.
    path = remote.strip("/\\").replace("/", "\\")
    return rf"\\sshfs.r\{user}@{host}\{path}"


def windows_error(code: int) -> str:
    try:
        return str(ctypes.WinError(code))
    except (ValueError, OSError):
        return f"Windows error {code}"


def load_mpr() -> Any:
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    mpr.WNetAddConnection2W.argtypes = [
        ctypes.POINTER(NETRESOURCEW),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    mpr.WNetAddConnection2W.restype = wintypes.DWORD
    mpr.WNetGetConnectionW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    mpr.WNetGetConnectionW.restype = wintypes.DWORD
    mpr.WNetCancelConnection2W.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    mpr.WNetCancelConnection2W.restype = wintypes.DWORD
    return mpr


def current_mapping(drive: str) -> str:
    mpr = load_mpr()
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    result = mpr.WNetGetConnectionW(drive, buffer, ctypes.byref(size))
    return buffer.value if result == NO_ERROR else ""


def cancel_mapping(drive: str) -> None:
    mpr = load_mpr()
    result = mpr.WNetCancelConnection2W(drive, 0, True)
    if result != NO_ERROR:
        raise OSError(f"Bestehendes Mapping konnte nicht getrennt werden: {windows_error(result)}")


def connect_network_provider(drive: str, unc: str, user: str, password: str) -> None:
    mpr = load_mpr()
    resource = NETRESOURCEW()
    resource.dwType = RESOURCETYPE_DISK
    resource.lpLocalName = drive
    resource.lpRemoteName = unc
    result = mpr.WNetAddConnection2W(
        ctypes.byref(resource),
        password,
        user,
        CONNECT_TEMPORARY,
    )
    if result in {ERROR_ALREADY_ASSIGNED, ERROR_DEVICE_ALREADY_REMEMBERED}:
        existing = current_mapping(drive)
        if existing.casefold() == unc.casefold():
            cancel_mapping(drive)
            result = mpr.WNetAddConnection2W(
                ctypes.byref(resource), password, user, CONNECT_TEMPORARY
            )
        else:
            raise OSError(
                f"Laufwerk {drive} ist bereits anders belegt: {existing or 'lokales Laufwerk'}"
            )
    if result != NO_ERROR:
        raise OSError(
            f"SSHFS-Win Netzwerkprovider fehlgeschlagen ({result}): {windows_error(result)}"
        )


def is_ready(root: Path) -> bool:
    return root.is_dir() and (root / "PointData").is_dir()


def main() -> int:
    import keyring

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

    unc = sshfs_unc(user, host, remote)
    try:
        try:
            connect_network_provider(drive, unc, user, password)
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    finally:
        password = ""

    deadline = time.monotonic() + max(1, args.wait_seconds)
    while time.monotonic() < deadline:
        if is_ready(root):
            print(f"LSDF verbunden: {root} -> {unc}")
            return 0
        time.sleep(1)
    mapped = current_mapping(drive)
    print(
        f"ERROR: Mapping wurde angelegt, aber der Projektpfad ist nicht lesbar: {root}\n"
        f"Mapping: {mapped or unc}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

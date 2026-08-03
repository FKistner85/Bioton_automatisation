from __future__ import annotations
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile, time, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any
import pandas as pd

LSDF_LOGICAL_PREFIX = "/lsdf/"
GFSE_LSDF_PREFIX = "/gfse/data/LSDF/lsdf01/lsdf/"
INVALID_LSDF01_PREFIX = "/lsdf01/lsdf/"

CANONICAL_STATUSES = {
    "not_started",
    "queued",
    "running",
    "complete",
    "validated",
    "missing",
    "has_issues",
    "partial",
    "failed",
    "outdated",
    "skipped",
    "not_applicable",
    "manual_review_required",
    "approved",
}

MANIFEST_PACKAGES = [
    "pandas",
    "geopandas",
    "pyogrio",
    "shapely",
    "pyarrow",
    "av",
    "Pillow",
    "rasterio",
    "requests",
    "xarray",
    "rioxarray",
]

# These products evolve independently and therefore intentionally use
# separate schema versions.
STEP_MANIFEST_SCHEMA_VERSION = "2026-07-23-step-manifest-v2"
BATCH_STATUS_SCHEMA_VERSION = "2026-07-23-batch-status-v2"
PROGRESS_SNAPSHOT_SCHEMA_VERSION = "2026-07-29-progress-v1"


@dataclass
class ResolvedPath:
    label: str
    configured: Path
    resolved: Path
    checked: list[Path]
    exists: bool
    is_file: bool
    is_dir: bool
    readable: bool

    def format_report(self) -> str:
        return "\n".join(
            [
                f"Configured {self.label} path: {self.configured}",
                f"Resolved {self.label} path: {self.resolved}",
                f"Exists: {self.exists}",
                f"Is file: {self.is_file}",
                f"Is directory: {self.is_dir}",
                f"Readable: {self.readable}",
                "Checked paths:",
                *[f"- {path}" for path in self.checked],
            ]
        )

def load_config(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def lsdf_path_candidates(path: str | Path) -> list[Path]:
    configured = Path(path)
    text = configured.as_posix()
    candidates: list[Path] = [configured]

    def add(value: str) -> None:
        candidate = Path(value)
        if candidate not in candidates:
            candidates.append(candidate)

    if text.startswith(GFSE_LSDF_PREFIX):
        logical = text.replace(GFSE_LSDF_PREFIX, LSDF_LOGICAL_PREFIX, 1)
        add(logical)
    elif text.startswith(LSDF_LOGICAL_PREFIX):
        suffix = text[len(LSDF_LOGICAL_PREFIX):]
        add(GFSE_LSDF_PREFIX + suffix)
    elif text.startswith(INVALID_LSDF01_PREFIX):
        suffix = text[len(INVALID_LSDF01_PREFIX):]
        corrected = LSDF_LOGICAL_PREFIX + suffix
        add(corrected)
        add(GFSE_LSDF_PREFIX + suffix)

    return candidates


def resolve_existing_path(
    path: str | Path,
    label: str,
    expected: str = "any",
    required: bool = True,
) -> ResolvedPath:
    checked = lsdf_path_candidates(path)
    selected: Path | None = None
    selected_stat = {
        "exists": False,
        "is_file": False,
        "is_dir": False,
        "readable": False,
    }

    for candidate in checked:
        exists = candidate.exists()
        is_file = candidate.is_file()
        is_dir = candidate.is_dir()
        readable = os.access(candidate, os.R_OK) if exists else False
        kind_ok = (
            expected == "any"
            or (expected == "file" and is_file)
            or (expected == "dir" and is_dir)
        )
        if exists and readable and kind_ok:
            selected = candidate
            selected_stat = {
                "exists": exists,
                "is_file": is_file,
                "is_dir": is_dir,
                "readable": readable,
            }
            break

    if selected is None:
        selected = checked[0]
        if selected.exists():
            selected_stat = {
                "exists": True,
                "is_file": selected.is_file(),
                "is_dir": selected.is_dir(),
                "readable": os.access(selected, os.R_OK),
            }

    result = ResolvedPath(
        label=label,
        configured=Path(path),
        resolved=selected,
        checked=checked,
        **selected_stat,
    )

    if required and (
        not result.exists
        or not result.readable
        or (expected == "file" and not result.is_file)
        or (expected == "dir" and not result.is_dir)
    ):
        raise FileNotFoundError(
            f"ERROR: {label} path not found or not readable.\n"
            + result.format_report()
        )

    return result


def resolve_output_path(path: str | Path) -> Path:
    candidates = lsdf_path_candidates(path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
        parent = candidate.parent
        if parent.exists() and os.access(parent, os.W_OK):
            return candidate
    return candidates[0]


def print_path_report(result: ResolvedPath) -> None:
    print(result.format_report())

def ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def normalize_id(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def read_ids_file(path: str | Path | None) -> set[str]:
    if not path:
        return set()
    source = Path(path)
    if not source.is_file() or source.stat().st_size == 0:
        return set()
    frame = pd.read_csv(source, low_memory=False, dtype="string")
    for column in ("dawn_chorus_id", "id", "recording_id"):
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce").dropna().astype("int64")
            return {str(value) for value in values.tolist()}
    raise KeyError(f"No ID column found in {source}")


def find_id_column(df: pd.DataFrame) -> str:
    for c in ("dawn_chorus_id", "id", "recording_id"):
        if c in df.columns:
            return c
    raise KeyError("Keine ID-Spalte gefunden; erwartet: dawn_chorus_id oder id.")

def atomic_write_csv(df: pd.DataFrame, path: str | Path) -> None:
    p = ensure_parent(path)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, dir=p.parent, encoding="utf-8", newline="") as tmp:
        tmp_path = Path(tmp.name)
        df.to_csv(tmp, index=False)
    tmp_path.replace(p)

def atomic_write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = ensure_parent(path)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=p.parent, encoding="utf-8") as tmp:
        tmp_path = Path(tmp.name)
        json.dump(payload, tmp, indent=2, sort_keys=True, default=str)
        tmp.write("\n")
    tmp_path.replace(p)

def atomic_write_text(path: str | Path, text: str) -> None:
    p = ensure_parent(path)
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=p.suffix or ".txt",
        delete=False,
        dir=p.parent,
        encoding="utf-8",
        newline="",
    ) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(text)
    tmp_path.replace(p)

def backup_file(path: str | Path, backup_dir: str | Path, keep_last: int = 10) -> Path | None:
    src = Path(path)
    if not src.exists():
        return None
    dst_dir = Path(backup_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = dst_dir / f"{src.stem}_{stamp}{src.suffix}"
    shutil.copy2(src, dst)
    backups = sorted(dst_dir.glob(f"{src.stem}_*{src.suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep_last:]:
        old.unlink(missing_ok=True)
    return dst

def parse_id_from_filename(name: str) -> int | None:
    m = re.match(r"^(\d+)(?:[_\-.]|$)", Path(name).name)
    return int(m.group(1)) if m else None

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def safe_name(value: str | int) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "item"

def file_fingerprint(path: str | Path, hash_bytes: int = 1024 * 1024) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    stat = p.stat()
    result: dict[str, Any] = {
        "path": str(p),
        "exists": True,
        "kind": "dir" if p.is_dir() else "file",
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }
    if p.is_file():
        digest = hashlib.sha256()
        with p.open("rb") as handle:
            digest.update(handle.read(hash_bytes))
            if stat.st_size > hash_bytes:
                handle.seek(max(0, stat.st_size - hash_bytes))
                digest.update(handle.read(hash_bytes))
        result["edge_sha256"] = digest.hexdigest()
    return result

def dependency_fingerprints(paths: list[str | Path]) -> list[dict[str, Any]]:
    return [file_fingerprint(path) for path in paths]

def output_is_nonempty(path: str | Path) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    if p.is_file():
        return p.stat().st_size > 0
    if p.is_dir():
        try:
            return any(True for _ in p.iterdir())
        except OSError:
            return False
    return False

def processed_root_from_config(cfg: dict[str, Any]) -> Path:
    if cfg.get("processed_root"):
        return resolve_output_path(cfg["processed_root"])
    if cfg.get("status_dir"):
        status = resolve_output_path(cfg["status_dir"])
        if status.name == "_status":
            return status.parent
        if status.parent.name == "_status":
            return status.parent.parent
        return status.parent
    return resolve_output_path("processed")

def manifest_root(cfg: dict[str, Any]) -> Path:
    return resolve_output_path(cfg.get("manifest_dir", processed_root_from_config(cfg) / "_manifests"))

def slurm_context() -> dict[str, str]:
    keys = [
        "SLURM_JOB_ID",
        "SLURM_JOB_NAME",
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_PARTITION",
        "SLURM_SUBMIT_DIR",
        "SLURM_SUBMIT_HOST",
        "HOSTNAME",
    ]
    return {key: os.environ.get(key, "") for key in keys if os.environ.get(key)}

def workflow_run_id() -> str:
    configured = os.environ.get("BIOOTON_RUN_ID", "").strip()
    if configured:
        return configured
    return (
        f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_"
        f"{os.environ.get('SLURM_JOB_ID', 'local')}_{uuid.uuid4().hex[:8]}"
    )

def runtime_environment() -> dict[str, Any]:
    versions: dict[str, str] = {}
    for package in MANIFEST_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = ""
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": versions,
    }

def start_step_manifest(
    cfg: dict[str, Any],
    step_name: str,
    config_path: str | Path | None = None,
    inputs: list[str | Path] | None = None,
    outputs: list[str | Path] | None = None,
    parameters: dict[str, Any] | None = None,
    force: bool = False,
    batch_count: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    workflow_id = workflow_run_id()
    step_run_id = (
        f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_"
        f"{os.environ.get('SLURM_JOB_ID', 'local')}_{uuid.uuid4().hex[:8]}"
    )
    path = manifest_root(cfg) / step_name / f"{step_run_id}.json"
    payload: dict[str, Any] = {
        "schema_version": STEP_MANIFEST_SCHEMA_VERSION,
        "workflow_run_id": workflow_id,
        "run_id": step_run_id,
        "step_run_id": step_run_id,
        "step_name": step_name,
        "status": "running",
        "started_utc": utc_now_iso(),
        "finished_utc": "",
        "force": bool(force),
        "config_path": str(config_path) if config_path is not None else "",
        "inputs": [str(path) for path in inputs or []],
        "input_fingerprints": dependency_fingerprints(inputs or []),
        "outputs": [str(path) for path in outputs or []],
        "parameters": parameters or {},
        "batch_count": batch_count,
        "slurm": slurm_context(),
        "runtime": runtime_environment(),
        "stdout_log": os.environ.get("BIOOTON_STDOUT_LOG", ""),
        "stderr_log": os.environ.get("BIOOTON_STDERR_LOG", ""),
        "result": {},
        "warnings": [],
        "error": "",
    }
    atomic_write_json(path, payload)
    return path, payload

def finish_step_manifest(
    path: str | Path,
    manifest: dict[str, Any],
    status: str,
    result: dict[str, Any] | None = None,
    error: str = "",
    warnings: list[str] | None = None,
) -> None:
    if status not in CANONICAL_STATUSES:
        raise ValueError(f"Unknown canonical status: {status}")
    payload = dict(manifest)
    payload["status"] = status
    payload["finished_utc"] = utc_now_iso()
    payload["result"] = result or {}
    payload["error"] = error
    payload["warnings"] = warnings or []
    payload["output_fingerprints"] = dependency_fingerprints(payload.get("outputs", []))
    atomic_write_json(path, payload)

def write_batch_status(
    directory: str | Path,
    batch_id: str | int,
    status: str,
    inputs: list[str | Path] | None = None,
    outputs: list[str | Path] | None = None,
    result: dict[str, Any] | None = None,
    error: str = "",
    started_utc: str | None = None,
) -> Path:
    if status not in CANONICAL_STATUSES:
        raise ValueError(f"Unknown canonical status: {status}")
    status_path = Path(directory) / f"{safe_name(batch_id)}.json"
    payload = {
        "schema_version": BATCH_STATUS_SCHEMA_VERSION,
        "workflow_run_id": workflow_run_id(),
        "batch_id": str(batch_id),
        "status": status,
        "started_utc": started_utc or utc_now_iso(),
        "finished_utc": utc_now_iso() if status in {"complete", "failed", "skipped"} else "",
        "inputs": [str(item) for item in inputs or []],
        "outputs": [str(item) for item in outputs or []],
        "output_fingerprints": dependency_fingerprints(outputs or []),
        "result": result or {},
        "error": error,
    }
    atomic_write_json(status_path, payload)
    return status_path


def write_progress_snapshot(
    path: str | Path,
    *,
    step_name: str,
    total_batches: int,
    completed_batches: int,
    succeeded: int = 0,
    failed: int = 0,
    skipped: int = 0,
    started_monotonic: float | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a cheap, overwrite-safe progress/ETA product after each batch."""
    elapsed = max(0.0, time.monotonic() - started_monotonic) if started_monotonic else 0.0
    rate = completed_batches / elapsed if elapsed > 0 else 0.0
    remaining = max(0, total_batches - completed_batches)
    eta = remaining / rate if rate > 0 else None
    payload = {
        "schema_version": PROGRESS_SNAPSHOT_SCHEMA_VERSION,
        "workflow_run_id": workflow_run_id(),
        "step_name": step_name,
        "updated_utc": utc_now_iso(),
        "total_batches": int(total_batches),
        "completed_batches": int(completed_batches),
        "remaining_batches": int(remaining),
        "succeeded": int(succeeded),
        "failed": int(failed),
        "skipped": int(skipped),
        "elapsed_seconds": round(elapsed, 3),
        "mean_seconds_per_batch": round(elapsed / completed_batches, 3) if completed_batches else None,
        "estimated_remaining_seconds": round(eta, 3) if eta is not None else None,
        "estimated_finished_utc": "",
        "extra": extra or {},
    }
    if eta is not None:
        payload["estimated_finished_utc"] = datetime.fromtimestamp(
            time.time() + eta,
            tz=timezone.utc,
        ).isoformat()
    atomic_write_json(path, payload)
    return Path(path)


def run_mastertable_batch_update(
    config_path: str | Path,
    ids: list[str],
    *,
    step_name: str,
    request_dir: str | Path,
    timeout_seconds: int = 900,
) -> bool:
    """Run a serialized mastertable partial update after a persisted batch.

    The mastertable script owns the cross-process write lock. This helper only
    creates a traceable ID request and invokes it after step outputs are durable.
    """
    unique_ids = sorted({str(value) for value in ids if str(value).strip()})
    if not unique_ids:
        return False
    directory = Path(request_dir)
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / f"{safe_name(step_name)}_{utc_now_iso().replace(':', '').replace('+', '_')}_{uuid.uuid4().hex[:8]}.csv"
    atomic_write_csv(pd.DataFrame({"dawn_chorus_id": unique_ids}), request)
    master_script = Path(__file__).resolve().parent / "Step_7_0_update_master_table.py"
    command = [
        sys.executable,
        str(master_script),
        "--config",
        str(config_path),
        "--ids-file",
        str(request),
    ]
    try:
        result = subprocess.run(command, check=False, timeout=timeout_seconds)
    except Exception as exc:
        print(f"WARNING: Batch mastertable update failed to start for {step_name}: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"WARNING: Batch mastertable update failed for {step_name} (exit {result.returncode}).", file=sys.stderr)
        return False
    return True

def status_path(cfg: dict, filename: str) -> Path:
    p = Path(cfg["status_dir"]) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def source_signature(paths: list[str | Path]) -> str:
    values=[]
    for raw in paths:
        p=Path(raw)
        if not p.exists():
            values.append(f"{p}:missing")
        elif p.is_file():
            st=p.stat()
            values.append(f"{p}:{st.st_size}:{st.st_mtime_ns}")
        else:
            st=p.stat()
            values.append(f"{p}:dir:{st.st_mtime_ns}")
    return hashlib.sha256("|".join(values).encode()).hexdigest()

def should_skip(run_meta_path: Path, signature: str) -> bool:
    if not run_meta_path.exists():
        return False
    try:
        old=json.loads(run_meta_path.read_text(encoding="utf-8"))
        return old.get("success") is True and old.get("source_signature")==signature
    except Exception:
        return False

def write_run_meta(path: Path, step: str, signature: str, outputs: list[str], row_count: int, success: bool=True, error: str="") -> None:
    payload={
        "pipeline_step": step,
        "workflow_run_id": workflow_run_id(),
        "run_finished_utc": utc_now_iso(),
        "source_signature": signature,
        "outputs": outputs,
        "row_count": int(row_count),
        "success": bool(success),
        "error": error,
    }
    atomic_write_json(path, payload)

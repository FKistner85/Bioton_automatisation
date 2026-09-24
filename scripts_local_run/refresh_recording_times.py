"""Apply an audited time correction locally, with backups and full verification.

Does not publish or run spatial, weather, media or remote processing.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "scripts")]
import pipeline_lock
from audit_recording_times import audit, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--verified-audit", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    verified = json.loads(args.verified_audit.read_text(encoding="utf-8"))
    workspace = Path(config["local_runtime"]["workspace_dir"]).resolve()
    source = Path(config["dawn_chorus_csv"]).resolve()
    status = Path(config["status_dir"]).resolve()
    master = Path(config["master_table"]["output_csv"]).resolve()
    short = master.with_name("Bio_O_Ton_Master_CI_TEC.csv")
    lock = Path(config["pipeline_control"]["lock_dir"]).resolve()
    paths = [source, status, master, short, lock,
             Path(config["metadata_extraction"]["fingerprint_csv"]).resolve(),
             Path(config["master_table"]["output_parquet"]).resolve(),
             Path(config["master_table"]["summary_json"]).resolve(),
             Path(config["pipeline_control"]["status_event_csv"]).resolve()]
    for path in paths:
        if not path.is_relative_to(workspace) or path == workspace:
            raise ValueError(f"Refusing a target outside the local workspace: {path}")
    if sha(source) != verified["source_sha256"] or sha(master) != verified["baseline_sha256"]:
        raise ValueError("Source or master changed since the reviewed audit; audit again first")
    if any(verified[key] for key in ["unresolved", "local_clock_mismatches", "utc_fallback_mismatches"]):
        raise ValueError("The reviewed audit contains unresolved timestamp failures")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"local_time_correction_{stamp}_{os.getpid()}"
    backup = workspace / "backups" / run_id
    if pipeline_lock.acquire(lock, run_id, os.getpid()) != 0:
        raise RuntimeError("Local pipeline lock is already held")
    try:
        backup.mkdir(parents=True, exist_ok=False)
        backup_files = [*paths[2:4], *paths[5:], *status.glob("*.csv")]
        for path in dict.fromkeys(backup_files):
            if path.is_file():
                target = backup / path.relative_to(workspace)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        baseline = backup / master.relative_to(workspace)
        print(f"Backup: {backup}", flush=True)
        for script, extra in [
            ("scripts/Step_1_metadata_extraction.py", ["--config", str(args.config), "--force"]),
            ("scripts/Step_7_0_update_master_table.py", ["--config", str(args.config), "--preserve-existing-nonformation-domains"]),
        ]:
            subprocess.run([sys.executable, str(ROOT / script), *extra], cwd=ROOT, check=True)
        summary = audit(source, baseline, args.report_dir, master)
        summary["verified_lsdf_audit"] = str(args.verified_audit.resolve())
        summary["lsdf_source"] = verified["source"]
        summary["lsdf_and_local_source_sha256_equal"] = True
        summary["backup_directory"] = str(backup)
        (args.report_dir / "recording_time_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        # lock was resolved and checked against the workspace before acquisition.
        pipeline_lock.release(lock, run_id, force=False)


if __name__ == "__main__":
    main()

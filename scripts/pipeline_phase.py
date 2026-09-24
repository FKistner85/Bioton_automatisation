"""Execution scope shared by planners, master updates and validation."""
from __future__ import annotations

import json
import os
from pathlib import Path


def execution_phase() -> str:
    path = os.environ.get("BIOOTON_RUN_PLAN", "").strip()
    if not path:
        return "all"  # Direct maintenance commands retain their existing behavior.
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    phase = plan.get("phase", "all")
    if phase not in {"core", "bioacoustics", "all"}:
        raise ValueError(f"Unknown pipeline phase: {phase}")
    return phase

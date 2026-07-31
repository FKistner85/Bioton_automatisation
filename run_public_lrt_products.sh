#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${BIOOTON_CONFIG:-$SCRIPT_DIR/config.horeka.json}"
PYTHON_BIN="${PYTHON:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(bash "$SCRIPT_DIR/bootstrap_env.sh" | tail -n 1)"
fi

FORCE_ARGS=()
if [[ "${1:-}" == "--force" ]]; then
  FORCE_ARGS=(--force)
fi

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/Step_2_5_clean_public_lrts.py" --config "$CONFIG" "${FORCE_ARGS[@]}"
"$PYTHON_BIN" "$SCRIPT_DIR/scripts/Step_2_6_merge_public_lrts_and_grid.py" --config "$CONFIG" "${FORCE_ARGS[@]}"

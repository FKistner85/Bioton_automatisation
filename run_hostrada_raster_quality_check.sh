#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${BIOOTON_CONFIG:-$SCRIPT_DIR/config.horeka.json}"
PYTHON_BIN="${PYTHON:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(bash "$SCRIPT_DIR/bootstrap_env.sh" | tail -n 1)"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/Step_5_5_check_hostrada_raster_products.py" --config "$CONFIG" "$@"

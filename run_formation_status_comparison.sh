#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi

"${PYTHON}" "${PIPELINE_DIR}/tools/compare_formation_status_products.py" \
  --config "${CONFIG}"

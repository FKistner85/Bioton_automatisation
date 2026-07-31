#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: bash run_hostrada_raster_year.sh <Variable> <Year> [--force]" >&2
  echo "Variables: Ta Rh Radiation CloudCover Winddirection Windspeed" >&2
  exit 2
fi

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
VARIABLE="$1"
YEAR="$2"
FORCE_ARG="${3:-}"
if [[ -n "${FORCE_ARG}" && "${FORCE_ARG}" != "--force" ]]; then
  echo "Unknown optional argument: ${FORCE_ARG}" >&2
  exit 2
fi

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi

"${PYTHON}" "${PIPELINE_DIR}/scripts/Step_5_4_prepare_hostrada_rasters.py" \
  --config "${CONFIG}" \
  --variable "${VARIABLE}" \
  --year "${YEAR}" \
  ${FORCE_ARG}

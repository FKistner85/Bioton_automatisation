#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
SCRIPTS="${PIPELINE_DIR}/scripts"
RUN_DOWNLOADS=0
FORCE=0

usage() {
  cat <<'EOF'
Usage: bash run_step3_direct.sh [--run-downloads] [--force]

Runs Step 3 directly on HoreKa/haicore/LSDF paths:
  Step_3_0_a_audio_inventory.py
  Step_3_0_b_photo_inventory.py
  optionally Step_3_1_a_audio_download.py
  optionally Step_3_1_b_photo_download.py
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-downloads) RUN_DOWNLOADS=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -f "${CONFIG}" ]] || { echo "Missing config: ${CONFIG}" >&2; exit 1; }

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi

common_args=(--config "${CONFIG}")
if [[ "${FORCE}" -eq 1 ]]; then
  common_args+=(--force)
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

"${PYTHON}" "${PIPELINE_DIR}/tools/step3_path_preflight.py" --config "${CONFIG}"
"${PYTHON}" "${SCRIPTS}/Step_3_0_a_audio_inventory.py" "${common_args[@]}"
"${PYTHON}" "${SCRIPTS}/Step_3_0_b_photo_inventory.py" "${common_args[@]}"

if [[ "${RUN_DOWNLOADS}" -eq 1 ]]; then
  "${PYTHON}" "${SCRIPTS}/Step_3_1_a_audio_download.py" "${common_args[@]}"
  "${PYTHON}" "${SCRIPTS}/Step_3_1_b_photo_download.py" "${common_args[@]}"
else
  echo "Step 3 download steps skipped. Add --run-downloads to run Step_3_1_a and Step_3_1_b."
fi

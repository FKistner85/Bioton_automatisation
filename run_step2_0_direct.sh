#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
SCRIPT="${PIPELINE_DIR}/scripts/Step_2_0_clean_lrts.py"
FORCE=0

usage() {
  cat <<'EOF'
Usage: bash run_step2_0_direct.sh [--force]

Runs Step_2_0_clean_lrts.py directly on HoreKa/haicore using config.horeka.json.
Use --force after changing the LRT formation definition.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -f "${CONFIG}" ]] || { echo "Missing config: ${CONFIG}" >&2; exit 1; }
[[ -f "${SCRIPT}" ]] || { echo "Missing script: ${SCRIPT}" >&2; exit 1; }

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi

[[ -x "${PYTHON}" ]] || { echo "Missing Python executable: ${PYTHON}" >&2; exit 1; }

args=(--config "${CONFIG}")
if [[ "${FORCE}" -eq 1 ]]; then
  args+=(--force)
fi

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

echo "Python: ${PYTHON}"
echo "Config: ${CONFIG}"
echo "Script: ${SCRIPT}"

"${PYTHON}" "${SCRIPT}" "${args[@]}"

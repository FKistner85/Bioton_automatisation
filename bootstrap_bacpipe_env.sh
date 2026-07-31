#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PREFIX="${BIOOTON_BACPIPE_ENV_PREFIX:-${PIPELINE_DIR}/.venv_bacpipe}"
PYTHON="${ENV_PREFIX}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 "${ENV_PREFIX}"
  elif command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv "${ENV_PREFIX}"
  elif [[ -x "${PIPELINE_DIR}/.venv/bin/python" ]] \
    && "${PIPELINE_DIR}/.venv/bin/python" -c \
      'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)'
  then
    "${PIPELINE_DIR}/.venv/bin/python" -m venv "${ENV_PREFIX}"
  else
    echo "Python 3.11 is required for Bacpipe and was not found." >&2
    exit 1
  fi
fi

"${PYTHON}" -m pip install --upgrade pip
"${PYTHON}" -m pip install -r "${PIPELINE_DIR}/requirements.bacpipe.txt"
"${PYTHON}" -c 'import bacpipe, pandas, pyarrow, torch; print("Bacpipe environment OK")'
echo "${PYTHON}"

#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PREFIX="${BIOOTON_ENV_PREFIX:-${PIPELINE_DIR}/.venv}"
PYTHON="${ENV_PREFIX}/bin/python"

check_imports() {
  "${PYTHON}" - <<'PY'
import pandas, geopandas, pyogrio, shapely, pyarrow, av, rasterio, requests, xarray, netCDF4, pyproj, tqdm
from PIL import Image
print("Bio-O-Ton Python dependencies OK")
PY
}

if [[ -x "${PYTHON}" ]]; then
  if check_imports; then
    echo "${PYTHON}"
    exit 0
  fi
fi

if command -v micromamba >/dev/null 2>&1; then
  micromamba create -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml"
elif command -v mamba >/dev/null 2>&1; then
  mamba env create -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml" || \
    mamba env update -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml"
elif command -v conda >/dev/null 2>&1; then
  conda env create -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml" || \
    conda env update -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml"
else
  python3 -m venv "${ENV_PREFIX}"
  "${PYTHON}" -m pip install --upgrade pip
  "${PYTHON}" -m pip install -r "${PIPELINE_DIR}/requirements.hpc.txt"
fi

check_imports
echo "${PYTHON}"

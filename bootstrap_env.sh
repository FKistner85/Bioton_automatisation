#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${PIPELINE_DIR}/cluster_profile.sh"
ENV_PREFIX="${BIOOTON_ENV_PREFIX:-${PIPELINE_DIR}/.venv}"
PYTHON="${ENV_PREFIX}/bin/python"

check_imports() {
  "${PYTHON}" - <<'PY'
import pandas, geopandas, pyogrio, shapely, pyarrow, av, rasterio, requests, xarray, netCDF4, pyproj, tqdm
import sys
import ee
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from PIL import Image
assert sys.version_info >= (3, 11), f"Python 3.11+ required, found {sys.version}"
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
  micromamba create -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml" || \
    micromamba update -y -p "${ENV_PREFIX}" -f "${PIPELINE_DIR}/environment.hpc.yml"
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

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
CONFIG="${CONFIG:-${ROOT}/config.horeka.json}"
SAMPLE_SIZE="${BIOOTON_SENTINEL_SCORE_SAMPLE_SIZE:-100}"
REFERENCE_MIN_DATE="${BIOOTON_SENTINEL_SCORE_REFERENCE_MIN_DATE:-2026-01-01}"
REPORT="${BIOOTON_SENTINEL_SCORE_REPORT:-/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_4_1_sentinel2_download/score_validation_${SAMPLE_SIZE}.csv}"

exec "${PYTHON}" "${ROOT}/tools/validate_sentinel_scores.py" \
  --config "${CONFIG}" \
  --report-csv "${REPORT}" \
  --sample-size "${SAMPLE_SIZE}" \
  --chunk-size 100 \
  --reference-min-date "${REFERENCE_MIN_DATE}"

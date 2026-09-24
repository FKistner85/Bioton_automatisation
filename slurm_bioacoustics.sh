#!/usr/bin/env bash
set -euo pipefail
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${PIPELINE_DIR}/submit_bio_o_ton_horeka.sh" bioacoustics

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CONFIG="${CONFIG:-${ROOT}/config.horeka.json}"
PYTHON="${PYTHON:-}"
FORCE=0
ALLOW_INTERACTIVE_AUTH=0

usage() {
  cat <<'EOF'
Usage: bash run_sentinel2_mirror.sh [--force] [--allow-interactive-auth]

Mirrors externally generated Sentinel-2 GeoTIFFs from the configured Google
Drive folder into PointData/S2 and validates downloaded/local files.

For unattended HoreKa runs, prepare token.json once and do not use
--allow-interactive-auth.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --allow-interactive-auth) ALLOW_INTERACTIVE_AUTH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PYTHON" ]]; then
  PYTHON="$(bash "$ROOT/bootstrap_env.sh" | tail -n 1)"
fi

args=(--config "$CONFIG")
[[ "$FORCE" -eq 1 ]] && args+=(--force)
[[ "$ALLOW_INTERACTIVE_AUTH" -eq 1 ]] && args+=(--allow-interactive-auth)

"$PYTHON" "$ROOT/scripts/Step_4_1_Sentinel2_download.py" "${args[@]}"

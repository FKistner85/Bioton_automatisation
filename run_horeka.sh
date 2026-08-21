#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-add_new_ids}"
shift || true

FOREGROUND=0
UPDATE=0
BRANCH="main"
SESSION=""
LOCAL_TEST=0

usage() {
  cat <<'EOF'
Usage: bash run_horeka.sh <mode> [options]

Modes:
  functionality_test
  add_new_ids
  from_scratch
  formation_compare

Options:
  --update             Pull the selected Git branch before starting.
  --branch <name>      Branch used with --update (default: main).
  --session <name>     tmux session name.
  --local-test         Run local control steps and print Slurm submissions.
  --foreground         Run the controller in the current shell.
EOF
}

case "${MODE}" in
  functionality_test|add_new_ids|from_scratch|formation_compare) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update) UPDATE=1; shift ;;
    --branch) BRANCH="${2:?Missing branch name}"; shift 2 ;;
    --session) SESSION="${2:?Missing session name}"; shift 2 ;;
    --local-test) LOCAL_TEST=1; shift ;;
    --foreground) FOREGROUND=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "${UPDATE}" -eq 1 ]]; then
  bash "${PIPELINE_DIR}/update_horeka_from_git.sh" "${BRANCH}"
fi

PYTHON="${PYTHON:-${PIPELINE_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi
[[ -x "${PYTHON}" ]] || { echo "Missing Python executable: ${PYTHON}" >&2; exit 1; }

if [[ "${FOREGROUND}" -eq 1 ]]; then
  controller_args=(
    --config "${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
    --mode "${MODE}"
  )
  [[ "${LOCAL_TEST}" -eq 1 ]] && controller_args+=(--local-test)
  exec "${PYTHON}" "${PIPELINE_DIR}/tools/horeka_controller.py" "${controller_args[@]}"
fi

command -v tmux >/dev/null 2>&1 || {
  echo "tmux is not available on this host. Use --foreground or load/install tmux." >&2
  exit 1
}

if [[ -z "${SESSION}" ]]; then
  SESSION="bioton_${MODE}_$(date -u +%Y%m%dT%H%M%SZ)"
fi
[[ "${SESSION}" =~ ^[A-Za-z0-9_.-]+$ ]] || {
  echo "Invalid tmux session name: ${SESSION}" >&2
  exit 2
}

local_test_arg=""
[[ "${LOCAL_TEST}" -eq 1 ]] && local_test_arg="--local-test"
printf -v controller_command \
  'cd %q && BIOOTON_TMUX_SESSION=%q PYTHON=%q bash %q %q --foreground %s' \
  "${PIPELINE_DIR}" "${SESSION}" "${PYTHON}" \
  "${PIPELINE_DIR}/run_horeka.sh" "${MODE}" "${local_test_arg}"

tmux new-session -d -s "${SESSION}" "${controller_command}"
echo "Started Bio-O-Ton controller in tmux session: ${SESSION}"
echo "Attach: tmux attach -t ${SESSION}"
echo "List:   tmux ls"

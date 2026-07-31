#!/usr/bin/env bash
set -euo pipefail

TAIL_LINES="${1:-160}"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
PYTHON="${PYTHON:-${PIPELINE_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi
LOGDIR="${BIOOTON_LOGDIR:-$("${PYTHON}" -c "import json; print(json.load(open('${CONFIG}', encoding='utf-8')).get('slurm_log_dir', ''))")}"
[[ -n "${LOGDIR}" ]] || { echo "Missing slurm_log_dir in config or BIOOTON_LOGDIR." >&2; exit 1; }

if [[ "${TAIL_LINES}" == "--full" ]]; then
  TAIL_LINES="full"
fi

START_TIME="$(date -d '24 hours ago' '+%Y-%m-%dT%H:%M:%S')"

echo "Pipeline dir : ${PIPELINE_DIR}"
echo "Log dir      : ${LOGDIR}"
echo "User         : ${USER}"
echo "Start time   : ${START_TIME}"
echo

echo "== sacct summary, last 24 hours =="
sacct -u "${USER}" \
  --starttime "${START_TIME}" \
  --format=JobID,JobName%24,State,ExitCode,Elapsed,Timelimit,Start,End

echo
echo "== squeue current =="
squeue -u "${USER}" -o "%.18i %.24j %.2t %.10M %.35R" || true

echo
echo "== finished/known top-level jobs and logs =="

mapfile -t JOB_ROWS < <(
  sacct -u "${USER}" \
    --starttime "${START_TIME}" \
    --parsable2 \
    --noheader \
    --format=JobIDRaw,JobName,State,ExitCode,Elapsed,Timelimit,Start,End |
    awk -F'|' '$1 !~ /\./ && $1 != "" {print}'
)

if [[ "${#JOB_ROWS[@]}" -eq 0 ]]; then
  echo "No sacct jobs found in the last 24 hours."
  exit 0
fi

print_log_file() {
  local label="$1"
  local path="$2"
  echo
  echo "--- ${label}: ${path} ---"
  if [[ ! -f "${path}" ]]; then
    echo "missing"
    return
  fi
  if [[ "${TAIL_LINES}" == "full" ]]; then
    cat "${path}"
  else
    tail -n "${TAIL_LINES}" "${path}"
  fi
}

for row in "${JOB_ROWS[@]}"; do
  IFS='|' read -r jobid jobname state exitcode elapsed timelimit start end <<< "${row}"
  echo
  echo "======================================================================"
  echo "JOB ${jobid} | ${jobname} | ${state} | exit=${exitcode} | elapsed=${elapsed} | limit=${timelimit}"
  echo "start=${start} end=${end}"

  shopt -s nullglob
  matches=( "${LOGDIR}/${jobname}_${jobid}.out" "${LOGDIR}/${jobname}_${jobid}.err" )
  fallback=( "${LOGDIR}"/*"${jobid}"*.out "${LOGDIR}"/*"${jobid}"*.err )
  shopt -u nullglob

  printed=0
  for path in "${matches[@]}"; do
    if [[ -f "${path}" ]]; then
      print_log_file "log" "${path}"
      printed=1
    fi
  done

  if [[ "${printed}" -eq 0 ]]; then
    for path in "${fallback[@]}"; do
      if [[ -f "${path}" ]]; then
        print_log_file "log" "${path}"
        printed=1
      fi
    done
  fi

  if [[ "${printed}" -eq 0 ]]; then
    echo
    echo "No slurm log file found for job ${jobid} in ${LOGDIR}."
  fi
done

echo
echo "== known pipeline run logs =="

known_logs=(
  "/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_5_2_weather_download/run_log.txt"
)

for path in "${known_logs[@]}"; do
  if [[ -f "${path}" ]]; then
    print_log_file "pipeline log" "${path}"
  fi
done

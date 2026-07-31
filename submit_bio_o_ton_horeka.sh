#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-add_new_ids}"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-${PIPELINE_DIR}/.venv/bin/python}"
BACPIPE_PYTHON="${BIOOTON_BACPIPE_PYTHON:-${PIPELINE_DIR}/.venv_bacpipe/bin/python}"
CONFIG="${CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
LOGDIR="${BIOOTON_LOGDIR:-}"

PARTITION="${BIOOTON_PARTITION:-cpuonly}"
BIOACOUSTICS_PARTITION="${BIOOTON_BIOACOUSTICS_PARTITION:-${PARTITION}}"
BIOACOUSTICS_GRES="${BIOOTON_BIOACOUSTICS_GRES:-}"
BIOACOUSTICS_MEMORY="${BIOOTON_BIOACOUSTICS_MEMORY:-48G}"
ACCOUNT="${BIOOTON_ACCOUNT:-}"
TIME_OVERRIDE="${BIOOTON_PIPELINE_TIME_OVERRIDE:-}"

STEP2_CPUS="${BIOOTON_STEP2_CPUS:-16}"
STEP24_CPUS="${BIOOTON_STEP24_CPUS:-16}"
STEP3_INVENTORY_CPUS="${BIOOTON_STEP3_INVENTORY_CPUS:-16}"
STEP3_DOWNLOAD_CPUS="${BIOOTON_STEP3_DOWNLOAD_CPUS:-16}"
STEP40_CPUS="${BIOOTON_STEP40_CPUS:-16}"
STEP41_CPUS="${BIOOTON_STEP41_CPUS:-1}"
STEP51_CPUS="${BIOOTON_STEP51_CPUS:-16}"
STEP52_CPUS="${BIOOTON_STEP52_CPUS:-16}"
WEATHER_SHARD_LIMIT="${BIOOTON_WEATHER_SHARD_COUNT:-}"
WEATHER_MAX_CONCURRENT="${BIOOTON_WEATHER_MAX_CONCURRENT_TASKS:-}"
HOSTRADA_RASTER_CPUS="${BIOOTON_STEP54_CPUS:-8}"
HOSTRADA_RASTER_MEMORY="${BIOOTON_STEP54_MEMORY:-32G}"
HOSTRADA_RASTER_MAX_CONCURRENT="${BIOOTON_STEP54_MAX_CONCURRENT_TASKS:-2}"
MASTER_CPUS="${BIOOTON_MASTER_CPUS:-2}"
FORMATION_COMPARE_CPUS="${BIOOTON_FORMATION_COMPARE_CPUS:-4}"
BIOACOUSTICS_CPUS="${BIOOTON_BIOACOUSTICS_CPUS:-16}"

usage() {
  cat <<'EOF'
Usage: bash submit_bio_o_ton_horeka.sh <mode>

Modes:
  functionality_test  Fast imports, config, schema, syntax and regression tests
  add_new_ids         Incremental run for new/changed/problematic IDs
  from_scratch        Full logical rebuild without deleting original downloads
  formation_compare   Compare generated formation products with reference data

Useful environment variables:
  BIOOTON_PARTITION=cpuonly
  BIOOTON_ACCOUNT=<account>
  BIOOTON_PIPELINE_TIME_OVERRIDE=00:30:00
  BIOOTON_STEP2_CPUS=16
  BIOOTON_STEP3_DOWNLOAD_CPUS=16
  BIOOTON_STEP52_CPUS=16
  BIOOTON_WEATHER_SHARD_COUNT=8
  BIOOTON_WEATHER_MAX_CONCURRENT_TASKS=4
  BIOOTON_STEP54_CPUS=8
  BIOOTON_STEP54_MEMORY=32G
  BIOOTON_STEP54_MAX_CONCURRENT_TASKS=2
  BIOOTON_BACPIPE_PYTHON=/path/to/.venv_bacpipe/bin/python
  BIOOTON_BIOACOUSTICS_PARTITION=cpuonly        # Standard, keine GPU noetig
  BIOOTON_BIOACOUSTICS_CPUS=16

GPU optional, falls der Account Zugriff hat:
  BIOOTON_BIOACOUSTICS_PARTITION=accelerated-h100
  BIOOTON_BIOACOUSTICS_GRES=gpu:1
EOF
}

case "${MODE}" in
  functionality_test|add_new_ids|from_scratch|formation_compare|susi_compare) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi
[[ -x "${PYTHON}" ]] || { echo "Missing Python executable." >&2; exit 1; }
[[ -f "${CONFIG}" ]] || { echo "Missing config: ${CONFIG}" >&2; exit 1; }
if [[ -z "${LOGDIR}" ]]; then
  LOGDIR="$("${PYTHON}" -c "import json; print(json.load(open('${CONFIG}', encoding='utf-8')).get('slurm_log_dir', ''))")"
fi
[[ -n "${LOGDIR}" ]] || { echo "Missing slurm_log_dir in config or BIOOTON_LOGDIR." >&2; exit 1; }
if [[ -z "${WEATHER_SHARD_LIMIT}" ]]; then
  WEATHER_SHARD_LIMIT="$("${PYTHON}" -c "import json; print(int(json.load(open('${CONFIG}', encoding='utf-8'))['weather_download'].get('slurm_shard_count', 8)))")"
fi
if [[ -z "${WEATHER_MAX_CONCURRENT}" ]]; then
  WEATHER_MAX_CONCURRENT="$("${PYTHON}" -c "import json; print(int(json.load(open('${CONFIG}', encoding='utf-8'))['weather_download'].get('slurm_max_concurrent_tasks', 4)))")"
fi
[[ "${WEATHER_SHARD_LIMIT}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid weather shard count: ${WEATHER_SHARD_LIMIT}" >&2; exit 1; }
[[ "${WEATHER_MAX_CONCURRENT}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid weather max concurrency: ${WEATHER_MAX_CONCURRENT}" >&2; exit 1; }
mkdir -p "${LOGDIR}"
BIOACOUSTICS_ENABLED="$("${PYTHON}" -c "import json; print('1' if json.load(open('${CONFIG}', encoding='utf-8')).get('bioacoustics', {}).get('enabled', True) else '0')")"
if [[ "${BIOACOUSTICS_ENABLED}" == "1" && "${MODE}" =~ ^(add_new_ids|from_scratch)$ && ! -x "${BACPIPE_PYTHON}" ]]; then
  BACPIPE_PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_bacpipe_env.sh" | tail -n 1)"
fi
if [[ "${BIOACOUSTICS_ENABLED}" == "1" && "${MODE}" =~ ^(add_new_ids|from_scratch)$ ]]; then
  [[ -x "${BACPIPE_PYTHON}" ]] || { echo "Missing Bacpipe Python executable." >&2; exit 1; }
fi

RUN_ID="${BIOOTON_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)_${USER:-user}_$$}"
LOG_STAMP="${BIOOTON_LOG_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
export BIOOTON_RUN_ID="${RUN_ID}"
export PYTHONUNBUFFERED=1

account_args=()
[[ -n "${ACCOUNT}" ]] && account_args=(--account="${ACCOUNT}")
bio_resource_args=()
[[ -n "${BIOACOUSTICS_GRES}" ]] && bio_resource_args=(--gres="${BIOACOUSTICS_GRES}")

apply_override() {
  if [[ -n "${TIME_OVERRIDE}" ]]; then
    echo "${TIME_OVERRIDE}"
  else
    echo "$1"
  fi
}

submit_python() {
  local job_name="$1"
  local step_name="$2"
  local cpus="$3"
  local walltime="$4"
  local dependency="$5"
  local target="$6"
  shift 6
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"

  sbatch --parsable \
    --job-name="${job_name}" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${cpus}" \
    --time="${walltime}" \
    --output="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.out" \
    --error="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.err\"; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name '${step_name}' -- '${PYTHON}' '${PIPELINE_DIR}/${target}' --config '${CONFIG}' ${extra_args[*]}"
}

submit_bash() {
  local job_name="$1"
  local step_name="$2"
  local cpus="$3"
  local walltime="$4"
  local dependency="$5"
  local target="$6"
  shift 6
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"

  sbatch --parsable \
    --job-name="${job_name}" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${cpus}" \
    --time="${walltime}" \
    --output="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.out" \
    --error="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export CONFIG='${CONFIG}' PYTHON='${PYTHON}' BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.err\"; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name '${step_name}' -- bash '${PIPELINE_DIR}/${target}' ${extra_args[*]}"
}

submit_external_python() {
  local job_name="$1"
  local step_name="$2"
  local cpus="$3"
  local walltime="$4"
  local dependency="$5"
  local external_python="$6"
  local target="$7"
  shift 7
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"

  sbatch --parsable \
    --job-name="${job_name}" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${cpus}" \
    --time="${walltime}" \
    --output="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.out" \
    --error="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.err\"; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name '${step_name}' -- '${external_python}' '${PIPELINE_DIR}/${target}' --config '${CONFIG}' ${extra_args[*]}"
}

submit_bacpipe_array() {
  local job_name="$1"
  local step_name="$2"
  local walltime="$3"
  local dependency="$4"
  local target="$5"
  local task_count="$6"
  local max_concurrent="$7"
  shift 7
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"
  local last_task=$((task_count - 1))

  sbatch --parsable \
    --job-name="${job_name}" \
    --partition="${BIOACOUSTICS_PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${BIOACOUSTICS_CPUS}" \
    "${bio_resource_args[@]}" \
    --mem="${BIOACOUSTICS_MEMORY}" \
    --time="${walltime}" \
    --array="0-${last_task}%${max_concurrent}" \
    --output="${LOGDIR}/${LOG_STAMP}_${job_name}_%A_%a.out" \
    --error="${LOGDIR}/${LOG_STAMP}_${job_name}_%A_%a.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.err\"; export OMP_NUM_THREADS='${BIOACOUSTICS_CPUS}'; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name '${step_name}' -- '${BACPIPE_PYTHON}' '${PIPELINE_DIR}/${target}' --config '${CONFIG}' --task-index \${SLURM_ARRAY_TASK_ID} ${extra_args[*]}"
}

submit_bacpipe_job() {
  local job_name="$1"
  local step_name="$2"
  local walltime="$3"
  local dependency="$4"
  local target="$5"
  shift 5
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"

  sbatch --parsable \
    --job-name="${job_name}" \
    --partition="${BIOACOUSTICS_PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${BIOACOUSTICS_CPUS}" \
    "${bio_resource_args[@]}" \
    --mem="${BIOACOUSTICS_MEMORY}" \
    --time="${walltime}" \
    --output="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.out" \
    --error="${LOGDIR}/${LOG_STAMP}_${job_name}_%j.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_${job_name}_\${SLURM_JOB_ID}.err\"; export OMP_NUM_THREADS='${BIOACOUSTICS_CPUS}'; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name '${step_name}' -- '${BACPIPE_PYTHON}' '${PIPELINE_DIR}/${target}' --config '${CONFIG}' ${extra_args[*]}"
}

submit_weather_array() {
  local walltime="$1"
  local dependency="$2"
  local task_count="$3"
  local ids_file="$4"
  shift 4
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"
  local last_task=$((task_count - 1))

  sbatch --parsable \
    --job-name="bio_step52" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${STEP52_CPUS}" \
    --time="${walltime}" \
    --array="0-${last_task}%${WEATHER_MAX_CONCURRENT}" \
    --output="${LOGDIR}/${LOG_STAMP}_bio_step52_%A_%a.out" \
    --error="${LOGDIR}/${LOG_STAMP}_bio_step52_%A_%a.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_bio_step52_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_bio_step52_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.err\"; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name 'step_5_2_weather_download_array_task' -- '${PYTHON}' '${PIPELINE_DIR}/scripts/Step_5_2_download_weather_data.py' --config '${CONFIG}' --ids-file '${ids_file}' --task-index \${SLURM_ARRAY_TASK_ID} --task-count '${task_count}' ${extra_args[*]}"
}

submit_hostrada_raster_array() {
  local walltime="$1"
  local dependency="$2"
  local task_count="$3"
  shift 3
  local extra_args=("$@")
  local dep_args=()
  [[ -n "${dependency}" ]] && dep_args=(--dependency="${dependency}")
  walltime="$(apply_override "${walltime}")"
  local last_task=$((task_count - 1))

  sbatch --parsable \
    --job-name="bio_step54" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task="${HOSTRADA_RASTER_CPUS}" \
    --mem="${HOSTRADA_RASTER_MEMORY}" \
    --time="${walltime}" \
    --array="0-${last_task}%${HOSTRADA_RASTER_MAX_CONCURRENT}" \
    --output="${LOGDIR}/${LOG_STAMP}_bio_step54_%A_%a.out" \
    --error="${LOGDIR}/${LOG_STAMP}_bio_step54_%A_%a.err" \
    "${account_args[@]}" \
    "${dep_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}' BIOOTON_RUN_PLAN='${RUN_PLAN:-}'; export BIOOTON_STDOUT_LOG=\"${LOGDIR}/${LOG_STAMP}_bio_step54_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.out\" BIOOTON_STDERR_LOG=\"${LOGDIR}/${LOG_STAMP}_bio_step54_\${SLURM_ARRAY_JOB_ID}_\${SLURM_ARRAY_TASK_ID}.err\"; export OMP_NUM_THREADS='${HOSTRADA_RASTER_CPUS}' OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1; '${PYTHON}' '${PIPELINE_DIR}/tools/run_with_manifest.py' --config '${CONFIG}' --step-name 'step_5_4_hostrada_raster_array_task' -- '${PYTHON}' '${PIPELINE_DIR}/tools/run_hostrada_raster_all.py' --config '${CONFIG}' --task-index \${SLURM_ARRAY_TASK_ID} ${extra_args[*]}"
}

afterany_jobs() {
  local ids=()
  local candidate
  for candidate in "$@"; do
    [[ "${candidate}" =~ ^[0-9]+$ ]] && ids+=("${candidate}")
  done
  if [[ "${#ids[@]}" -eq 0 ]]; then
    echo ""
    return
  fi
  local joined
  joined="$(IFS=:; echo "${ids[*]}")"
  echo "afterany:${joined}"
}

afterok_jobs() {
  local dependency
  dependency="$(afterany_jobs "$@")"
  echo "${dependency/afterany:/afterok:}"
}

if [[ "${MODE}" == "susi_compare" ]]; then
  MODE="formation_compare"
fi

RUN_PLAN=""
if [[ "${MODE}" == "functionality_test" ]]; then
  job="$(submit_python bio_func functionality_test 2 "00:10:00" "" tools/functionality_test.py)"
  echo "Functionality test job: ${job}"
  echo "Workflow run ID: ${RUN_ID}"
  echo "Monitor with: squeue -u ${USER}"
  exit 0
fi

if [[ "${MODE}" == "formation_compare" ]]; then
  job="$(submit_bash bio_form_cmp formation_compare "${FORMATION_COMPARE_CPUS}" "02:00:00" "" run_formation_status_comparison.sh)"
  echo "Formation comparison job: ${job}"
  echo "Workflow run ID: ${RUN_ID}"
  echo "Monitor with: squeue -u ${USER}"
  exit 0
fi

"${PYTHON}" -c "import pandas, geopandas, pyogrio, shapely, pyarrow, av; from PIL import Image; import rasterio, requests, xarray" || {
  echo "Missing Python dependencies in selected environment." >&2
  exit 1
}

"${PYTHON}" "${PIPELINE_DIR}/tools/pipeline_lock.py" \
  --config "${CONFIG}" acquire --run-id "${RUN_ID}"

SUBMISSION_STARTED=0
release_on_early_error() {
  if [[ "${SUBMISSION_STARTED}" -eq 0 ]]; then
    "${PYTHON}" "${PIPELINE_DIR}/tools/pipeline_lock.py" \
      --config "${CONFIG}" release --run-id "${RUN_ID}" || true
  else
    echo "Submission failed after jobs were queued. The pipeline lock remains active." >&2
    echo "Inspect queued jobs, then use the documented force-release command if needed." >&2
  fi
}
trap release_on_early_error ERR INT TERM

RUN_PLAN="$(
  "${PYTHON}" "${PIPELINE_DIR}/tools/plan_pipeline_run.py" \
    --config "${CONFIG}" \
    --run-id "${RUN_ID}" \
    --mode "${MODE}" |
    tail -n 1
)"
[[ -f "${RUN_PLAN}" ]] || { echo "Run plan was not created: ${RUN_PLAN}" >&2; exit 1; }
export BIOOTON_RUN_PLAN="${RUN_PLAN}"

plan_run() {
  "${PYTHON}" -c \
    'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); print("1" if p["steps"][sys.argv[2]]["run"] else "0")' \
    "${RUN_PLAN}" "$1"
}

plan_ids() {
  "${PYTHON}" -c \
    'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); print(p["id_files"][sys.argv[2]])' \
    "${RUN_PLAN}" "$1"
}

force_args=()
if [[ "${MODE}" == "from_scratch" ]]; then
  force_args=(--force)
  t_step1="00:30:00"
  t_step20="04:00:00"
  t_step21="06:00:00"
  t_step22="01:00:00"
  t_step23="01:00:00"
  t_step24="08:00:00"
  t_inv="02:00:00"
  t_media_download="08:00:00"
  t_step41="04:00:00"
  t_step40="02:00:00"
  t_step51="01:00:00"
  t_step52="12:00:00"
  t_step53="08:00:00"
  t_step54="24:00:00"
  t_step55="08:00:00"
  t_step60="02:00:00"
  t_step61="01:00:00"
  t_step62="12:00:00"
  t_step63="04:00:00"
  t_step64="04:00:00"
  t_step65="04:00:00"
  t_step66="02:00:00"
  t_master="01:00:00"
else
  t_step1="00:20:00"
  t_step20="01:00:00"
  t_step21="02:00:00"
  t_step22="00:30:00"
  t_step23="00:30:00"
  t_step24="04:00:00"
  t_inv="00:30:00"
  t_media_download="04:00:00"
  t_step41="02:00:00"
  t_step40="01:00:00"
  t_step51="00:30:00"
  t_step52="08:00:00"
  t_step53="04:00:00"
  t_step54="12:00:00"
  t_step55="04:00:00"
  t_step60="02:00:00"
  t_step61="00:30:00"
  t_step62="04:00:00"
  t_step63="01:00:00"
  t_step64="01:00:00"
  t_step65="01:00:00"
  t_step66="00:30:00"
  t_master="00:30:00"
fi

SUBMISSION_STARTED=1
metadata_ids="$(plan_ids metadata)"
point_ids="$(plan_ids point_assignment)"
audio_ids="$(plan_ids audio)"
photo_ids="$(plan_ids photo)"
weather_ids="$(plan_ids weather)"
bioacoustic_ids="$(plan_ids bioacoustic)"
sentinel_ids="$(plan_ids sentinel)"

# Master-table updates are serialized so concurrent Slurm jobs cannot overwrite
# each other's partial results. Each update writes only the IDs relevant to its
# completed upstream step; global grid/raster changes intentionally refresh all.
jmaster_chain=""
submit_master_update() {
  local stage="$1"
  local upstream_job="$2"
  local ids_file="${3:-}"
  local master_args=()
  [[ -n "${ids_file}" ]] && master_args=(--ids-file "${ids_file}")
  jmaster_chain="$(submit_python "bio_master_${stage}" "step_7_0_master_${stage}" "${MASTER_CPUS}" "${t_master}" "$(afterany_jobs "${upstream_job}" "${jmaster_chain}")" scripts/Step_7_0_update_master_table.py "${master_args[@]}")"
}

j1="skipped_plan"
if [[ "$(plan_run step_1_metadata)" == "1" ]]; then
  j1="$(submit_python bio_step1 step_1_metadata 1 "${t_step1}" "" scripts/Step_1_metadata_extraction.py "${force_args[@]}" --ids-file "${metadata_ids}")"
  submit_master_update metadata "${j1}" "${metadata_ids}"
fi

j20="skipped_plan"
if [[ "$(plan_run step_2_0_lrt_cleaning)" == "1" ]]; then
  j20="$(submit_python bio_step20 step_2_0_lrt_cleaning "${STEP2_CPUS}" "${t_step20}" "" scripts/Step_2_0_clean_lrts.py "${force_args[@]}")"
fi

j21="skipped_plan"
if [[ "$(plan_run step_2_1_100m_formation)" == "1" ]]; then
  j21="$(submit_python bio_step21 step_2_1_100m_formation "${STEP2_CPUS}" "${t_step21}" "$(afterany_jobs "${j20}")" scripts/Step_2_1_merge_lrts_and_grid.py "${force_args[@]}")"
fi

j22="skipped_plan"
if [[ "$(plan_run step_2_2_point_assignment)" == "1" ]]; then
  j22="$(submit_python bio_step22 step_2_2_point_assignment 1 "${t_step22}" "$(afterany_jobs "${j1}" "${j21}")" scripts/Step_2_2_assign_points_to_lrt_grid.py "${force_args[@]}" --ids-file "${point_ids}")"
  submit_master_update point_assignment "${j22}" "${point_ids}"
fi

j23="skipped_plan"
if [[ "$(plan_run step_2_3_grid_aggregation)" == "1" ]]; then
  j23="$(submit_python bio_step23 step_2_3_grid_aggregation 3 "${t_step23}" "$(afterany_jobs "${j21}")" scripts/Step_2_3_generate_remaining_grid_products.py "${force_args[@]}")"
fi

j24="skipped_plan"
if [[ "$(plan_run step_2_4_10m_formation)" == "1" ]]; then
  j24="$(submit_python bio_step24 step_2_4_10m_formation "${STEP24_CPUS}" "${t_step24}" "$(afterany_jobs "${j21}")" scripts/Step_2_4_generate_10m_formation_status_products.py "${force_args[@]}")"
  submit_master_update formation_products "${j24}"
fi

# Step 3 only reads configured media paths and the raw Dawn-Chorus table;
# it does not require Step 1's derived metadata outputs.
j3pre="$(submit_python bio_step3pre step_3_path_preflight 1 "00:10:00" "" tools/step3_path_preflight.py)"
j30a="skipped_plan"
if [[ "$(plan_run step_3_0_audio_inventory)" == "1" ]]; then
  j30a="$(submit_python bio_step30a step_3_0_audio_inventory "${STEP3_INVENTORY_CPUS}" "${t_inv}" "$(afterany_jobs "${j3pre}")" scripts/Step_3_0_a_audio_inventory.py "${force_args[@]}")"
fi
j30b="skipped_plan"
if [[ "$(plan_run step_3_0_photo_inventory)" == "1" ]]; then
  j30b="$(submit_python bio_step30b step_3_0_photo_inventory "${STEP3_INVENTORY_CPUS}" "${t_inv}" "$(afterany_jobs "${j3pre}")" scripts/Step_3_0_b_photo_inventory.py "${force_args[@]}")"
fi
j31a="skipped_plan"
if [[ "$(plan_run step_3_1_audio_download)" == "1" ]]; then
  j31a="$(submit_python bio_step31a step_3_1_audio_download "${STEP3_DOWNLOAD_CPUS}" "${t_media_download}" "$(afterany_jobs "${j30a}")" scripts/Step_3_1_a_audio_download.py "${force_args[@]}" --ids-file "${audio_ids}")"
fi
j30apost="skipped_plan"
if [[ "$(plan_run step_3_0_audio_inventory_post)" == "1" ]]; then
  j30apost="$(submit_python bio_step30apost step_3_0_audio_inventory_post "${STEP3_INVENTORY_CPUS}" "${t_inv}" "$(afterany_jobs "${j31a}")" scripts/Step_3_0_a_audio_inventory.py)"
  submit_master_update audio "${j30apost}" "${audio_ids}"
fi
j31b="skipped_plan"
if [[ "$(plan_run step_3_1_photo_download)" == "1" ]]; then
  j31b="$(submit_python bio_step31b step_3_1_photo_download "${STEP3_DOWNLOAD_CPUS}" "${t_media_download}" "$(afterany_jobs "${j30b}")" scripts/Step_3_1_b_photo_download.py "${force_args[@]}" --ids-file "${photo_ids}")"
  submit_master_update photo "${j31b}" "${photo_ids}"
fi

j41="skipped_plan"
if [[ "$(plan_run step_4_1_sentinel2_mirror)" == "1" ]]; then
  j41="$(submit_python bio_step41 step_4_1_sentinel2_mirror "${STEP41_CPUS}" "${t_step41}" "$(afterany_jobs "${j1}")" scripts/Step_4_1_Sentinel2_download.py "${force_args[@]}")"
fi
j40="skipped_plan"
if [[ "$(plan_run step_4_0_sentinel2_inventory)" == "1" ]]; then
  j40="$(submit_python bio_step40 step_4_0_sentinel2_inventory "${STEP40_CPUS}" "${t_step40}" "$(afterany_jobs "${j41}")" scripts/Step_4_0_Sentinel2_inventory.py "${force_args[@]}")"
  submit_master_update sentinel "${j40}" "${sentinel_ids}"
fi

j51pre="skipped_plan"
if [[ "$(plan_run step_5_1_weather_inventory)" == "1" ]]; then
  j51pre="$(submit_python bio_step51pre step_5_1_weather_inventory "${STEP51_CPUS}" "${t_step51}" "$(afterany_jobs "${j1}")" scripts/Step_5_1_Weather_inventory.py "${force_args[@]}")"
fi
j52="skipped_plan"
j52verify="skipped_plan"
if [[ "$(plan_run step_5_2_weather_download)" == "1" ]]; then
  weather_id_count="$(
    "${PYTHON}" -c \
      'import sys; sys.path.insert(0, sys.argv[1]); from common import read_ids_file; print(len(read_ids_file(sys.argv[2])))' \
      "${PIPELINE_DIR}/scripts" "${weather_ids}"
  )"
  weather_task_count=$(( (weather_id_count + 4999) / 5000 ))
  (( weather_task_count < 1 )) && weather_task_count=1
  (( weather_task_count > WEATHER_SHARD_LIMIT )) && weather_task_count="${WEATHER_SHARD_LIMIT}"
  j52="$(submit_weather_array "${t_step52}" "$(afterany_jobs "${j51pre}")" "${weather_task_count}" "${weather_ids}" "${force_args[@]}")"
  j52verify="$(submit_python bio_step52verify step_5_2_weather_download 1 "00:15:00" "$(afterany_jobs "${j52}")" scripts/Step_5_2_download_weather_data.py --verify-shards --ids-file "${weather_ids}")"
fi
j51post="skipped_plan"
if [[ "${j52}" =~ ^[0-9]+$ ]]; then
  j51post="$(submit_python bio_step51post step_5_1_weather_inventory_post "${STEP51_CPUS}" "${t_step51}" "$(afterany_jobs "${j52verify}")" scripts/Step_5_1_Weather_inventory.py)"
  submit_master_update weather "${j51post}" "${weather_ids}"
fi

j53="skipped_plan"
if [[ "$(plan_run step_5_3_hostrada_monthly)" == "1" ]]; then
  j53="$(submit_python bio_step53 step_5_3_hostrada_monthly "${STEP52_CPUS}" "${t_step53}" "" scripts/Step_5_3_download_hostrada_monthly.py)"
fi
j54="skipped_plan"
j54verify="skipped_plan"
if [[ "$(plan_run step_5_4_hostrada_rasters)" == "1" ]]; then
  hostrada_task_count="$("${PYTHON}" "${PIPELINE_DIR}/tools/run_hostrada_raster_all.py" --config "${CONFIG}" --task-count)"
  [[ "${hostrada_task_count}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid HOSTRADA array task count: ${hostrada_task_count}" >&2; exit 1; }
  j54="$(submit_hostrada_raster_array "${t_step54}" "$(afterany_jobs "${j53}")" "${hostrada_task_count}" "${force_args[@]}")"
  # The verification task writes the single Step 5.4 completion marker only
  # after every array element has stopped. Step 5.5 intentionally uses
  # afterany so it can report partial products after a timeout or failure.
  j54verify="$(submit_python bio_step54verify step_5_4_hostrada_rasters 1 "00:15:00" "$(afterany_jobs "${j54}")" tools/run_hostrada_raster_all.py --verify-array)"
fi
j55="skipped_plan"
if [[ "$(plan_run step_5_5_hostrada_raster_qc)" == "1" ]]; then
  j55="$(submit_python bio_step55 step_5_5_hostrada_raster_qc "${STEP51_CPUS}" "${t_step55}" "$(afterany_jobs "${j54verify}")" scripts/Step_5_5_check_hostrada_raster_products.py)"
  submit_master_update hostrada_raster "${j55}"
fi

j60="skipped_plan"
if [[ "$(plan_run step_6_0_bioacoustic_model_preflight)" == "1" ]]; then
  preflight_model_args=()
  instantiate_models="$("${PYTHON}" -c "import json; c=json.load(open('${CONFIG}', encoding='utf-8')); print('1' if c['bioacoustics'].get('instantiate_models_in_preflight', True) else '0')")"
  [[ "${instantiate_models}" == "1" ]] && preflight_model_args=(--instantiate-models)
  j60="$(submit_bacpipe_job bio_step60 step_6_0_bioacoustic_model_preflight "${t_step60}" "" scripts/Step_6_0_bioacoustic_model_preflight.py "${preflight_model_args[@]}")"
fi

j61="skipped_plan"
if [[ "$(plan_run step_6_1_bioacoustic_worklist)" == "1" ]]; then
  j61="$(submit_python bio_step61 step_6_1_bioacoustic_worklist 2 "${t_step61}" "$(afterok_jobs "${j30apost}" "${j1}" "${j60}")" scripts/Step_6_1_prepare_bioacoustic_worklist.py "${force_args[@]}" --ids-file "${bioacoustic_ids}")"
fi

bio_model_count="$("${PYTHON}" -c "import json; c=json.load(open('${CONFIG}', encoding='utf-8')); print(len(c['bioacoustics']['models']))")"
bio_shard_count="$("${PYTHON}" -c "import json; c=json.load(open('${CONFIG}', encoding='utf-8')); print(int(c['bioacoustics'].get('shard_count', 16)))")"
bio_max_concurrent="$("${PYTHON}" -c "import json; c=json.load(open('${CONFIG}', encoding='utf-8')); print(int(c['bioacoustics'].get('max_concurrent_tasks', c['bioacoustics'].get('max_concurrent_gpu_tasks', 4))))")"
bio_task_count=$((bio_model_count * bio_shard_count))

j62="skipped_plan"
if [[ "$(plan_run step_6_2_bioacoustic_embeddings)" == "1" ]]; then
  # Step 6_1 already requires the model preflight, so j60 is transitive here.
  j62="$(submit_bacpipe_array bio_step62 step_6_2_bioacoustic_embeddings "${t_step62}" "$(afterok_jobs "${j61}")" scripts/Step_6_2_generate_bioacoustic_embeddings.py "${bio_task_count}" "${bio_max_concurrent}" "${force_args[@]}")"
fi

j63="skipped_plan"
if [[ "$(plan_run step_6_3_species_predictions)" == "1" ]]; then
  j63="$(submit_python bio_step63 step_6_3_species_predictions 8 "${t_step63}" "$(afterany_jobs "${j62}")" scripts/Step_6_3_normalise_species_predictions.py)"
fi
j64="skipped_plan"
if [[ "$(plan_run step_6_4_germany_taxonomy_filter)" == "1" ]]; then
  # j63 is downstream of j62 -> j61 -> j1, therefore j1 is transitive.
  j64="$(submit_python bio_step64 step_6_4_germany_taxonomy_filter 8 "${t_step64}" "$(afterok_jobs "${j63}")" scripts/Step_6_4_filter_germany_taxonomy.py)"
fi
j65="skipped_plan"
if [[ "$(plan_run step_6_5_bioacoustic_aggregation)" == "1" ]]; then
  j65="$(submit_python bio_step65 step_6_5_bioacoustic_aggregation 8 "${t_step65}" "$(afterok_jobs "${j64}")" scripts/Step_6_5_aggregate_bioacoustic_results.py)"
fi
j66="skipped_plan"
if [[ "$(plan_run step_6_6_bioacoustic_qc)" == "1" ]]; then
  # j65 already transitively waits for j62. Keeping only j65 avoids a
  # redundant dependency without allowing QC before aggregation.
  j66="$(submit_python bio_step66 step_6_6_bioacoustic_qc 4 "${t_step66}" "$(afterany_jobs "${j65}")" scripts/Step_6_6_bioacoustic_quality_control.py)"
  submit_master_update bioacoustics "${j66}" "${bioacoustic_ids}"
fi

if [[ -z "${jmaster_chain}" ]]; then
  submit_master_update initial ""
fi
jmaster="${jmaster_chain}"
jvalid="$(submit_python bio_validate final_validation 1 "00:15:00" "$(afterany_jobs "${jmaster}")" tools/final_validation_report.py)"
jvisual="$(submit_python bio_visual step_9_visual_reports 1 "00:10:00" "$(afterany_jobs "${jvalid}")" tools/generate_pipeline_visual_reports.py)"

junlock="$(
  sbatch --parsable \
    --job-name="bio_unlock" \
    --partition="${PARTITION}" \
    --constraint=LSDF \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task=1 \
    --time="00:05:00" \
    --output="${LOGDIR}/${LOG_STAMP}_bio_unlock_%j.out" \
    --error="${LOGDIR}/${LOG_STAMP}_bio_unlock_%j.err" \
    "${account_args[@]}" \
    --dependency="$(afterany_jobs "${jvisual}")" \
    --wrap="set -euo pipefail; '${PYTHON}' '${PIPELINE_DIR}/tools/pipeline_lock.py' --config '${CONFIG}' release --run-id '${RUN_ID}'"
)"

trap - ERR INT TERM

printf 'Mode:          %s\nWorkflow run:  %s\nRun plan:      %s\nStep 1:        %s\nStep 2_0:      %s\nStep 2_1:      %s\nStep 2_2:      %s\nStep 2_3:      %s\nStep 2_4:      %s\nStep 3 pre:    %s\nStep 3_0a:     %s\nStep 3_0b:     %s\nStep 3_1a:     %s\nStep 3_0a post:%s\nStep 3_1b:     %s\nStep 4_1:      %s\nStep 4_0:      %s\nStep 5_1 pre:  %s\nStep 5_2 array:%s\nStep 5_2 verify:%s\nStep 5_1 post: %s\nStep 5_3:      %s\nStep 5_4 array:%s\nStep 5_4 verify:%s\nStep 5_5:      %s\nStep 6_0:      %s\nStep 6_1:      %s\nStep 6_2 array:%s\nStep 6_3:      %s\nStep 6_4:      %s\nStep 6_5:      %s\nStep 6_6:      %s\nMaster 7_0:    %s\nValidation:    %s\nVisual reports:%s\nUnlock:        %s\n' \
  "${MODE}" "${RUN_ID}" "${RUN_PLAN}" "${j1}" "${j20}" "${j21}" "${j22}" "${j23}" "${j24}" "${j3pre}" "${j30a}" "${j30b}" "${j31a}" "${j30apost}" "${j31b}" "${j41}" "${j40}" "${j51pre}" "${j52}" "${j52verify}" "${j51post}" "${j53}" "${j54}" "${j54verify}" "${j55}" "${j60}" "${j61}" "${j62}" "${j63}" "${j64}" "${j65}" "${j66}" "${jmaster}" "${jvalid}" "${jvisual}" "${junlock}"

echo "Submitted Bio-O-Ton Slurm workflow."
echo "Monitor with: squeue -u ${USER}"

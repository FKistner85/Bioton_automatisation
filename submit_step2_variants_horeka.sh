#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-add_new_ids}"
[[ "${MODE}" == "add_new_ids" || "${MODE}" == "from_scratch" ]] || {
  echo "Usage: bash submit_step2_variants_horeka.sh [add_new_ids|from_scratch]" >&2
  exit 2
}

PIPELINE_DIR="${BIOOTON_PIPELINE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
CONFIG="${BIOOTON_CONFIG:-${PIPELINE_DIR}/config.horeka.json}"
PYTHON="${BIOOTON_PYTHON:-${PIPELINE_DIR}/.venv/bin/python}"
PARTITION="${BIOOTON_PARTITION:-cpuonly}"
ACCOUNT="${BIOOTON_ACCOUNT:-}"
LOGDIR="${BIOOTON_LOGDIR:-}"
MAX_CONCURRENT="${BIOOTON_STEP2_VARIANT_CONCURRENCY:-}"
VARIANT_CPUS="${BIOOTON_STEP2_VARIANT_CPUS:-16}"
VARIANT_MEMORY="${BIOOTON_STEP2_VARIANT_MEMORY:-64G}"
VARIANT_TIME="${BIOOTON_STEP2_VARIANT_TIME:-${BIOOTON_STEP2_VARIANT_TIME_OVERRIDE:-24:00:00}}"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(bash "${PIPELINE_DIR}/bootstrap_env.sh" | tail -n 1)"
fi
[[ -x "${PYTHON}" ]] || { echo "Missing Python: ${PYTHON}" >&2; exit 1; }
[[ -f "${CONFIG}" ]] || { echo "Missing config: ${CONFIG}" >&2; exit 1; }

if [[ -z "${LOGDIR}" ]]; then
  LOGDIR="$(${PYTHON} -c "import json; print(json.load(open('${CONFIG}', encoding='utf-8'))['slurm_log_dir'])")"
fi
if [[ -z "${MAX_CONCURRENT}" ]]; then
  MAX_CONCURRENT="$(${PYTHON} -c "import json; print(json.load(open('${CONFIG}', encoding='utf-8'))['lrt_variants'].get('slurm_max_concurrent_variants', 4))")"
fi
mkdir -p "${LOGDIR}"

"${PYTHON}" "${PIPELINE_DIR}/tools/step2_variants.py" \
  --config "${CONFIG}" --python "${PYTHON}" --prepare-only
TASK_COUNT="$(${PYTHON} "${PIPELINE_DIR}/tools/step2_variants.py" \
  --config "${CONFIG}" --python "${PYTHON}" --task-count | tail -n 1)"
[[ "${TASK_COUNT}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid variant count: ${TASK_COUNT}" >&2; exit 1; }
LAST_TASK=$((TASK_COUNT - 1))
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="${STAMP}_step2_variants_${USER}_$$"
account_args=()
[[ -n "${ACCOUNT}" ]] && account_args=(--account="${ACCOUNT}")
force_args=()
[[ "${MODE}" == "from_scratch" ]] && force_args=(--force)

"${PYTHON}" "${PIPELINE_DIR}/tools/pipeline_lock.py" \
  --config "${CONFIG}" acquire --run-id "${RUN_ID}" --owner-pid "$$"

submit_variant_array() {
  sbatch --parsable \
    --job-name="bio_v2all" --partition="${PARTITION}" --constraint=LSDF \
    --nodes=1 --ntasks=1 --cpus-per-task="${VARIANT_CPUS}" \
    --mem="${VARIANT_MEMORY}" --time="${VARIANT_TIME}" \
    --array="0-${LAST_TASK}%${MAX_CONCURRENT}" \
    --output="${LOGDIR}/${STAMP}_bio_v2all_%A_%a.out" \
    --error="${LOGDIR}/${STAMP}_bio_v2all_%A_%a.err" \
    "${account_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}'; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1; '${PYTHON}' tools/step2_variants.py --config '${CONFIG}' --python '${PYTHON}' --all-stages --task-index \${SLURM_ARRAY_TASK_ID} ${force_args[*]}"
}

submit_job() {
  local name="$1" cpus="$2" requested_time="$3" dependency="$4" target="$5"
  local include_force="${6:-1}"
  local job_force=""
  [[ "${include_force}" == "1" ]] && job_force="${force_args[*]}"
  local dependency_args=()
  [[ -n "${dependency}" ]] && dependency_args=(--dependency="${dependency}")
  sbatch --parsable \
    --job-name="${name}" --partition="${PARTITION}" --constraint=LSDF \
    --nodes=1 --ntasks=1 --cpus-per-task="${cpus}" --time="${requested_time}" \
    --output="${LOGDIR}/${STAMP}_${name}_%j.out" \
    --error="${LOGDIR}/${STAMP}_${name}_%j.err" \
    "${account_args[@]}" "${dependency_args[@]}" \
    --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; export BIOOTON_RUN_ID='${RUN_ID}'; '${PYTHON}' '${target}' --config '${CONFIG}' ${job_force}"
}

j2all="$(submit_variant_array)"
j71="$(submit_job bio_vmaster 4 02:00:00 "afterany:${j2all}" "${PIPELINE_DIR}/scripts/Step_7_1_update_formation_variant_table.py")"
j70="$(submit_job bio_master 2 01:00:00 "afterany:${j71}" "${PIPELINE_DIR}/scripts/Step_7_0_update_master_table.py" 0)"
junlock="$(sbatch --parsable \
  --job-name=bio_vunlock --partition="${PARTITION}" --constraint=LSDF \
  --nodes=1 --ntasks=1 --cpus-per-task=1 --time=00:05:00 \
  --dependency="afterany:${j70}" \
  --output="${LOGDIR}/${STAMP}_bio_vunlock_%j.out" \
  --error="${LOGDIR}/${STAMP}_bio_vunlock_%j.err" \
  "${account_args[@]}" \
  --wrap="set -euo pipefail; cd '${PIPELINE_DIR}'; '${PYTHON}' tools/pipeline_lock.py --config '${CONFIG}' release --run-id '${RUN_ID}'")"

cat <<EOF
Submitted ${TASK_COUNT} isolated Step-2 variants (${MODE}).
Step 2 all array: ${j2all}
Resources       : ${VARIANT_CPUS} CPUs, ${VARIANT_MEMORY}, ${VARIANT_TIME}, max ${MAX_CONCURRENT} parallel
Variant master : ${j71}
Main master    : ${j70}
Unlock         : ${junlock}

Monitor: squeue -u "${USER}"
EOF

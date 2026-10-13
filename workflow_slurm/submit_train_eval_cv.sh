#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=sherlock_config.sh
source "${SCRIPT_DIR}/sherlock_config.sh"
setup_transcriptml_env
# shellcheck source=../workflow/common.sh
source "${AUTORESEARCH_ROOT}/workflow/common.sh"

if [[ "${1:-}" != "--experiment-id" || -z "${2:-}" || $# -ne 2 ]]; then
  echo "usage: $0 --experiment-id ID" >&2
  exit 2
fi
EXPERIMENT_ID="$2"
require_experiment_id "${EXPERIMENT_ID}"
validate_campaign
command -v sbatch >/dev/null 2>&1 || { echo "sbatch is not available" >&2; exit 2; }

"${PYTHON_BIN}" -m autoresearch_harness prepare-experiment \
  --root "${AUTORESEARCH_ROOT}" \
  --experiment-id "${EXPERIMENT_ID}" \
  --base-config "${BASE_TRAIN_CONFIG}" \
  --runs-root "${RUNS_ROOT}" \
  --dataset "${DATASET_DIR}" >/dev/null

EXPERIMENT_DIR="${RUNS_ROOT}/${EXPERIMENT_ID}"
BASE_TRAIN_CONFIG="${EXPERIMENT_DIR}/config/train_config.json"
LOG_DIR="${EXPERIMENT_DIR}/slurm"
mkdir -p "${LOG_DIR}"

EXPORTS="ALL,AUTORESEARCH_ROOT=${AUTORESEARCH_ROOT},AUTORESEARCH_EXPERIMENT_ID=${EXPERIMENT_ID},RUNS_ROOT=${RUNS_ROOT},DATASET_DIR=${DATASET_DIR},BASE_TRAIN_CONFIG=${BASE_TRAIN_CONFIG},MOTIF_SPECS_FILE=${MOTIF_SPECS_FILE},CONDA_ENV=${CONDA_ENV},SHERLOCK_CONDA_ROOT=${SHERLOCK_CONDA_ROOT}"
ARRAY_JOB_RAW="$(sbatch \
  --parsable \
  --array="0-$((N_FOLDS - 1))" \
  --chdir="${AUTORESEARCH_ROOT}" \
  --output="${LOG_DIR}/fold_%A_%a.out" \
  --error="${LOG_DIR}/fold_%A_%a.err" \
  --export="${EXPORTS}" \
  "${SCRIPT_DIR}/train_eval_cv_fold.sh")"
ARRAY_JOB_ID="${ARRAY_JOB_RAW%%;*}"
[[ "${ARRAY_JOB_ID}" =~ ^[0-9]+$ ]] || { echo "Could not parse array job id: ${ARRAY_JOB_RAW}" >&2; exit 1; }

AGGREGATE_JOB_RAW="$(sbatch \
  --parsable \
  --dependency="afterany:${ARRAY_JOB_ID}" \
  --chdir="${AUTORESEARCH_ROOT}" \
  --output="${LOG_DIR}/aggregate_%j.out" \
  --error="${LOG_DIR}/aggregate_%j.err" \
  --export="${EXPORTS}" \
  "${SCRIPT_DIR}/aggregate_experiment.sh")"
AGGREGATE_JOB_ID="${AGGREGATE_JOB_RAW%%;*}"
[[ "${AGGREGATE_JOB_ID}" =~ ^[0-9]+$ ]] || { echo "Could not parse aggregate job id: ${AGGREGATE_JOB_RAW}" >&2; exit 1; }

"${PYTHON_BIN}" -m autoresearch_harness write-submission \
  --experiment-dir "${EXPERIMENT_DIR}" \
  --array-job-id "${ARRAY_JOB_ID}" \
  --aggregate-job-id "${AGGREGATE_JOB_ID}" >/dev/null

printf '{"experiment_id":"%s","array_job_id":"%s","aggregate_job_id":"%s"}\n' \
  "${EXPERIMENT_ID}" "${ARRAY_JOB_ID}" "${AGGREGATE_JOB_ID}"

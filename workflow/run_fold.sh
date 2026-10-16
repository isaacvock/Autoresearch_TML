#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

EXPERIMENT_ID=""
FOLD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    --fold) FOLD="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

require_experiment_id "${EXPERIMENT_ID}"
validate_campaign
if [[ ! "${FOLD}" =~ ^[0-9]+$ ]] || (( FOLD < 0 || FOLD >= N_FOLDS )); then
  echo "fold must be an integer in [0, $((N_FOLDS - 1))]" >&2
  exit 2
fi

EXPERIMENT_DIR="${RUNS_ROOT}/${EXPERIMENT_ID}"
"${PYTHON_BIN}" -m autoresearch_harness prepare-experiment \
  --root "${AUTORESEARCH_ROOT}" \
  --experiment-id "${EXPERIMENT_ID}" \
  --base-config "${BASE_TRAIN_CONFIG}" \
  --runs-root "${RUNS_ROOT}" \
  --dataset "${DATASET_DIR}" \
  --motifs "${MOTIF_SPECS_FILE}"

MOTIF_SPECS_FILE="${EXPERIMENT_DIR}/config/motifs.tsv"

if "${PYTHON_BIN}" -m autoresearch_harness validate-fold \
    --experiment-dir "${EXPERIMENT_DIR}" \
    --fold "${FOLD}" \
    --motifs "${MOTIF_SPECS_FILE}" >/dev/null 2>&1; then
  echo "fold${FOLD} is already complete for ${EXPERIMENT_ID}; skipping"
  exit 0
fi

# A previous process may have finished training, evaluation, and ablation but
# stopped before it could promote the attempt (for example, because an older
# harness rejected TranscriptML's fold-derived seed). Validate existing
# attempts newest-first so expensive completed work is reused when possible.
ATTEMPTS_ROOT="${EXPERIMENT_DIR}/attempts/fold${FOLD}"
if [[ -d "${ATTEMPTS_ROOT}" ]]; then
  while IFS= read -r prior_attempt; do
    if "${PYTHON_BIN}" -m autoresearch_harness complete-fold \
        --experiment-dir "${EXPERIMENT_DIR}" \
        --attempt-dir "${prior_attempt}" \
        --fold "${FOLD}" \
        --motifs "${MOTIF_SPECS_FILE}" \
        --eval-split "${EVAL_SPLIT}" >/dev/null 2>&1; then
      echo "recovered completed fold${FOLD} attempt for ${EXPERIMENT_ID}; skipping retraining"
      exit 0
    fi
  done < <(find "${ATTEMPTS_ROOT}" -mindepth 1 -maxdepth 1 -type d -print | sort -r)
fi

ATTEMPT_ID="${AUTORESEARCH_ATTEMPT_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-$$}}"
ATTEMPT_DIR="${EXPERIMENT_DIR}/attempts/fold${FOLD}/${ATTEMPT_ID}"
CV_ROOT="${ATTEMPT_DIR}/cv"
INTERPRET_ROOT="${ATTEMPT_DIR}/interpret"
CONFIG_SNAPSHOT="${EXPERIMENT_DIR}/config/train_config.json"
mkdir -p "${ATTEMPT_DIR}"

record_failure() {
  local status=$?
  "${PYTHON_BIN}" -m autoresearch_harness fail-fold \
    --experiment-dir "${EXPERIMENT_DIR}" \
    --attempt-dir "${ATTEMPT_DIR}" \
    --fold "${FOLD}" \
    --exit-code "${status}" || true
  exit "${status}"
}
trap record_failure ERR INT TERM

MODEL_NAME="$("${PYTHON_BIN}" -m autoresearch_harness config-model "${CONFIG_SNAPSHOT}")"
CONFIG_PATH="$(
  run_transcriptml cv prepare-fold \
    --dataset "${DATASET_DIR}" \
    --base-config "${CONFIG_SNAPSHOT}" \
    --cv-root "${CV_ROOT}" \
    --fold "${FOLD}" \
    --model "${MODEL_NAME}" \
    --n-folds "${N_FOLDS}" \
    --seed "${CV_SEED}" \
    --val-offset "${CV_VAL_OFFSET}"
)"

run_transcriptml train "${CONFIG_PATH}"

FOLD_DIR="${CV_ROOT}/fold${FOLD}"
CHECKPOINT="${FOLD_DIR}/model/best.pt"
mkdir -p "${FOLD_DIR}/eval"
run_transcriptml evaluate \
  --checkpoint "${CHECKPOINT}" \
  --dataset "${FOLD_DIR}/dataset" \
  --out-csv "${FOLD_DIR}/eval/${EVAL_SPLIT}_predictions.csv" \
  --split "${EVAL_SPLIT}" \
  --batch-size "${PRED_BATCH_SIZE}" \
  --device "${DEVICE}"

while IFS=$'\t' read -r label motif; do
  [[ -z "${label}" || "${label}" == \#* ]] && continue
  run_transcriptml motif-ablation \
    --checkpoint "${CHECKPOINT}" \
    --dataset "${DATASET_DIR}" \
    --out-dir "${INTERPRET_ROOT}/motif_ablation/${label}" \
    --motif "${motif}" \
    --n-scrambles "${N_SCRAMBLES}" \
    --strategy "${MOTIF_STRATEGY}" \
    --seed "${MOTIF_SEED}" \
    --region "${MOTIF_REGION}" \
    --device "${DEVICE}" \
    --batch-size "${PRED_BATCH_SIZE}"
done < "${MOTIF_SPECS_FILE}"

trap - ERR INT TERM
"${PYTHON_BIN}" -m autoresearch_harness complete-fold \
  --experiment-dir "${EXPERIMENT_DIR}" \
  --attempt-dir "${ATTEMPT_DIR}" \
  --fold "${FOLD}" \
  --motifs "${MOTIF_SPECS_FILE}" \
  --eval-split "${EVAL_SPLIT}"
echo "completed ${EXPERIMENT_ID} fold${FOLD}"

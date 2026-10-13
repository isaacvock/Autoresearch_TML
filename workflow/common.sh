#!/bin/bash

set -euo pipefail

WORKFLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="${AUTORESEARCH_ROOT:-$(cd "${WORKFLOW_DIR}/.." && pwd)}"

source "${WORKFLOW_DIR}/campaign.env"

# User paths are loaded by the WSL or Sherlock wrapper from config.sh.
: "${DATASET_DIR:?Launch through a WSL or Sherlock wrapper so config.sh is loaded}"
BASE_TRAIN_CONFIG="${BASE_TRAIN_CONFIG:-${WORKFLOW_DIR}/example_train_config.json}"
: "${RUNS_ROOT:?Launch through a WSL or Sherlock wrapper so config.sh is loaded}"
MOTIF_SPECS_FILE="${MOTIF_SPECS_FILE:-${WORKFLOW_DIR}/motifs.tsv}"
PYTHON_BIN="${PYTHON_BIN:-python}"
TRANSCRIPTML_BIN="${TRANSCRIPTML_BIN:-transcriptml}"

export PYTHONPATH="${AUTORESEARCH_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

require_experiment_id() {
  local experiment_id="${1:-}"
  if [[ -z "${experiment_id}" || ! "${experiment_id}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "experiment id must match [A-Za-z0-9][A-Za-z0-9._-]*" >&2
    return 2
  fi
}

validate_campaign() {
  if [[ "${N_FOLDS}" -ne 5 ]]; then
    echo "This campaign requires exactly five folds; got N_FOLDS=${N_FOLDS}" >&2
    return 2
  fi
  [[ "${CV_SEED}" == "10141996" && "${CV_VAL_OFFSET}" == "1" ]] || {
    echo "CV seed and validation offset differ from the immutable campaign" >&2
    return 2
  }
  [[ "${TRAIN_SEED}" == "42" && "${MOTIF_SEED}" == "42" ]] || {
    echo "Training and motif seeds differ from the immutable campaign" >&2
    return 2
  }
  [[ "${PEARSON_TOLERANCE}" == "0.0001" && "${MOTIF_TOLERANCE}" == "0.000001" ]] || {
    echo "Pareto tolerances differ from the immutable campaign" >&2
    return 2
  }
  [[ -d "${DATASET_DIR}" ]] || {
    echo "Dataset directory not found: ${DATASET_DIR}. Edit the matching path in config.sh." >&2
    return 2
  }
  [[ -f "${BASE_TRAIN_CONFIG}" ]] || { echo "Base train config not found: ${BASE_TRAIN_CONFIG}" >&2; return 2; }
  [[ -f "${MOTIF_SPECS_FILE}" ]] || { echo "Motif specification not found: ${MOTIF_SPECS_FILE}" >&2; return 2; }
  [[ "${EVAL_SPLIT}" == "test" ]] || { echo "EVAL_SPLIT is immutable and must be test" >&2; return 2; }
  command -v "${TRANSCRIPTML_BIN}" >/dev/null 2>&1 || {
    echo "TranscriptML executable not found: ${TRANSCRIPTML_BIN}" >&2
    return 2
  }
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "Python not found: ${PYTHON_BIN}" >&2; return 2; }
  "${PYTHON_BIN}" -c \
    'from autoresearch_harness.folds import read_motifs; import sys; read_motifs(sys.argv[1])' \
    "${MOTIF_SPECS_FILE}"
}

run_transcriptml() {
  "${TRANSCRIPTML_BIN}" "$@"
}

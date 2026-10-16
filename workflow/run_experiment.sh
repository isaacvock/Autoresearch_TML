#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

if [[ "${1:-}" != "--experiment-id" || -z "${2:-}" || $# -ne 2 ]]; then
  echo "usage: $0 --experiment-id ID" >&2
  exit 2
fi
EXPERIMENT_ID="$2"
require_experiment_id "${EXPERIMENT_ID}"
validate_campaign

for FOLD in $(seq 0 $((N_FOLDS - 1))); do
  bash "${SCRIPT_DIR}/run_fold.sh" --experiment-id "${EXPERIMENT_ID}" --fold "${FOLD}"
done

MOTIF_SPECS_FILE="${RUNS_ROOT}/${EXPERIMENT_ID}/config/motifs.tsv"
"${PYTHON_BIN}" -m autoresearch_harness score \
  --experiment-dir "${RUNS_ROOT}/${EXPERIMENT_ID}" \
  --motifs "${MOTIF_SPECS_FILE}" \
  --expected-folds "${N_FOLDS}" \
  --pearson-tolerance "${PEARSON_TOLERANCE}" \
  --motif-tolerance "${MOTIF_TOLERANCE}"

"${PYTHON_BIN}" -m autoresearch_harness record-score \
  --root "${AUTORESEARCH_ROOT}" \
  --experiment-id "${EXPERIMENT_ID}" \
  --runs-root "${RUNS_ROOT}"

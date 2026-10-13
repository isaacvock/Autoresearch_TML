#!/bin/bash
#SBATCH --partition=akundaje
#SBATCH --job-name=tml_aggregate
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=sherlock_config.sh
source "${SCRIPT_DIR}/sherlock_config.sh"
setup_transcriptml_env
# shellcheck source=../workflow/common.sh
source "${AUTORESEARCH_ROOT}/workflow/common.sh"

: "${AUTORESEARCH_EXPERIMENT_ID:?AUTORESEARCH_EXPERIMENT_ID was not exported by the submitter}"

"${PYTHON_BIN}" -m autoresearch_harness score \
  --experiment-dir "${RUNS_ROOT}/${AUTORESEARCH_EXPERIMENT_ID}" \
  --motifs "${MOTIF_SPECS_FILE}" \
  --expected-folds "${N_FOLDS}" \
  --pearson-tolerance "${PEARSON_TOLERANCE}" \
  --motif-tolerance "${MOTIF_TOLERANCE}"

"${PYTHON_BIN}" -m autoresearch_harness record-score \
  --root "${AUTORESEARCH_ROOT}" \
  --experiment-id "${AUTORESEARCH_EXPERIMENT_ID}" \
  --runs-root "${RUNS_ROOT}"

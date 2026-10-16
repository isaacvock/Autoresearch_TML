#!/bin/bash
#SBATCH --partition=akundaje
#SBATCH --job-name=tml_autoresearch
#SBATCH --cpus-per-task=4
#SBATCH --gpus=1
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH -C GPU_MEM:48GB

set -euo pipefail

: "${AUTORESEARCH_ROOT:?AUTORESEARCH_ROOT was not exported by the submitter}"
# shellcheck source=sherlock_config.sh
source "${AUTORESEARCH_ROOT}/workflow_slurm/sherlock_config.sh"
setup_transcriptml_env

: "${AUTORESEARCH_EXPERIMENT_ID:?AUTORESEARCH_EXPERIMENT_ID was not exported by the submitter}"
: "${SLURM_ARRAY_TASK_ID:?This script must run as a Slurm array task}"

exec bash "${AUTORESEARCH_ROOT}/workflow/run_fold.sh" \
  --experiment-id "${AUTORESEARCH_EXPERIMENT_ID}" \
  --fold "${SLURM_ARRAY_TASK_ID}"

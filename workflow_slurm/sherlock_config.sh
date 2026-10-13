#!/bin/bash

# Sherlock-specific environment activation. Campaign parameters live only in
# workflow/campaign.env so local and Slurm execution cannot silently diverge.

SLURM_WORKFLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="${AUTORESEARCH_ROOT:-$(cd "${SLURM_WORKFLOW_DIR}/.." && pwd)}"

CONDA_ENV="${CONDA_ENV:-transcript-ml}"
SHERLOCK_CONDA_ROOT="${SHERLOCK_CONDA_ROOT:-${GROUP_HOME:-${HOME}}/miniconda}"

setup_transcriptml_env() {
  if command -v module >/dev/null 2>&1; then
    module load gcc/10.1.0
    module load openblas/0.3.10
  fi
  if [[ ! -f "${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh" ]]; then
    echo "Conda initialization not found at ${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh" >&2
    echo "Set SHERLOCK_CONDA_ROOT to the Sherlock Conda installation root." >&2
    return 1
  fi
  # shellcheck source=/dev/null
  source "${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh"
  conda activate "${CONDA_ENV}"
  command -v transcriptml >/dev/null 2>&1 || {
    echo "transcriptml is not installed in Conda environment ${CONDA_ENV}" >&2
    return 1
  }
  export AUTORESEARCH_ROOT
  export PYTHONPATH="${AUTORESEARCH_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
}

#!/bin/bash

# Sherlock-specific environment activation. Campaign parameters live in
# workflow/campaign.env and user paths/environment settings live in config.sh.

SLURM_WORKFLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${SLURM_WORKFLOW_DIR}/.." && pwd)"
# shellcheck source=../config.sh
source "${AUTORESEARCH_ROOT}/config.sh"

DATASET_DIR="${SHERLOCK_DATASET_DIR}"
RUNS_ROOT="${SHERLOCK_RUNS_ROOT}"
CODEX_BIN="${SHERLOCK_CODEX_BIN}"
CONDA_ENV="${SHERLOCK_CONDA_ENV}"

setup_transcriptml_env() {
  if command -v module >/dev/null 2>&1; then
    module load gcc/10.1.0
    module load openblas/0.3.10
  fi
  if [[ ! -f "${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh" ]]; then
    echo "Conda initialization not found at ${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh" >&2
    echo "Edit SHERLOCK_CONDA_ROOT in config.sh." >&2
    return 1
  fi
  # shellcheck source=/dev/null
  source "${SHERLOCK_CONDA_ROOT}/etc/profile.d/conda.sh"
  conda activate "${CONDA_ENV}"
  command -v transcriptml >/dev/null 2>&1 || {
    echo "transcriptml is not installed in Conda environment ${CONDA_ENV}" >&2
    return 1
  }
  export AUTORESEARCH_ROOT DATASET_DIR RUNS_ROOT CODEX_BIN CONDA_ENV SHERLOCK_CONDA_ROOT
  export PYTHONPATH="${AUTORESEARCH_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
}

setup_sherlock_codex() {
  if ! command -v module >/dev/null 2>&1; then
    echo "The Sherlock module command is unavailable; cannot load Codex." >&2
    return 1
  fi
  module load codex
  command -v "${CODEX_BIN}" >/dev/null 2>&1 || {
    echo "Codex command not found after 'module load codex': ${CODEX_BIN}" >&2
    return 1
  }
  export CODEX_BIN
}

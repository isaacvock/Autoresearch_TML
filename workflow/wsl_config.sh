#!/bin/bash

# Local WSL environment activation. All user settings live in config.sh.

WORKFLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${WORKFLOW_DIR}/.." && pwd)"
# shellcheck source=../config.sh
source "${AUTORESEARCH_ROOT}/config.sh"

DATASET_DIR="${WSL_DATASET_DIR}"
RUNS_ROOT="${WSL_RUNS_ROOT}"
CODEX_BIN="${WSL_CODEX_BIN}"

setup_wsl_transcriptml_env() {
  local conda_sh="${WSL_CONDA_ROOT}/etc/profile.d/conda.sh"
  if [[ ! -f "${conda_sh}" ]]; then
    echo "Conda initialization not found at ${conda_sh}; edit WSL_CONDA_ROOT in config.sh." >&2
    return 1
  fi
  # shellcheck source=/dev/null
  source "${conda_sh}"
  conda activate "${WSL_CONDA_ENV}"
  command -v transcriptml >/dev/null 2>&1 || {
    echo "transcriptml is not installed in WSL Conda environment ${WSL_CONDA_ENV}" >&2
    return 1
  }
  export AUTORESEARCH_ROOT DATASET_DIR RUNS_ROOT CODEX_BIN
}

#!/bin/bash

# Local WSL environment activation. Override WSL_CONDA_ROOT only when Conda is
# installed outside the common locations below.

WSL_CONDA_ENV="${WSL_CONDA_ENV:-transcript-ml2}"

setup_wsl_transcriptml_env() {
  local conda_sh=""
  local candidate
  if [[ -n "${WSL_CONDA_ROOT:-}" ]]; then
    conda_sh="${WSL_CONDA_ROOT}/etc/profile.d/conda.sh"
  else
    for candidate in "${HOME}/miniforge3" "${HOME}/miniconda3" "${HOME}/anaconda3"; do
      if [[ -f "${candidate}/etc/profile.d/conda.sh" ]]; then
        conda_sh="${candidate}/etc/profile.d/conda.sh"
        break
      fi
    done
  fi
  if [[ -n "${conda_sh}" && -f "${conda_sh}" ]]; then
    # shellcheck source=/dev/null
    source "${conda_sh}"
  elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
  else
    echo "Could not locate Conda. Set WSL_CONDA_ROOT to the Conda installation root." >&2
    return 1
  fi
  conda activate "${WSL_CONDA_ENV}"
  command -v transcriptml >/dev/null 2>&1 || {
    echo "transcriptml is not installed in WSL Conda environment ${WSL_CONDA_ENV}" >&2
    return 1
  }
}

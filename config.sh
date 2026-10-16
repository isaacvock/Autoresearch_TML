#!/bin/bash

# User configuration for both supported execution environments.
# Edit this file once after cloning the repository. Launch scripts select the
# WSL or Sherlock section automatically; do not export these values manually.

# Local WSL
WSL_DATASET_DIR="/path/to/imported/transcriptml_dataset"
WSL_RUNS_ROOT="${AUTORESEARCH_ROOT}/runs"
WSL_CODEX_BIN="/path/to/codex"
WSL_CONDA_ROOT="/home/isaac/miniforge3"
WSL_CONDA_ENV="transcript-ml2"

# Sherlock
SHERLOCK_DATASET_DIR="/scratch/users/${USER}/path/to/imported/transcriptml_dataset"
SHERLOCK_RUNS_ROOT="/scratch/users/${USER}/saluki-autoresearch-runs"
# The Sherlock supervisor loads the "codex" module, which provides this command.
SHERLOCK_CODEX_BIN="codex"
SHERLOCK_CONDA_ROOT="${GROUP_HOME:-${HOME}}/miniconda"
SHERLOCK_CONDA_ENV="transcript-ml"

# Motif-ablation objective, shared by WSL and Sherlock.
# Each entry is "LABEL=MOTIF". Use one entry for a single-motif objective or
# multiple entries to minimize the maximum of their pooled median A - R effects.
MOTIFS_TO_ABLATE=(
  "let7_7mer_m8=CUACCUC"
)

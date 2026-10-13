#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=wsl_config.sh
source "${SCRIPT_DIR}/wsl_config.sh"
setup_wsl_transcriptml_env

export AUTORESEARCH_EXECUTION_MODE=local
export PYTHONPATH="${AUTORESEARCH_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec python -m autoresearch_harness supervisor --root "${AUTORESEARCH_ROOT}" "$@"

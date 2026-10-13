#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=wsl_config.sh
source "${SCRIPT_DIR}/wsl_config.sh"
setup_wsl_transcriptml_env

exec bash "${SCRIPT_DIR}/run_experiment.sh" "$@"

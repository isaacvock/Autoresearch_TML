#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=sherlock_config.sh
source "${SCRIPT_DIR}/sherlock_config.sh"
setup_transcriptml_env

export AUTORESEARCH_EXECUTION_MODE=slurm
exec python -m autoresearch_harness supervisor --root "${AUTORESEARCH_ROOT}" "$@"

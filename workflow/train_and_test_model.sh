#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_ID="${EXPERIMENT_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}"

echo "Deprecated entry point: running the unified five-fold workflow as ${EXPERIMENT_ID}" >&2
exec bash "${SCRIPT_DIR}/run_experiment.sh" --experiment-id "${EXPERIMENT_ID}"

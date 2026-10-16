#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=autoresearch_scrontab_common.sh
source "${SCRIPT_DIR}/autoresearch_scrontab_common.sh"

if [[ -f "${AUTORESEARCH_ROOT}/runtime/STOP" ]]; then
  echo "Campaign control: stopped (runtime/STOP exists)"
else
  echo "Campaign control: allowed to run"
fi

if command -v scrontab >/dev/null 2>&1 && scrontab_has_autoresearch; then
  echo "Sherlock schedule: enabled (every five minutes)"
else
  echo "Sherlock schedule: disabled"
fi

state_file="${AUTORESEARCH_ROOT}/runtime/state.json"
if [[ -f "${state_file}" ]]; then
  echo
  echo "Saved campaign state:"
  if command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool "${state_file}"
  else
    sed 's/^/  /' "${state_file}"
  fi
else
  echo "Saved campaign state: none yet"
fi

if command -v squeue >/dev/null 2>&1; then
  echo
  echo "Related Slurm jobs:"
  squeue --me --name=saluki-autoresearch,tml_autoresearch,tml_aggregate
fi

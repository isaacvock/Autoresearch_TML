#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=autoresearch_scrontab_common.sh
source "${SCRIPT_DIR}/autoresearch_scrontab_common.sh"

mkdir -p "${AUTORESEARCH_ROOT}/runtime"
touch "${AUTORESEARCH_ROOT}/runtime/STOP"

if command -v scrontab >/dev/null 2>&1; then
  temporary_dir="$(mktemp -d)"
  trap 'rm -rf -- "${temporary_dir}"' EXIT
  current="${temporary_dir}/current"
  updated="${temporary_dir}/updated"
  errors="${temporary_dir}/errors"
  read_user_scrontab "${current}" "${errors}"
  remove_autoresearch_block "${current}" "${updated}"
  scrontab "${updated}"
fi

echo "Autoresearch is stopped. Running training jobs were not cancelled."

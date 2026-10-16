#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTORESEARCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=autoresearch_scrontab_common.sh
source "${SCRIPT_DIR}/autoresearch_scrontab_common.sh"

command -v scrontab >/dev/null 2>&1 || {
  echo "Sherlock's scrontab command is unavailable." >&2
  exit 1
}
if [[ "${AUTORESEARCH_ROOT}" =~ [[:space:]] ]]; then
  echo "The repository path cannot contain whitespace in a scrontab entry: ${AUTORESEARCH_ROOT}" >&2
  exit 1
fi

# Validate the configured environments and campaign before enabling unattended
# execution. This does not invoke Codex or submit an experiment.
# shellcheck source=sherlock_config.sh
source "${SCRIPT_DIR}/sherlock_config.sh"
setup_transcriptml_env
setup_sherlock_codex
# shellcheck source=../workflow/common.sh
source "${AUTORESEARCH_ROOT}/workflow/common.sh"
validate_campaign

mkdir -p "${AUTORESEARCH_ROOT}/runtime"
temporary_dir="$(mktemp -d)"
trap 'rm -rf -- "${temporary_dir}"' EXIT
current="${temporary_dir}/current"
without_block="${temporary_dir}/without-block"
updated="${temporary_dir}/updated"
errors="${temporary_dir}/errors"

read_user_scrontab "${current}" "${errors}"
remove_autoresearch_block "${current}" "${without_block}"
cp "${without_block}" "${updated}"
if [[ -s "${updated}" ]]; then
  printf '\n' >>"${updated}"
fi
printf '%s\n' \
  "${AUTORESEARCH_SCRONTAB_BEGIN}" \
  '#SCRON -p service' \
  '#SCRON --name=saluki-autoresearch' \
  '#SCRON -t 01:00:00' \
  '#SCRON -c 1' \
  '#SCRON --mem=2G' \
  '#SCRON --dependency=singleton' \
  "#SCRON -o ${AUTORESEARCH_ROOT}/runtime/supervisor.log" \
  '#SCRON --open-mode=append' \
  "*/5 * * * * bash ${AUTORESEARCH_ROOT}/workflow_slurm/supervisor_once_sherlock.sh" \
  "${AUTORESEARCH_SCRONTAB_END}" >>"${updated}"

scrontab "${updated}"
rm -f "${AUTORESEARCH_ROOT}/runtime/STOP"
echo "Autoresearch scheduled every five minutes on Sherlock."
echo "Log: ${AUTORESEARCH_ROOT}/runtime/supervisor.log"
echo "Use workflow_slurm/status_autoresearch.sh to inspect it."

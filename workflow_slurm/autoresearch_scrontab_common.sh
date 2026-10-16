#!/bin/bash

# Shared, non-destructive helpers for managing only this project's block in the
# user's Sherlock scrontab. Other scheduled jobs are preserved verbatim.

AUTORESEARCH_SCRONTAB_BEGIN="# BEGIN SALUKI_AUTORESEARCH"
AUTORESEARCH_SCRONTAB_END="# END SALUKI_AUTORESEARCH"

read_user_scrontab() {
  local output_file="$1"
  local error_file="$2"
  if scrontab -l >"${output_file}" 2>"${error_file}"; then
    return 0
  fi
  if grep -Eqi 'no (s?crontab|crontab)' "${error_file}"; then
    : >"${output_file}"
    return 0
  fi
  echo "Could not read the existing Sherlock scrontab:" >&2
  sed 's/^/  /' "${error_file}" >&2
  return 1
}

remove_autoresearch_block() {
  local input_file="$1"
  local output_file="$2"
  if ! awk \
    -v begin="${AUTORESEARCH_SCRONTAB_BEGIN}" \
    -v end="${AUTORESEARCH_SCRONTAB_END}" '
      $0 == begin {
        if (skipping) invalid = 1
        skipping = 1
        begins += 1
        next
      }
      $0 == end {
        if (!skipping) invalid = 1
        skipping = 0
        ends += 1
        next
      }
      !skipping { print }
      END {
        if (invalid || skipping || begins != ends) exit 2
      }
    ' "${input_file}" >"${output_file}"; then
    echo "The existing scrontab contains an incomplete autoresearch block; refusing to rewrite it." >&2
    return 1
  fi
}

scrontab_has_autoresearch() {
  scrontab -l 2>/dev/null | grep -Fqx "${AUTORESEARCH_SCRONTAB_BEGIN}"
}

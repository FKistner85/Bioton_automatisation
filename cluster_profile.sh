#!/usr/bin/env bash
# Source a trusted, local cluster profile before resolving launcher defaults.
# Profiles should use ${VAR:-default} so explicit environment overrides win.
if [[ -n "${BIOOTON_CLUSTER_PROFILE:-}" ]]; then
  [[ -f "${BIOOTON_CLUSTER_PROFILE}" ]] || { echo "Missing cluster profile: ${BIOOTON_CLUSTER_PROFILE}" >&2; return 1; }
  source "${BIOOTON_CLUSTER_PROFILE}"
fi

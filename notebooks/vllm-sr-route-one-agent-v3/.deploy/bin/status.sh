#!/usr/bin/env bash
set -euo pipefail

source /opt/workshop/config/environment.env

check() {
  local name=$1
  local url=$2
  if curl --fail --silent --show-error --max-time 2 "${url}" >/dev/null; then
    printf '✓ %-20s ready\n' "${name}"
  else
    printf '○ %-20s not ready\n' "${name}"
  fi
}

check "routine model" "${ROUTINE_ENDPOINT}/v1/models"
check "reasoning model" "${REASONING_ENDPOINT}/v1/models"
check "semantic router" "${ROUTER_API}/v1/models"
check "router management" "${ROUTER_MANAGEMENT_API}/health"
check "dashboard" "${DASHBOARD_URL}/"

if command -v hermes >/dev/null 2>&1; then
  printf '✓ %-20s ready\n' "Hermes"
else
  printf '○ %-20s not installed\n' "Hermes"
fi

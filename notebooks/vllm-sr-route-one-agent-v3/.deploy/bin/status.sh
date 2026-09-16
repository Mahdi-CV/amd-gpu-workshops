#!/usr/bin/env bash
set -euo pipefail

check() {
  local name=$1
  local url=$2
  if curl --fail --silent --show-error --max-time 2 "${url}" >/dev/null; then
    printf '✓ %-20s ready\n' "${name}"
  else
    printf '○ %-20s not ready\n' "${name}"
  fi
}

check "routine model" "http://127.0.0.1:8002/v1/models"
check "reasoning model" "http://127.0.0.1:8001/v1/models"
check "semantic router" "http://127.0.0.1:8898/v1/models"
check "router management" "http://127.0.0.1:8080/health"
check "dashboard" "http://127.0.0.1:8700/"

if command -v hermes >/dev/null 2>&1; then
  printf '✓ %-20s ready\n' "Hermes"
else
  printf '○ %-20s not installed\n' "Hermes"
fi

#!/usr/bin/env bash
set -euo pipefail

count_requests() {
  local endpoint=$1
  curl --fail --silent --show-error "${endpoint}/metrics" |
    awk '
      /^vllm:request_success_total{/ &&
      $0 !~ /finished_reason="error"/ &&
      $0 !~ /finished_reason="abort"/ {
        total += $NF
      }
      END {
        if (total == "") {
          print "unavailable"
        } else {
          printf "%.0f\n", total
        }
      }
    '
}

printf '%-16s %s\n' "routine-model" "$(count_requests http://127.0.0.1:8002)"
printf '%-16s %s\n' "reasoning-model" "$(count_requests http://127.0.0.1:8001)"

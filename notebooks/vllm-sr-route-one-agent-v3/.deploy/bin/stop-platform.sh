#!/usr/bin/env bash
set -euo pipefail

STATE_DIR=/workspace/state

for service in dashboard envoy router; do
  pid_file="${STATE_DIR}/${service}.pid"
  if [[ ! -f "${pid_file}" ]]; then
    continue
  fi
  pid=$(cat "${pid_file}")
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}"
    for _ in $(seq 1 20); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
  fi
  rm -f "${pid_file}"
done

echo "Routing platform stopped."

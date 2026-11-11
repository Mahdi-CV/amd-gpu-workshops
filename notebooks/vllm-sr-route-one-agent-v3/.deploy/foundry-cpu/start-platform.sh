#!/usr/bin/env bash
# Starts the Foundry relay, the vLLM-SR Router (with d3-lite) and the Dashboard, each only if
# it is not already running, then waits until all answer. Safe to run again.
# Used by the container's start script and by lab.start_platform() in the notebook.
set -euo pipefail

LOG_DIR=/workspace/logs
STATE_DIR=/workspace/state
CONFIG_PATH="${ROUTER_CONFIG_PATH:-/workspace/generated-config/router.yaml}"
DASHBOARD_DATA=/var/lib/vllm-sr-dashboard   # inside the container: a new container starts a fresh login
mkdir -p "$LOG_DIR" "$STATE_DIR" "$(dirname "$CONFIG_PATH")" "$DASHBOARD_DATA"

# The workshop's routing policy; the notebook replaces it in Section 7.
[ -f "$CONFIG_PATH" ] || cp /opt/workshop/config/router.yaml "$CONFIG_PATH"

running() { [ -f "$STATE_DIR/$1.pid" ] && kill -0 "$(cat "$STATE_DIR/$1.pid")" 2>/dev/null; }

start() {   # name, then the command; runs in its own session so a notebook interrupt cannot stop it
  local name=$1; shift
  if running "$name"; then echo "✓ $name already running"; return; fi
  setsid "$@" </dev/null >>"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$STATE_DIR/$name.pid"
  echo "  started $name (pid $!)"
}

wait_http() {   # name, url, seconds
  for _ in $(seq 1 "$3"); do
    if curl -fsS -m 3 -o /dev/null "$2" 2>/dev/null; then echo "✓ $1"; return 0; fi
    sleep 1
  done
  echo "✗ $1 not ready after $3 s: $2 (log: $LOG_DIR)" >&2
  return 1
}

if [ -z "${FOUNDRY_ENDPOINT:-}" ] || [ -z "${FOUNDRY_API_KEY:-}" ]; then
  echo "FOUNDRY_ENDPOINT and FOUNDRY_API_KEY are not set; the two model lanes cannot answer." >&2
fi
start foundry-relay python3 /opt/workshop/bin/foundry_proxy.py
wait_http "routine model (relay :8002)" "http://127.0.0.1:8002/v1/models" 30
wait_http "reasoning model (relay :8001)" "http://127.0.0.1:8001/v1/models" 30

# The Router serves the routed API on :8898 itself (no Envoy) and starts d3-lite on the CPU.
start router env HF_HUB_OFFLINE=1 /usr/local/bin/router \
  -config="$CONFIG_PATH" -port=50051 -enable-api=true \
  -gateway=standalone -listener-address=127.0.0.1
wait_http "Router management API" "http://127.0.0.1:8080/health" 600
wait_http "routed model (vllm-sr/auto on :8898)" "http://127.0.0.1:8898/v1/models" 120

start dashboard env -C "$DASHBOARD_DATA" \
  DASHBOARD_ADMIN_EMAIL="${DASHBOARD_ADMIN_EMAIL:-admin@workshop.local}" \
  DASHBOARD_ADMIN_PASSWORD="${DASHBOARD_ADMIN_PASSWORD:-workshop2026}" \
  DASHBOARD_JWT_SECRET="${DASHBOARD_JWT_SECRET:-workshop-jwt-secret}" \
  VLLM_SR_GATEWAY=standalone \
  /usr/local/bin/dashboard-backend \
    -port=9000 \
    -static=/opt/vllm-sr-dashboard/frontend \
    -config="$CONFIG_PATH" \
    -router_api=http://127.0.0.1:8080 \
    -router_metrics=http://127.0.0.1:9190/metrics \
    -envoy=http://127.0.0.1:8898 \
    -python=/opt/workshop-venv/bin/python3 \
    -auth-db="$DASHBOARD_DATA/auth.db" \
    -workflow-db="$DASHBOARD_DATA/workflow.sqlite" \
    -config-projection-db="$DASHBOARD_DATA/config-projection.sqlite"
wait_http "Dashboard (:9000)" "http://127.0.0.1:9000" 60

echo
echo "Routing platform is ready."

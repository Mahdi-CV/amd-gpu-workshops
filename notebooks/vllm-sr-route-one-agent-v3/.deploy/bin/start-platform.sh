#!/usr/bin/env bash
set -euo pipefail

source /opt/workshop/config/environment.env

STATE_DIR=/workspace/state
LOG_DIR=/workspace/logs
CONFIG_PATH=/workspace/generated-config/router.yaml

mkdir -p "${STATE_DIR}" "${LOG_DIR}" /workspace/generated-config /workspace/state/hermes

/opt/workshop/bin/configure-hermes.sh

wait_http() {
  local name=$1
  local url=$2
  local attempts=${3:-120}
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl --fail --silent --max-time 3 "${url}" >/dev/null 2>&1; then
      printf '✓ %s\n' "${name}"
      return 0
    fi
    sleep 2
  done
  printf '✗ %s did not become ready: %s\n' "${name}" "${url}" >&2
  return 1
}

wait_http "routine model" "${ROUTINE_ENDPOINT}/v1/models"
wait_http "reasoning model" "${REASONING_ENDPOINT}/v1/models"

cp /opt/workshop/config/router-demo.yaml "${CONFIG_PATH}"

# The Python vllm-sr tooling requires providers.defaults.default_model for envoy
# config generation and validation, but the Go router binary rejects it as
# deprecated.  Build a temp config that keeps the field for the Python tools,
# while the actual CONFIG_PATH (used by the Go binary) omits it.
ENVOY_GEN_CONFIG=$(mktemp "${STATE_DIR}/envoy-gen-XXXXXX.yaml")
python3 -c "
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
cfg.setdefault('providers', {}).setdefault('defaults', {})['default_model'] = \
    cfg['providers']['models'][0]['name']
yaml.safe_dump(cfg, open(sys.argv[2], 'w'), sort_keys=False)
" "${CONFIG_PATH}" "${ENVOY_GEN_CONFIG}"

vllm-sr validate --config "${ENVOY_GEN_CONFIG}"
vllm-sr config envoy --config "${ENVOY_GEN_CONFIG}" \
  | sed -n '/^admin:/,$p' >"${STATE_DIR}/envoy.yaml"
rm -f "${ENVOY_GEN_CONFIG}"

if [[ -f "${STATE_DIR}/router.pid" ]] \
  && kill -0 "$(cat "${STATE_DIR}/router.pid")" 2>/dev/null; then
  echo "✓ Router already running"
else
  nohup /usr/local/bin/router \
    -config="${CONFIG_PATH}" \
    -port=50051 \
    -enable-api=true \
    </dev/null >"${LOG_DIR}/router.log" 2>&1 &
  echo $! >"${STATE_DIR}/router.pid"
fi
wait_http "Router management" "${ROUTER_MANAGEMENT_API}/health"

if [[ -f "${STATE_DIR}/envoy.pid" ]] \
  && kill -0 "$(cat "${STATE_DIR}/envoy.pid")" 2>/dev/null; then
  echo "✓ Envoy already running"
else
  nohup /usr/local/bin/envoy \
    -c "${STATE_DIR}/envoy.yaml" \
    --log-level info \
    --disable-hot-restart \
    </dev/null >"${LOG_DIR}/envoy.log" 2>&1 &
  echo $! >"${STATE_DIR}/envoy.pid"
fi
wait_http "routed model" "${ROUTER_API}/v1/models"

if [[ -f "${STATE_DIR}/dashboard.pid" ]] \
  && kill -0 "$(cat "${STATE_DIR}/dashboard.pid")" 2>/dev/null; then
  echo "✓ Dashboard already running"
else
  ROUTER_CONFIG_PATH="${CONFIG_PATH}" \
  DASHBOARD_CONFIG_DIR="${STATE_DIR}/dashboard" \
  DASHBOARD_AUTH_DB_PATH="${STATE_DIR}/dashboard/auth.db" \
  DASHBOARD_WORKFLOW_DB_PATH="${STATE_DIR}/dashboard/workflow.sqlite" \
  DASHBOARD_CONFIG_PROJECTION_DB_PATH="${STATE_DIR}/dashboard/config-projection.sqlite" \
  TARGET_ROUTER_API_URL="${ROUTER_MANAGEMENT_API}" \
  TARGET_ROUTER_METRICS_URL="http://127.0.0.1:9190/metrics" \
  TARGET_ENVOY_URL="${ROUTER_API}" \
  DASHBOARD_ADMIN_EMAIL="${DASHBOARD_ADMIN_EMAIL:-admin@workshop.local}" \
  DASHBOARD_ADMIN_PASSWORD="${DASHBOARD_ADMIN_PASSWORD:-workshop2026}" \
  DASHBOARD_JWT_SECRET="${DASHBOARD_JWT_SECRET:-workshop-jwt-secret-$(hostname)}" \
  nohup /opt/vllm-sr/dashboard-backend \
    -port=9000 \
    -static=/opt/vllm-sr/frontend \
    -config="${CONFIG_PATH}" \
    </dev/null >"${LOG_DIR}/dashboard.log" 2>&1 &
  echo $! >"${STATE_DIR}/dashboard.pid"
fi
wait_http "Dashboard" "${DASHBOARD_URL}"

echo
echo "Routing platform is ready."

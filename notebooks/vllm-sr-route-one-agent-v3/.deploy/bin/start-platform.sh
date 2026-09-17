#!/usr/bin/env bash
set -euo pipefail

source /opt/workshop/config/environment.env

STATE_DIR=/workspace/state
LOG_DIR=/workspace/logs
CONFIG_PATH=/workspace/generated-config/router.yaml

mkdir -p "${STATE_DIR}" "${LOG_DIR}" /workspace/generated-config

wait_http() {
  local name=$1
  local url=$2
  local attempts=${3:-120}
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl --fail --silent --show-error --max-time 3 "${url}" >/dev/null; then
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

if vllm-sr config validate --help >/dev/null 2>&1; then
  VALIDATE_COMMAND=(vllm-sr config validate)
else
  VALIDATE_COMMAND=(vllm-sr validate)
fi

ENVOY_GEN_CONFIG="${CONFIG_PATH}"
VALIDATION_LOG=$(mktemp "${STATE_DIR}/validate-XXXXXX.log")
if ! "${VALIDATE_COMMAND[@]}" --config "${CONFIG_PATH}" \
  >"${VALIDATION_LOG}" 2>&1; then
  if grep -Eq "Default model 'None' not found|providers.defaults.default_model" \
    "${VALIDATION_LOG}"; then
    ENVOY_GEN_CONFIG=$(mktemp "${STATE_DIR}/envoy-gen-XXXXXX.yaml")
    python3 - "${CONFIG_PATH}" "${ENVOY_GEN_CONFIG}" <<'PY'
import sys
import yaml

source, destination = sys.argv[1:3]
config = yaml.safe_load(open(source, encoding="utf-8"))
models = config["providers"]["models"]
config.setdefault("providers", {}).setdefault("defaults", {})[
    "default_model"
] = models[0]["name"]
with open(destination, "w", encoding="utf-8") as output:
    yaml.safe_dump(config, output, sort_keys=False)
PY
    "${VALIDATE_COMMAND[@]}" --config "${ENVOY_GEN_CONFIG}"
  else
    cat "${VALIDATION_LOG}" >&2
    rm -f "${VALIDATION_LOG}"
    exit 1
  fi
fi
rm -f "${VALIDATION_LOG}"

vllm-sr config envoy --config "${ENVOY_GEN_CONFIG}" >"${STATE_DIR}/envoy.yaml"
if [[ "${ENVOY_GEN_CONFIG}" != "${CONFIG_PATH}" ]]; then
  rm -f "${ENVOY_GEN_CONFIG}"
fi

if [[ -f "${STATE_DIR}/router.pid" ]] \
  && kill -0 "$(cat "${STATE_DIR}/router.pid")" 2>/dev/null; then
  echo "✓ Router already running"
else
  nohup /usr/local/bin/router \
    -config="${CONFIG_PATH}" \
    -port=50051 \
    -enable-api=true \
    >"${LOG_DIR}/router.log" 2>&1 &
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
    >"${LOG_DIR}/envoy.log" 2>&1 &
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
  DASHBOARD_ADMIN_EMAIL="${DASHBOARD_ADMIN_EMAIL:?DASHBOARD_ADMIN_EMAIL is required}" \
  DASHBOARD_ADMIN_PASSWORD="${DASHBOARD_ADMIN_PASSWORD:?DASHBOARD_ADMIN_PASSWORD is required}" \
  DASHBOARD_JWT_SECRET="${DASHBOARD_JWT_SECRET:?DASHBOARD_JWT_SECRET is required}" \
  nohup /opt/vllm-sr/dashboard-backend \
    -port=8700 \
    -static=/opt/vllm-sr/frontend \
    -config="${CONFIG_PATH}" \
    >"${LOG_DIR}/dashboard.log" 2>&1 &
  echo $! >"${STATE_DIR}/dashboard.pid"
fi
wait_http "Dashboard" "${DASHBOARD_URL}"

echo
echo "Routing platform is ready."

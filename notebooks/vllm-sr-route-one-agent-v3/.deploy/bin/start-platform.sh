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

# Patch dashboard frontend for /app/{pod}/ nginx proxy prefix.
# Two-part fix:
#   1. Patch the main JS bundle to pass basename to React Router's
#      BrowserRouter — this makes the SPA router strip /app/{pod}/ from
#      location.pathname when matching routes, so /app/{pod}/dashboard
#      correctly matches the /dashboard route.  React Router also prepends
#      basename when pushing history, so SPA navigation stays under the
#      proxy prefix.
#   2. Inject a small inline shim into index.html that:
#      a. Sets window.__VSR_BASE = "/app/{pod}" (read by the patched
#         BrowserRouter basename)
#      b. Intercepts fetch() so all server requests (e.g. /api/setup/state,
#         /wasm_exec.js) are routed through /app/{pod}/… via the proxy.
# HTML asset refs (href, src) are made relative (./) so static resources
# resolve against the current document URL (/app/{pod}/), which the proxy
# forwards to the dashboard-backend.
_dashboard_frontend="/opt/vllm-sr/frontend"
if [[ -f "${_dashboard_frontend}/index.html" ]] \
  && ! grep -q '__vsr_subpath_shim' "${_dashboard_frontend}/index.html" 2>/dev/null; then
  # Make HTML asset references relative
  sed -i 's|href="/|href="./|g; s|src="/|src="./|g' \
    "${_dashboard_frontend}/index.html"

  # Patch BrowserRouter to read basename from window.__VSR_BASE.
  # The main bundle renders: (0,N.jsx)(h,{children:…  (h = BrowserRouter)
  # We inject: basename:window.__VSR_BASE||"/"
  _main_js=$(ls "${_dashboard_frontend}"/assets/index-*.js 2>/dev/null | head -1)
  if [[ -n "${_main_js}" ]]; then
    python3 -c "
p='${_main_js}';j=open(p).read()
j=j.replace('(0,N.jsx)(h,{children:','(0,N.jsx)(h,{basename:window.__VSR_BASE||\"\/\",children:',1)
open(p,'w').write(j)
"
  fi

  # Patch the Vite/Rolldown chunk-path resolver in the vendor bundle.
  # The original prepends "/" making chunk URLs absolute to root.
  # We prepend __VSR_BASE so chunks route through /app/{pod}/ proxy.
  _vendor_js=$(ls "${_dashboard_frontend}"/assets/react-vendor-*.js 2>/dev/null | head -1)
  if [[ -n "${_vendor_js}" ]]; then
    python3 -c "
p='${_vendor_js}';j=open(p).read();bt=chr(96)
old='p=function(e){return'+bt+'/'+bt+'+e}'
new='p=function(e){return(window.__VSR_BASE||'+bt+bt+')+'+bt+'/'+bt+'+e}'
j=j.replace(old,new,1)
open(p,'w').write(j)
"
  fi

  # Inject fetch-intercept shim (no replaceState — URL stays at /app/{pod}/).
  python3 - "${_dashboard_frontend}/index.html" << 'PYSHIM'
import sys
path = sys.argv[1]
html = open(path).read()
shim = '<script data-id="__vsr_subpath_shim">\n'
shim += '(function(){\n'
shim += '  var m=location.pathname.match(/^\\/app\\/[^\\/]+/);\n'
shim += '  if(!m)return;\n'
shim += '  var base=m[0];\n'
shim += '  window.__VSR_BASE=base;\n'
shim += '  var F=window.fetch;\n'
shim += '  window.fetch=function(i,o){\n'
shim += '    if(typeof i==="string"&&/^\\/(?!app\\/)/.test(i))\n'
shim += '      i=base+i;\n'
shim += '    return F.call(this,i,o);\n'
shim += '  };\n'
shim += '})();\n'
shim += '</script>\n'
html = html.replace('<script type="module"', shim + '<script type="module"', 1)
open(path, 'w').write(html)
PYSHIM
fi

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

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

vllm-sr config envoy --config "${ENVOY_GEN_CONFIG}" \
  | sed -n '/^admin:/,$p' >"${STATE_DIR}/envoy.yaml"
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
#
# The dashboard is a React SPA that assumes it runs at "/". Behind nginx's
# /app/{pod}/ reverse-proxy every absolute URL (API calls, lazy-loaded CSS/JS
# chunks, WASM assets, dynamic <script>/<link> elements) must be rewritten to
# include the proxy prefix.
#
# Three patches applied at first boot:
#   1. BrowserRouter basename — makes React Router strip the prefix from
#      location.pathname so /app/{pod}/dashboard matches the /dashboard route.
#   2. Vite chunk resolver — the vendored p() prepends "/" to chunk filenames;
#      patched to prepend __VSR_BASE+"/" instead.
#   3. Inline shim in index.html — sets window.__VSR_BASE, then monkey-patches
#      fetch(), HTMLLinkElement.prototype.href setter,
#      HTMLScriptElement.prototype.src setter, and Element.prototype.setAttribute
#      so every absolute-path resource request routes through the proxy.
#
# HTML asset refs (href, src) are also made relative (./) so the initial
# script/css tags resolve against the document URL (/app/{pod}/).
_dashboard_frontend="/opt/vllm-sr/frontend"
if [[ -f "${_dashboard_frontend}/index.html" ]] \
  && ! grep -q '__vsr_subpath_shim' "${_dashboard_frontend}/index.html" 2>/dev/null; then
  # Make HTML asset references relative
  sed -i 's|href="/|href="./|g; s|src="/|src="./|g' \
    "${_dashboard_frontend}/index.html"

  # Apply all JS + HTML patches via a single Python script.
  python3 - "${_dashboard_frontend}" << 'PATCH_ALL'
import sys, os, glob, re

frontend = sys.argv[1]
assets   = os.path.join(frontend, "assets")

# --- Patch 1: BrowserRouter basename ---
for main_js in glob.glob(os.path.join(assets, "index-*.js")):
    js = open(main_js).read()
    old = "(0,N.jsx)(h,{children:"
    new = '(0,N.jsx)(h,{basename:window.__VSR_BASE||"/",children:'
    if old in js:
        js = js.replace(old, new, 1)
        open(main_js, "w").write(js)
        print(f"  patch-1 basename  -> {os.path.basename(main_js)}")

# --- Patch 2: Vite chunk resolver p() ---
bt = chr(96)  # backtick
for vendor_js in glob.glob(os.path.join(assets, "react-vendor-*.js")):
    js = open(vendor_js).read()
    old = f"p=function(e){{return{bt}/{bt}+e}}"
    new = f"p=function(e){{return(window.__VSR_BASE||{bt}{bt})+{bt}/{bt}+e}}"
    if old in js:
        js = js.replace(old, new, 1)
        open(vendor_js, "w").write(js)
        print(f"  patch-2 chunk-resolver -> {os.path.basename(vendor_js)}")

# --- Patch 3: comprehensive inline shim ---
html_path = os.path.join(frontend, "index.html")
html = open(html_path).read()
# The shim intercepts:
#  a) fetch()                          — API calls, WASM fetches
#  b) HTMLLinkElement.prototype.href   — CSS preloads from Vite lazy loader
#  c) HTMLScriptElement.prototype.src  — dynamic <script> elements (wasm_exec)
#  d) Element.prototype.setAttribute   — fallback for any other href/src sets
shim_lines = [
    '<script data-id="__vsr_subpath_shim">',
    "(function(){",
    "  var m=location.pathname.match(/^\\/app\\/[^\\/]+/);",
    "  if(!m)return;",
    "  var base=m[0];",
    "  window.__VSR_BASE=base;",
    '  function needs(u){return typeof u==="string"&&u.charAt(0)==="/"&&u.indexOf("/app/")!==0;}',
    "  var F=window.fetch;",
    "  window.fetch=function(i,o){if(needs(i))i=base+i;return F.call(this,i,o);};",
    "  function patchSetter(proto,attr){",
    "    var d=Object.getOwnPropertyDescriptor(proto,attr);",
    "    if(!d||!d.set)return;",
    "    Object.defineProperty(proto,attr,{",
    "      set:function(v){if(needs(v))v=base+v;d.set.call(this,v);},",
    "      get:d.get,enumerable:d.enumerable,configurable:true",
    "    });",
    "  }",
    '  patchSetter(HTMLLinkElement.prototype,"href");',
    '  patchSetter(HTMLScriptElement.prototype,"src");',
    "  var origSet=Element.prototype.setAttribute;",
    "  Element.prototype.setAttribute=function(name,val){",
    '    if((name==="href"||name==="src")&&needs(val))val=base+val;',
    "    return origSet.call(this,name,val);",
    "  };",
    "})();",
    "<" + "/script>",
]
shim = "\n".join(shim_lines) + "\n"
html = html.replace('<script type="module"', shim + '<script type="module"', 1)
open(html_path, "w").write(html)
print("  patch-3 shim -> index.html")
PATCH_ALL
fi

if [[ -f "${STATE_DIR}/dashboard.pid" ]] \
  && kill -0 "$(cat "${STATE_DIR}/dashboard.pid")" 2>/dev/null; then
  echo "✓ Dashboard already running"
else
  ROUTER_CONFIG_PATH="${CONFIG_PATH}" \
  VLLM_SR_SOURCE_CONFIG_PATH="${CONFIG_PATH}" \
  VLLM_SR_RUNTIME_CONFIG_PATH="${CONFIG_PATH}" \
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

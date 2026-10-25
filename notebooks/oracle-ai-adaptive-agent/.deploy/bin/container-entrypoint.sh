#!/usr/bin/env bash
set -euo pipefail

: "${WORKSHOP_UID:=1000}"
: "${WORKSHOP_GID:=1000}"
: "${WORKSHOP_ROOT:=/opt/workshop}"
: "${WORKSHOP_WORKSPACE:=/workspace}"
: "${WORKSHOP_RUNTIME_DIR:=/workspace/runtime}"
: "${AUTO_BASE_URL:?AUTO_BASE_URL is required}"
: "${AUTO_API_KEY_FILE:=/run/secrets/auto_api_key}"
: "${JUPYTER_TOKEN_FILE:=/run/secrets/jupyter_token}"
: "${JUPYTER_LISTEN_HOST:=0.0.0.0}"
: "${JUPYTER_LISTEN_PORT:=8888}"

for secret in "$AUTO_API_KEY_FILE" "$JUPYTER_TOKEN_FILE"; do
  if [[ ! -s "$secret" ]]; then
    echo "Missing or empty secret file: $secret" >&2
    exit 2
  fi
done

install -d -o "$WORKSHOP_UID" -g "$WORKSHOP_GID" \
  "$WORKSHOP_WORKSPACE" \
  "$WORKSHOP_WORKSPACE/agents" \
  "$WORKSHOP_WORKSPACE/demo" \
  "$WORKSHOP_WORKSPACE/notebooks" \
  "$WORKSHOP_WORKSPACE/results" \
  "$WORKSHOP_RUNTIME_DIR" \
  "$WORKSHOP_WORKSPACE/state"

touch "$WORKSHOP_RUNTIME_DIR/routes.jsonl"
printf '{"phase":"unmarked","timestamp":0}\n' \
  > "$WORKSHOP_RUNTIME_DIR/current-phase.json"
chown "$WORKSHOP_UID:$WORKSHOP_GID" \
  "$WORKSHOP_RUNTIME_DIR/routes.jsonl" \
  "$WORKSHOP_RUNTIME_DIR/current-phase.json"
chmod 0660 \
  "$WORKSHOP_RUNTIME_DIR/routes.jsonl" \
  "$WORKSHOP_RUNTIME_DIR/current-phase.json"

python3 "$WORKSHOP_ROOT/.deploy/bin/logging_proxy.py" \
  --listen-host 127.0.0.1 \
  --listen-port 19090 \
  --base-url "$AUTO_BASE_URL" \
  --api-key-file "$AUTO_API_KEY_FILE" \
  --log-jsonl "$WORKSHOP_RUNTIME_DIR/routes.jsonl" \
  --phase-file "$WORKSHOP_RUNTIME_DIR/current-phase.json" \
  --cost-factors "$WORKSHOP_ROOT/.deploy/config/cost-factors.json" \
  >"$WORKSHOP_RUNTIME_DIR/proxy.log" 2>&1 &
PROXY_PID=$!

cleanup() {
  kill "$PROXY_PID" 2>/dev/null || true
  wait "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:19090/readyz >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "Route proxy exited during startup." >&2
    tail -80 "$WORKSHOP_RUNTIME_DIR/proxy.log" >&2 || true
    exit 3
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:19090/readyz >/dev/null

gosu workshop "$WORKSHOP_ROOT/.deploy/bin/bootstrap-workshop.sh"

JUPYTER_CONFIG="$WORKSHOP_RUNTIME_DIR/jupyter_server_config.py"
JUPYTER_TOKEN="$(tr -d '\r\n' < "$JUPYTER_TOKEN_FILE")"
python3 - "$JUPYTER_CONFIG" "$JUPYTER_TOKEN" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
token = sys.argv[2]
path.write_text(
    "c.ServerApp.ip = '0.0.0.0'\n"
    "c.ServerApp.port = 8888\n"
    "c.ServerApp.open_browser = False\n"
    "c.ServerApp.allow_remote_access = True\n"
    "c.ServerApp.root_dir = '/workspace/notebooks'\n"
    "c.ServerApp.jpserver_extensions = {'jupyter_ai': False}\n"
    f"c.IdentityProvider.token = {token!r}\n"
)
PY
chown "$WORKSHOP_UID:$WORKSHOP_GID" "$JUPYTER_CONFIG"
chmod 0600 "$JUPYTER_CONFIG"

gosu workshop jupyter lab \
  --no-browser \
  --config "$JUPYTER_CONFIG" &
JUPYTER_PID=$!
wait "$JUPYTER_PID"

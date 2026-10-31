#!/usr/bin/env bash
set -euo pipefail

: "${BOOTH_DATA_DIR:=/data}"
: "${OPENCLAW_STATE_DIR:=/data/openclaw}"
: "${OPENCLAW_WORKSPACES:=/data/agents}"

mkdir -p \
  "$BOOTH_DATA_DIR" \
  "$BOOTH_DATA_DIR/runs" \
  "$OPENCLAW_STATE_DIR" \
  "$OPENCLAW_WORKSPACES"

if ! gosu booth test -w "$BOOTH_DATA_DIR"; then
  echo "$BOOTH_DATA_DIR must be writable by UID/GID 10001." >&2
  exit 2
fi

gosu booth python3 /opt/booth/bootstrap_openclaw.py

GATEWAY_LOG="$BOOTH_DATA_DIR/gateway.log"
gosu booth openclaw gateway >"$GATEWAY_LOG" 2>&1 &

gateway_ready=false
for _ in $(seq 1 90); do
  if python3 - <<'PY'
import socket
try:
    with socket.create_connection(("127.0.0.1", 18789), timeout=0.5):
        pass
except OSError:
    raise SystemExit(1)
PY
  then
    gateway_ready=true
    break
  fi
  sleep 1
done

if [[ "$gateway_ready" != true ]]; then
  echo "OpenClaw Gateway did not become ready." >&2
  tail -100 "$GATEWAY_LOG" >&2 || true
  exit 3
fi

exec gosu booth uvicorn app:app \
  --host 0.0.0.0 \
  --port 8088 \
  --app-dir /opt/booth \
  --proxy-headers \
  --forwarded-allow-ips='*'

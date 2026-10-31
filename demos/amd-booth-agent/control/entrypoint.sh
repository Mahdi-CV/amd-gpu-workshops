#!/usr/bin/env bash
set -euo pipefail

: "${BOOTH_DATA_DIR:=/data}"
: "${OPENCLAW_STATE_DIR:=/data/openclaw}"
: "${OPENCLAW_WORKSPACES:=/data/agents}"

install -d -o booth -g booth \
  "$BOOTH_DATA_DIR" \
  "$BOOTH_DATA_DIR/runs" \
  "$OPENCLAW_STATE_DIR" \
  "$OPENCLAW_WORKSPACES"

gosu booth python3 /opt/booth/bootstrap_openclaw.py

GATEWAY_LOG="$BOOTH_DATA_DIR/gateway.log"
gosu booth openclaw gateway >"$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!

cleanup() {
  kill "$GATEWAY_PID" 2>/dev/null || true
  wait "$GATEWAY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

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
    break
  fi
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    echo "OpenClaw Gateway exited during startup." >&2
    tail -100 "$GATEWAY_LOG" >&2 || true
    exit 3
  fi
  sleep 1
done

exec gosu booth uvicorn app:app \
  --host 0.0.0.0 \
  --port 8088 \
  --app-dir /opt/booth \
  --proxy-headers \
  --forwarded-allow-ips='*'

#!/usr/bin/env bash
set -euo pipefail

: "${WORKSHOP_ROOT:=/opt/workshop}"
: "${WORKSHOP_WORKSPACE:=/workspace}"
: "${OPENCLAW_STATE_DIR:=/workspace/state/openclaw}"
: "${OPENCLAW_WORKSHOP_WORKSPACES:=/workspace/agents}"
: "${OPENCLAW_WORKSHOP_DEMO_ROOT:=/workspace/demo}"

full=false
if [[ "${1:-}" == "--full" ]]; then
  full=true
fi

gosu workshop python3 - <<'PY'
from workshop_lab import lab
lab.stop_gateway()
PY

rm -rf \
  "$OPENCLAW_STATE_DIR" \
  "$OPENCLAW_WORKSHOP_WORKSPACES" \
  "$OPENCLAW_WORKSHOP_DEMO_ROOT"
rm -f \
  "$WORKSHOP_WORKSPACE/runtime/routes.jsonl" \
  "$WORKSHOP_WORKSPACE/runtime/current-phase.json" \
  "$WORKSHOP_WORKSPACE/runtime/verification.json" \
  "$WORKSHOP_WORKSPACE/runtime/gateway.log" \
  "$WORKSHOP_WORKSPACE/runtime/gateway.pid"

if "$full"; then
  rm -f \
    "$WORKSHOP_WORKSPACE/notebooks/workshop.ipynb" \
    "$WORKSHOP_WORKSPACE/notebooks/README.md"
fi

install -o workshop -g workshop -m 0660 /dev/null \
  "$WORKSHOP_WORKSPACE/runtime/routes.jsonl"
printf '{"phase":"unmarked","timestamp":0}\n' \
  > "$WORKSHOP_WORKSPACE/runtime/current-phase.json"
chown workshop:workshop \
  "$WORKSHOP_WORKSPACE/runtime/current-phase.json"
chmod 0660 "$WORKSHOP_WORKSPACE/runtime/current-phase.json"

gosu workshop "$WORKSHOP_ROOT/.deploy/bin/bootstrap-workshop.sh"
echo "Workshop reset complete."

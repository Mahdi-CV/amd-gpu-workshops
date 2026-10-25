#!/usr/bin/env bash
set -euo pipefail

: "${WORKSHOP_ROOT:=/opt/workshop}"
: "${WORKSHOP_WORKSPACE:=/workspace}"
: "${OPENCLAW_STATE_DIR:=/workspace/state/openclaw}"
: "${OPENCLAW_WORKSHOP_WORKSPACES:=/workspace/agents}"
: "${AUTO_MODEL:=vllm-sr/auto}"

mkdir -p \
  "$WORKSHOP_WORKSPACE/notebooks" \
  "$WORKSHOP_WORKSPACE/results" \
  "$WORKSHOP_WORKSPACE/runtime" \
  "$(dirname "$OPENCLAW_STATE_DIR")" \
  "$OPENCLAW_WORKSHOP_WORKSPACES"

if [[ ! -f "$WORKSHOP_WORKSPACE/notebooks/workshop.ipynb" ]]; then
  cp "$WORKSHOP_ROOT/workshop.ipynb" \
    "$WORKSHOP_WORKSPACE/notebooks/workshop.ipynb"
fi
if [[ ! -f "$WORKSHOP_WORKSPACE/notebooks/README.md" ]]; then
  cp "$WORKSHOP_ROOT/README.md" \
    "$WORKSHOP_WORKSPACE/notebooks/README.md"
fi

if [[ ! -f "$OPENCLAW_STATE_DIR/openclaw.json" ]]; then
  openclaw onboard \
    --non-interactive \
    --mode local \
    --workspace "$OPENCLAW_WORKSHOP_WORKSPACES/main" \
    --auth-choice custom-api-key \
    --custom-base-url http://127.0.0.1:19090/v1 \
    --custom-model-id "$AUTO_MODEL" \
    --custom-provider-id vllm-sr \
    --custom-compatibility openai \
    --custom-api-key proxy-local \
    --secret-input-mode plaintext \
    --skip-bootstrap \
    --skip-channels \
    --skip-search \
    --skip-hooks \
    --skip-ui \
    --skip-health \
    --accept-risk
fi

openclaw config set memory.search.enabled false
openclaw config set tools.profile coding

python3 - <<'PY'
from workshop_lab import lab
lab.reset_demo()
PY

echo "Workshop bootstrap complete."

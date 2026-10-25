#!/usr/bin/env bash
set -euo pipefail

: "${WORKSHOP_ROOT:=/opt/workshop}"
: "${WORKSHOP_WORKSPACE:=/workspace}"
: "${WORKSHOP_RUNTIME_DIR:=/workspace/runtime}"
: "${OPENCLAW_STATE_DIR:=/workspace/state/openclaw}"
: "${OPENCLAW_WORKSHOP_WORKSPACES:=/workspace/agents}"
: "${AUTO_MODEL:=vllm-sr/auto}"

mkdir -p \
  "$WORKSHOP_WORKSPACE/notebooks" \
  "$WORKSHOP_WORKSPACE/results" \
  "$WORKSHOP_WORKSPACE/runtime" \
  "$(dirname "$OPENCLAW_STATE_DIR")" \
  "$OPENCLAW_WORKSHOP_WORKSPACES"

for notebook in workshop.ipynb openclaw-multi-agent-workshop.ipynb; do
  if [[ ! -f "$WORKSHOP_WORKSPACE/notebooks/$notebook" ]]; then
    cp "$WORKSHOP_ROOT/$notebook" \
      "$WORKSHOP_WORKSPACE/notebooks/$notebook"
  fi
done
if [[ ! -f "$WORKSHOP_WORKSPACE/notebooks/README.md" ]]; then
  cp "$WORKSHOP_ROOT/README.md" \
    "$WORKSHOP_WORKSPACE/notebooks/README.md"
fi

onboard_workspace() {
  local state_dir="$1"
  local workspace_dir="$2"
  OPENCLAW_STATE_DIR="$state_dir" openclaw onboard \
    --non-interactive \
    --mode local \
    --workspace "$workspace_dir" \
    --auth-choice custom-api-key \
    --custom-base-url http://127.0.0.1:19090/v1 \
    --custom-model-id "$AUTO_MODEL" \
    --custom-provider-id vllm-sr \
    --custom-compatibility openai \
    --custom-api-key proxy-local \
    --secret-input-mode plaintext \
    --skip-channels \
    --skip-search \
    --skip-hooks \
    --skip-ui \
    --skip-health \
    --accept-risk
}

if [[ ! -f "$OPENCLAW_STATE_DIR/openclaw.json" ]]; then
  onboard_workspace \
    "$OPENCLAW_STATE_DIR" \
    "$OPENCLAW_WORKSHOP_WORKSPACES/main"
else
  # Older workshop images skipped workspace initialization, leaving the
  # participant's main workspace empty. Generate templates with this installed
  # OpenClaw version in isolated temporary state, then copy only missing files.
  missing_workspace_file=false
  for name in AGENTS.md SOUL.md IDENTITY.md USER.md BOOTSTRAP.md; do
    if [[ ! -f "$OPENCLAW_WORKSHOP_WORKSPACES/main/$name" ]]; then
      missing_workspace_file=true
      break
    fi
  done
  if [[ "$missing_workspace_file" == true ]]; then
    seed_root="$(
      mktemp -d "$WORKSHOP_RUNTIME_DIR/workspace-seed.XXXXXX"
    )"
    onboard_workspace "$seed_root/state" "$seed_root/workspace" \
      >/dev/null
    if [[ -f "$OPENCLAW_WORKSHOP_WORKSPACES/main/AGENTS.md" ]] \
      && ! grep -q "^## First Run" \
        "$OPENCLAW_WORKSHOP_WORKSPACES/main/AGENTS.md"; then
      {
        cat "$seed_root/workspace/AGENTS.md"
        printf "\n"
        cat "$OPENCLAW_WORKSHOP_WORKSPACES/main/AGENTS.md"
      } > "$seed_root/AGENTS.md"
      mv "$seed_root/AGENTS.md" \
        "$OPENCLAW_WORKSHOP_WORKSPACES/main/AGENTS.md"
    fi
    for name in AGENTS.md SOUL.md IDENTITY.md USER.md BOOTSTRAP.md; do
      if [[ ! -f "$OPENCLAW_WORKSHOP_WORKSPACES/main/$name" ]]; then
        cp "$seed_root/workspace/$name" \
          "$OPENCLAW_WORKSHOP_WORKSPACES/main/$name"
      fi
    done
    rm -rf "$seed_root"
  fi
fi

openclaw config set memory.search.enabled false
openclaw config set tools.profile coding

python3 - <<'PY'
from workshop_lab import lab
lab.reset_demo()
PY

echo "Workshop bootstrap complete."

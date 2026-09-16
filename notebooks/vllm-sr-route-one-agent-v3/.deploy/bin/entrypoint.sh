#!/usr/bin/env bash
set -euo pipefail

mkdir -p \
  /workspace/generated-config \
  /workspace/logs \
  /workspace/state/hermes

if [[ ! -f /workspace/route-one-agent-across-two-models-v3.ipynb ]]; then
  cp /opt/workshop/templates/route-one-agent-across-two-models-v3.ipynb \
    /workspace/
fi
if [[ ! -f /workspace/workshop_lab.py ]]; then
  cp /opt/workshop/templates/workshop_lab.py /workspace/
fi

/opt/workshop/bin/configure-hermes.sh

exec jupyter lab \
  --no-browser \
  --ip=0.0.0.0 \
  --port=8888 \
  --notebook-dir=/workspace \
  --ServerApp.allow_remote_access=true \
  --ServerApp.token="${JUPYTER_TOKEN:?JUPYTER_TOKEN is required}" \
  --allow-root

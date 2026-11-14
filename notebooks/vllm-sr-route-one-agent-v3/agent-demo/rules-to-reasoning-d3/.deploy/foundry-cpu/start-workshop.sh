#!/usr/bin/env bash
# Container entrypoint: workshop files, Hermes, the routing platform, then JupyterLab.
set -uo pipefail

mkdir -p /workspace/generated-config /workspace/logs /workspace/state

# Notebook files: setup.sh normally downloads them from GitHub into /workspace;
# when it could not, the copy shipped in this image is used. Existing student
# edits are never touched.
if [ ! -f /workspace/route-one-agent-across-two-models-v3.ipynb ]; then
  echo "== /workspace has no workshop files; using the copy in the image"
  cp -rn /opt/workshop/templates/. /workspace/
fi

# The platform starts in the background so JupyterLab is up at once; the
# notebook's first code cell reports readiness.
setsid /opt/workshop/bin/start-platform.sh >>/workspace/logs/start-platform.log 2>&1 &

exec jupyter lab \
  --ip="${JUPYTER_IP:-127.0.0.1}" --port="${JUPYTER_PORT:-8888}" \
  --no-browser --allow-root --notebook-dir=/workspace \
  --IdentityProvider.token="${JUPYTER_TOKEN:-}" --ServerApp.password=''

#!/usr/bin/env bash
set -euo pipefail

/opt/workshop/bin/stop-platform.sh

rm -rf \
  /workspace/generated-config/* \
  /workspace/logs/* \
  /workspace/state/dashboard

cp /opt/workshop/templates/route-one-agent-across-two-models-v3.ipynb \
  /workspace/route-one-agent-across-two-models-v3.ipynb
cp /opt/workshop/templates/workshop_lab.py /workspace/workshop_lab.py

/opt/workshop/bin/configure-hermes.sh

echo "Workshop files and platform state reset."
echo "Running vLLM terminal processes are not stopped by this script."

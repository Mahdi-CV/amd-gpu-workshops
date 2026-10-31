#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"
cd "$ROOT"

docker compose stop booth
rm -rf data/booth/openclaw data/booth/agents data/booth/runs
mkdir -p data/booth/runs
docker compose up -d booth
echo "Booth OpenClaw state reset. Model and Router services were preserved."

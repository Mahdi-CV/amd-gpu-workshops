#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

mkdir -p "$ROOT/data/router-config"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$ROOT:/work" \
  -w /work \
  python:3.12-slim \
  sh -lc '
    pip install --quiet --no-cache-dir -r router/requirements.txt &&
    python3 router/render_config.py \
      --input router/decision-balance-base.yaml \
      --output data/router-config/config.yaml
  '

echo "Rendered $ROOT/data/router-config/config.yaml"

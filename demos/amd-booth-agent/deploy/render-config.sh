#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

KIMI_MODEL="${KIMI_MODEL:-accounts/fireworks/models/kimi-k3}"

mkdir -p "$ROOT/data/router-config"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e KIMI_MODEL \
  -v "$ROOT:/work" \
  -w /work \
  python:3.12-slim \
  sh -lc '
    pip install --quiet --no-cache-dir -r router/requirements.txt &&
    python3 router/render_config.py \
      --input router/decision-balance-base.yaml \
      --output data/router-config/config.yaml \
      --kimi-provider-model "$KIMI_MODEL"
  '

echo "Rendered $ROOT/data/router-config/config.yaml"

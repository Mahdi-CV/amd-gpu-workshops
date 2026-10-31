#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

cd "$ROOT"

if [[ ! -s secrets/fireworks_api_key ]]; then
  echo "Missing secrets/fireworks_api_key" >&2
  exit 2
fi
chmod 0600 secrets/fireworks_api_key

mkdir -p \
  data/hf \
  data/router-config \
  data/router-models \
  data/booth

# The booth image runs OpenClaw as its dedicated UID/GID.
chown -R 10001:10001 data/booth

"$ROOT/deploy/render-config.sh"

docker compose pull local-model router
docker compose build booth
docker compose up -d

echo
docker compose ps
echo
echo "Public URL: https://${BOOTH_HOSTNAME:-agent.165.245.129.230.sslip.io}"

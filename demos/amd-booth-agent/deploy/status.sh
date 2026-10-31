#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"
cd "$ROOT"

docker compose ps
echo
curl -fsS http://127.0.0.1:${BOOTH_PORT:-18090}/healthz | jq .
echo
curl -fsS http://127.0.0.1:18899/v1/models | jq .

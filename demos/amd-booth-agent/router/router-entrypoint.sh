#!/usr/bin/env sh
set -eu

secret=/run/secrets/fireworks_api_key
if [ ! -s "$secret" ]; then
  echo "Missing Fireworks API key secret." >&2
  exit 2
fi

export FIREWORKS_API_KEY
FIREWORKS_API_KEY="$(tr -d '\r\n' < "$secret")"

exec /app/start-router.sh "$@"

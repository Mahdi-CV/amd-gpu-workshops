#!/usr/bin/env bash
set -euo pipefail

: "${WORKSHOP_ROOT:=/opt/workshop}"

openclaw --version | grep -F "2026.10.4"
node --version | grep -F "v24.16.0"
python3 --version
jupyter --version

test ! -e /dev/kfd
test ! -e /dev/dri/renderD128
test -f "$WORKSHOP_ROOT/workshop.ipynb"
test -f "$WORKSHOP_ROOT/.deploy/fixture/MANIFEST.sha256"

(
  cd "$WORKSHOP_ROOT/.deploy/fixture"
  sha256sum -c MANIFEST.sha256
)

python3 -m py_compile \
  "$WORKSHOP_ROOT/.deploy/bin/logging_proxy.py" \
  "$WORKSHOP_ROOT/.deploy/bin/endpoint_access.py" \
  "$WORKSHOP_ROOT/.deploy/lib/workshop_lab.py"

if rg -n \
  'vsr-[a-z0-9-]{8,}|OPENAI_API_KEY=[^$]|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY' \
  "$WORKSHOP_ROOT" \
  --glob '!*.ipynb'; then
  echo "Potential secret detected in image content." >&2
  exit 1
fi

echo "Image verification passed."

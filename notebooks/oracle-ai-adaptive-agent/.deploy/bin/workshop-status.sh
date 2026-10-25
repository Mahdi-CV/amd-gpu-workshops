#!/usr/bin/env bash
set -euo pipefail

json=false
if [[ "${1:-}" == "--json" ]]; then
  json=true
fi

if [[ "$(id -u)" -eq 0 ]]; then
  runner=(gosu workshop python3)
else
  runner=(python3)
fi

if "$json"; then
  "${runner[@]}" - <<'PY'
import json
from workshop_lab import lab
print(json.dumps(lab.status(), indent=2))
PY
else
  "${runner[@]}" - <<'PY'
from workshop_lab import lab
lab.check_ready()
PY
fi

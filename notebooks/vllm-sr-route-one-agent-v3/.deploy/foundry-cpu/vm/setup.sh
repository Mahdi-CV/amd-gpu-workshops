#!/usr/bin/env bash
# vLLM-SR workshop on a CPU-only lab VM: model lanes on Azure Foundry, d3-lite routing on the CPU.
# Run with: bash ~/setup.sh   (FOUNDRY_ENDPOINT and FOUNDRY_API_KEY must be set)
set -euo pipefail

# The workshop image (Router, Dashboard, d3-lite + vela3-fast, relay, JupyterLab, Hermes).
# Pulled only when it is not on this machine yet.
IMAGE='mahatri/vllm-sr-agent-workshop:v5-foundry-cpu-d3'
# Notebook files come from this branch (or a tag: REF=tags/<name>); if GitHub is unreachable,
# the container uses the copy shipped in the image.
OWNER='Mahdi-CV'; REPO='amd-gpu-workshops'
REF="${REF:-heads/workshop/vllm-sr-route-one-agent-v3-foundry-cpu-d3}"
SUB='notebooks/vllm-sr-route-one-agent-v3'
DEST="$HOME/workshop"
MIN_FREE_GB=20   # the image is 9.9 GB

# Same Dashboard login on every VM; export either variable to override.
DASH_EMAIL="${DASHBOARD_ADMIN_EMAIL:-admin@workshop.local}"
DASH_PASS="${DASHBOARD_ADMIN_PASSWORD:-workshop2026}"

if [ -z "${FOUNDRY_ENDPOINT:-}" ] || [ -z "${FOUNDRY_API_KEY:-}" ]; then
  echo "Set FOUNDRY_ENDPOINT and FOUNDRY_API_KEY (from the lab instructions panel) first"; exit 1
fi

echo "== machine"
lsb_release -ds 2>/dev/null || true
echo "CPU: $(lscpu | sed -n 's/^Model name:[[:space:]]*//p')  x$(nproc)   RAM: $(free -g | awk '/Mem:/{print $2}') GB"

# 1. Docker installed and usable?
if ! command -v docker >/dev/null; then
  echo "== installing docker"
  sudo apt-get update -y
  sudo apt-get install -y docker.io
  sudo systemctl enable --now docker
fi
DOCKER=docker
if ! docker info >/dev/null 2>&1; then
  sudo systemctl start docker 2>/dev/null || true
  if sudo docker info >/dev/null 2>&1; then DOCKER='sudo docker'; else
    echo "Docker is installed but not responding"; exit 1; fi
fi
$DOCKER version --format 'Docker {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'

# 2. Pull the image, unless it is already here
if $DOCKER image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "== image already present"
else
  ROOT=$($DOCKER info -f '{{.DockerRootDir}}')
  FREE=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc 0-9)
  echo "== free on $ROOT: ${FREE} GB (need ${MIN_FREE_GB})"
  if [ "$FREE" -lt "$MIN_FREE_GB" ]; then
    echo "Not enough disk for the image; stopping before the pull."; df -h; exit 1
  fi
  echo "== pulling $IMAGE"
  $DOCKER pull "$IMAGE"
fi

# 3. Notebook files, once: a rerun keeps the student's edits.
if [ -f "$DEST/workshop_lab.py" ]; then
  echo "== workshop files already present, keeping them: $DEST"
else
  mkdir -p "$DEST"
  TMP=$(mktemp -d)
  if curl -fsSL "https://codeload.github.com/$OWNER/$REPO/tar.gz/refs/$REF" | tar -xz -C "$TMP" 2>/dev/null \
     && [ -f "$TMP"/*/"$SUB"/workshop_lab.py ]; then
    cp -r "$TMP"/*/"$SUB"/route-one-agent-across-two-models-v3.ipynb \
          "$TMP"/*/"$SUB"/workshop_lab.py "$TMP"/*/"$SUB"/agent-demo "$DEST"/
    echo "== workshop files from GitHub ($REF)"
  else
    echo "== GitHub unreachable; the container will use the copy in the image"
  fi
  rm -rf "$TMP"
fi

# 4. The workshop container. Host networking: everything listens on this VM's 127.0.0.1 only
#    (JupyterLab 8888, Dashboard 9000, routed API 8898, relay 8001/8002).
echo "== starting the workshop"
# Values are passed explicitly: `sudo docker -e NAME` would read sudo's (empty) environment.
ENVS=(-e "FOUNDRY_ENDPOINT=$FOUNDRY_ENDPOINT" -e "FOUNDRY_API_KEY=$FOUNDRY_API_KEY"
      -e "DASHBOARD_ADMIN_EMAIL=$DASH_EMAIL" -e "DASHBOARD_ADMIN_PASSWORD=$DASH_PASS")
for v in FOUNDRY_PATH ROUTINE_DEPLOYMENT REASONING_DEPLOYMENT; do
  if [ -n "${!v:-}" ]; then ENVS+=(-e "$v=${!v}"); fi
done
$DOCKER rm -f vllm-sr >/dev/null 2>&1 || true
$DOCKER run -d --name vllm-sr --network host "${ENVS[@]}" -v "$DEST:/workspace" "$IMAGE" >/dev/null

echo "== waiting for the Router (d3-lite loads on the CPU), Dashboard and JupyterLab"
ready=0
for _ in $(seq 1 300); do
  if $DOCKER exec vllm-sr sh -c 'curl -fsS -m 3 -o /dev/null http://127.0.0.1:8898/v1/models \
      && curl -fsS -m 3 -o /dev/null http://127.0.0.1:9000 \
      && curl -fsS -m 3 -o /dev/null http://127.0.0.1:8888/api/status' 2>/dev/null; then ready=1; break; fi
  if ! $DOCKER ps -q --filter name=^vllm-sr$ | grep -q .; then break; fi
  sleep 2
done
$DOCKER exec vllm-sr cat /workspace/logs/start-platform.log 2>/dev/null || $DOCKER logs --tail 20 vllm-sr
[ "$ready" = 1 ] || { echo "The workshop did not become ready; see the log above and: docker logs vllm-sr"; exit 1; }

echo "== relay check (one real call per model)"
for p in 8002 8001; do
  echo "port $p:"
  $DOCKER exec vllm-sr python3 -c "import json,urllib.request as u
r=u.Request('http://127.0.0.1:$p/v1/chat/completions',data=json.dumps({'messages':[{'role':'user','content':'Say OK'}],'max_tokens':8}).encode(),headers={'Content-Type':'application/json'})
try: print(u.urlopen(r,timeout=60).read()[:300].decode())
except Exception as e: print('FAILED:', e, getattr(e,'read',lambda:b'')()[:300])" || true
done

echo
echo "Open http://localhost:8888/lab in the browser on this VM."
echo "Dashboard: http://localhost:9000"
echo "Dashboard login: $DASH_EMAIL / $DASH_PASS"

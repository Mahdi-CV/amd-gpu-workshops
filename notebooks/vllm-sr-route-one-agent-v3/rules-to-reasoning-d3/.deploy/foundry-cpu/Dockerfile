# "From Rules to Reasoning" workshop: CPU-only lab VM, model lanes on Azure Foundry.
#
# One container: vLLM-SR Router (standalone gateway, d3-lite decision model on the CPU),
# Dashboard, Foundry relay, JupyterLab (ihighlight, bash terminals) and Hermes.
# Every input is pinned: images by digest, Python packages by version (requirements.lock),
# d3-lite by revision and per-file SHA-256.
#
# Build from the workshop folder:
# notebooks/vllm-sr-route-one-agent-v3/rules-to-reasoning-d3
#   bash .deploy/foundry-cpu/fetch-d3-lite.sh
#   docker build -f .deploy/foundry-cpu/Dockerfile -t <image> .

# vLLM-SR at commit 6b782822 (the CLI 0.5.0.dev20261110170302 runs exactly these images).
ARG ROUTER_IMAGE=ghcr.io/vllm-project/semantic-router/vllm-sr@sha256:e241c2b513f5d19fab5047464fe9d9f58f5afa1d1c3193e127a0f27e021c8059
ARG DASHBOARD_IMAGE=ghcr.io/vllm-project/semantic-router/dashboard@sha256:ef6b61cf3c53578af526b4e6c0d4be0bcafab375512b6e5d0c7749fa0e160c86

FROM ${DASHBOARD_IMAGE} AS dashboard

FROM ${ROUTER_IMAGE}
ARG ROUTER_IMAGE
ARG DASHBOARD_IMAGE
USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl git procps ripgrep tini \
    && rm -rf /var/lib/apt/lists/*

# Workshop Python environment: JupyterLab, Hermes, the vllm-sr CLI the notebook validates with.
COPY .deploy/foundry-cpu/requirements* /tmp/req/
RUN python3 -m venv /opt/workshop-venv \
    && /opt/workshop-venv/bin/pip install --no-cache-dir --upgrade "pip==26.3" \
    && if [ -f /tmp/req/requirements.lock ]; then \
         /opt/workshop-venv/bin/pip install --no-cache-dir -r /tmp/req/requirements.lock; \
       else \
         /opt/workshop-venv/bin/pip install --no-cache-dir -r /tmp/req/requirements.txt; \
       fi \
    && /opt/workshop-venv/bin/python3 -c 'import click, jinja2, pydantic, requests, yaml, cli, run_agent' \
    && rm -rf /tmp/req

# Dashboard backend and web UI (the binary only needs libc).
COPY --from=dashboard /usr/local/bin/dashboard-backend /usr/local/bin/dashboard-backend
COPY --from=dashboard /app/frontend /opt/vllm-sr-dashboard/frontend

# Decision model, served from this local path; the workshop never contacts
# Hugging Face at runtime.
COPY .deploy/foundry-cpu/models/d3-lite /opt/models/d3-lite

# JupyterLab terminals open a bash login shell instead of sh (dash).
RUN mkdir -p /opt/workshop-venv/etc/jupyter/jupyter_server_config.d \
    && printf '%s\n' '{"ServerApp": {"terminado_settings": {"shell_command": ["/bin/bash", "-l"]}}}' \
         > /opt/workshop-venv/etc/jupyter/jupyter_server_config.d/workshop-terminal-bash.json

# Workshop files: the notebook copy is the fallback when GitHub is unreachable
# at launch. Participant API helpers are defined visibly inside the notebook.
COPY rules-to-reasoning-with-vllm-sr.ipynb /opt/workshop/templates/
COPY .deploy/foundry-cpu/router-config.yaml /opt/workshop/config/router.yaml
COPY .deploy/foundry-cpu/foundry_proxy.py \
     .deploy/foundry-cpu/start-platform.sh \
     .deploy/foundry-cpu/start-workshop.sh \
     .deploy/bin/verify-notebook-e2e.py \
     /opt/workshop/bin/
RUN chmod +x /opt/workshop/bin/*.sh \
    && mkdir -p /workspace \
    && printf '%s\n' "ROUTER_IMAGE=${ROUTER_IMAGE}" "DASHBOARD_IMAGE=${DASHBOARD_IMAGE}" \
         "D3_LITE=vllm-sr/d3-lite@a8d25a91ef75552803f7009d25b7bd435991abd9" \
         > /opt/workshop/versions.env

ENV PATH="/opt/workshop-venv/bin:${PATH}" \
    SHELL=/bin/bash \
    HF_HUB_OFFLINE=1 \
    VLLM_SR_WORKSHOP_DIR=/workspace/generated-config \
    ROUTER_CONFIG_PATH=/workspace/generated-config/router.yaml \
    VLLM_SR_START_PLATFORM_SCRIPT=/opt/workshop/bin/start-platform.sh \
    ROUTER_API=http://127.0.0.1:8898 \
    ROUTER_MANAGEMENT_API=http://127.0.0.1:8080 \
    DASHBOARD_URL=http://127.0.0.1:9000 \
    DASHBOARD_BROWSER_URL=http://localhost:9000 \
    DECISION_MODEL_ENDPOINT=http://127.0.0.1:8100 \
    ROUTINE_ENDPOINT=http://127.0.0.1:8002 \
    REASONING_ENDPOINT=http://127.0.0.1:8001 \
    ROUTINE_PROVIDER_MODEL=FW-Qwen3.8-27B \
    REASONING_PROVIDER_MODEL=FW-GLM-5.3-Flash

LABEL org.opencontainers.image.title="From Rules to Reasoning workshop (CPU, Azure Foundry, D3 Lite)" \
      ai.vllm.semantic-router.router-image="${ROUTER_IMAGE}" \
      ai.vllm.semantic-router.dashboard-image="${DASHBOARD_IMAGE}" \
      ai.vllm.semantic-router.decision-model="vllm-sr/d3-lite@a8d25a91ef75552803f7009d25b7bd435991abd9"

WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/workshop/bin/start-workshop.sh"]

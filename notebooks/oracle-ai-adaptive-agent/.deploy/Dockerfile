# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:24.16.0-bookworm-slim
ARG BASE_IMAGE=rocm@sha256:81cb82398fd6f1c0d2fff67fd7629867814fdeca5f192119e41024a15eb5bd9d

FROM ${NODE_IMAGE} AS openclaw

ARG OPENCLAW_VERSION=2026.10.4

RUN npm install --global --omit=dev --no-audit --no-fund \
      "openclaw@${OPENCLAW_VERSION}" \
    && test "$(node --version)" = "v24.16.0" \
    && openclaw --version | grep -F "${OPENCLAW_VERSION}" \
    && npm cache clean --force

FROM ${BASE_IMAGE} AS runtime

ARG BASE_IMAGE
ARG NODE_IMAGE
ARG OPENCLAW_VERSION=2026.10.4
ARG SOURCE_REVISION=unavailable
ARG WORKSHOP_UID=1000
ARG WORKSHOP_GID=1000

LABEL org.opencontainers.image.title="OpenClaw vLLM-SR Workshop" \
      org.opencontainers.image.description="CPU-only OpenClaw and vLLM Semantic Router workshop" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      ai.openclaw.version="${OPENCLAW_VERSION}" \
      ai.openclaw.node-image="${NODE_IMAGE}"

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      gosu \
      jq \
      procps \
      python3 \
      python3-pip \
      python3-venv \
      ripgrep \
      tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=openclaw /usr/local/bin/ /usr/local/bin/
COPY --from=openclaw /usr/local/lib/node_modules/ /usr/local/lib/node_modules/

COPY .deploy/requirements.lock /tmp/workshop-requirements.lock
RUN python3 -m venv /opt/workshop-venv \
    && /opt/workshop-venv/bin/pip install --no-cache-dir \
      -r /tmp/workshop-requirements.lock \
    && /opt/workshop-venv/bin/python -c \
      "import aiohttp, ipykernel, jupyterlab, psutil, pytest, readchar, requests, rich, typer" \
    && rm /tmp/workshop-requirements.lock

RUN groupadd --gid "${WORKSHOP_GID}" workshop \
    && useradd \
      --uid "${WORKSHOP_UID}" \
      --gid "${WORKSHOP_GID}" \
      --create-home \
      --home-dir /home/workshop \
      --shell /bin/bash \
      workshop

WORKDIR /opt/workshop
COPY workshop.ipynb openclaw-multi-agent-workshop.ipynb README.md /opt/workshop/
COPY .deploy/bin/ /opt/workshop/.deploy/bin/
COPY .deploy/lib/ /opt/workshop/.deploy/lib/
COPY .deploy/tests/ /opt/workshop/.deploy/tests/
COPY .deploy/router/ /opt/workshop/.deploy/router/
COPY .deploy/fixture/ /opt/workshop/.deploy/fixture/
COPY .deploy/artifacts/ /opt/workshop/.deploy/artifacts/
COPY .deploy/config/ /opt/workshop/.deploy/config/
COPY .deploy/secrets/README.md /opt/workshop/.deploy/secrets/README.md
COPY .deploy/*.py .deploy/*.md .deploy/requirements.lock /opt/workshop/.deploy/

RUN find /opt/workshop -type d -name __pycache__ -prune -exec rm -rf {} + \
    && install -d -o workshop -g workshop \
      /workspace \
      /workspace/agents \
      /workspace/demo \
      /workspace/notebooks \
      /workspace/results \
      /workspace/runtime \
      /workspace/state \
      /home/workshop/.cache \
      /home/workshop/.local \
    && find /opt/workshop/.deploy/bin -maxdepth 1 -type f \
      \( -name "*.sh" -o -name "*.py" \) -exec chmod 0755 {} + \
    && ln -s /opt/workshop/.deploy/bin/workshop-status.sh \
      /usr/local/bin/workshop-status \
    && ln -s /opt/workshop/.deploy/bin/workshop-reset.sh \
      /usr/local/bin/workshop-reset \
    && ln -s /opt/workshop/.deploy/bin/verify-image.sh \
      /usr/local/bin/workshop-verify-image \
    && if [[ -f /opt/workshop/.deploy/bin/verify-e2e.py ]]; then \
         ln -s /opt/workshop/.deploy/bin/verify-e2e.py \
           /usr/local/bin/workshop-verify-e2e; \
       fi \
    && if [[ -f /opt/workshop/.deploy/bin/compare-policies.py ]]; then \
         ln -s /opt/workshop/.deploy/bin/compare-policies.py \
           /usr/local/bin/workshop-compare; \
       fi \
    && if [[ -f /opt/workshop/.deploy/bin/analyze-policy-results.py ]]; then \
         ln -s /opt/workshop/.deploy/bin/analyze-policy-results.py \
           /usr/local/bin/workshop-analyze-results; \
       fi

ENV PATH="/opt/workshop-venv/bin:/usr/local/bin:${PATH}" \
    HOME="/home/workshop" \
    PYTHONPATH="/opt/workshop/.deploy/lib" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1" \
    PIP_DISABLE_PIP_VERSION_CHECK="1" \
    WORKSHOP_ROOT="/opt/workshop" \
    WORKSHOP_WORKSPACE="/workspace" \
    WORKSHOP_RESULTS_DIR="/workspace/results" \
    WORKSHOP_RUNTIME_DIR="/workspace/runtime" \
    OPENCLAW_STATE_DIR="/workspace/state/openclaw" \
    OPENCLAW_WORKSHOP_STATE_DIR="/workspace/state/openclaw" \
    OPENCLAW_WORKSHOP_WORKSPACES="/workspace/agents" \
    OPENCLAW_WORKSHOP_DEMO_ROOT="/workspace/demo" \
    CUDA_VISIBLE_DEVICES="-1" \
    HIP_VISIBLE_DEVICES="-1" \
    HSA_VISIBLE_DEVICES="-1" \
    NVIDIA_VISIBLE_DEVICES="-1" \
    ROCR_VISIBLE_DEVICES="-1" \
    GPU_DEVICE_ORDINAL="-1"

EXPOSE 8888
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=8 \
  CMD curl --fail --silent --show-error --max-time 2 \
      http://127.0.0.1:19090/readyz >/dev/null \
      && python -c \
      'import socket; s=socket.create_connection(("127.0.0.1", 8888), 2); s.close()'

WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/workshop/.deploy/bin/container-entrypoint.sh"]
CMD []

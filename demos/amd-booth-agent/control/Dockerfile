# syntax=docker/dockerfile:1.7

FROM node:24.16.0-bookworm-slim

ARG OPENCLAW_VERSION=2026.10.4
ARG BOOTH_UID=1000
ARG BOOTH_GID=1000

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN npm install --global --omit=dev --no-audit --no-fund \
      "openclaw@${OPENCLAW_VERSION}" \
    && openclaw --version | grep -F "${OPENCLAW_VERSION}" \
    && npm cache clean --force

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      chromium \
      curl \
      fonts-dejavu-core \
      git \
      gosu \
      jq \
      procps \
      python3 \
      python3-pip \
      python3-venv \
      tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/booth-venv \
    && /opt/booth-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

RUN groupadd --gid "${BOOTH_GID}" booth \
    && useradd \
      --uid "${BOOTH_UID}" \
      --gid "${BOOTH_GID}" \
      --create-home \
      --home-dir /home/booth \
      --shell /bin/bash \
      booth

WORKDIR /opt/booth
COPY app.py bootstrap_openclaw.py entrypoint.sh /opt/booth/
COPY templates/ /opt/booth/templates/
COPY static/ /opt/booth/static/
COPY fixtures/ /opt/booth/fixtures/

RUN chmod 0755 /opt/booth/entrypoint.sh \
    && install -d -o booth -g booth \
      /data \
      /data/agents \
      /data/openclaw \
      /data/runs \
      /home/booth/.cache \
      /home/booth/.config \
      /home/booth/.local

ENV PATH="/opt/booth-venv/bin:/usr/local/bin:${PATH}" \
    HOME="/home/booth" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    BOOTH_DATA_DIR="/data" \
    BOOTH_RUNS_DIR="/data/runs" \
    OPENCLAW_STATE_DIR="/data/openclaw" \
    OPENCLAW_WORKSPACES="/data/agents" \
    ROUTER_BASE_URL="http://router:8899/v1" \
    ROUTER_MODEL="vllm-sr/auto" \
    BROWSER_EXECUTABLE_PATH="/usr/bin/chromium"

EXPOSE 8088
STOPSIGNAL SIGTERM

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/booth/entrypoint.sh"]

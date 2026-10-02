# syntax=docker/dockerfile:1.7

ARG VLLM_BASE_IMAGE
ARG VLLM_SR_IMAGE
ARG DASHBOARD_IMAGE
ARG VLLM_SR_CONTRACT_REVISION
ARG VLLM_SR_PYTHON_REVISION
ARG ALLOW_UNPINNED_IMAGES=0

FROM ${VLLM_SR_IMAGE} AS router
FROM ${DASHBOARD_IMAGE} AS dashboard
FROM envoyproxy/envoy:v1.34-latest AS envoy

FROM ${VLLM_BASE_IMAGE}

ARG SOURCE_REVISION=unavailable
ARG VLLM_BASE_IMAGE
ARG VLLM_SR_IMAGE
ARG DASHBOARD_IMAGE
ARG VLLM_SR_CONTRACT_REVISION
ARG VLLM_SR_PYTHON_SPEC
ARG VLLM_SR_PYTHON_REVISION
ARG ALLOW_UNPINNED_IMAGES

LABEL org.opencontainers.image.title="vLLM-SR Route One Agent Workshop"
LABEL org.opencontainers.image.revision="${SOURCE_REVISION}"
LABEL ai.vllm.semantic-router.revision="${VLLM_SR_CONTRACT_REVISION}"
LABEL ai.vllm.semantic-router.python-revision="${VLLM_SR_PYTHON_REVISION}"
LABEL ai.vllm.semantic-router.router-image="${VLLM_SR_IMAGE}"
LABEL ai.vllm.semantic-router.dashboard-image="${DASHBOARD_IMAGE}"

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        cmake \
        curl \
        git \
        patch \
        procps \
        ripgrep \
        tini \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY .deploy/vllm_sr-0.3.0-py3-none-any.whl /tmp/vllm_sr-0.3.0-py3-none-any.whl
RUN python3 -m venv /opt/workshop-venv \
    && /opt/workshop-venv/bin/pip install --no-cache-dir --upgrade pip \
    && test -n "${VLLM_SR_CONTRACT_REVISION}" \
    && test -n "${VLLM_SR_PYTHON_REVISION}" \
    && test "${VLLM_SR_CONTRACT_REVISION}" = "${VLLM_SR_PYTHON_REVISION}" \
    && if [ "${ALLOW_UNPINNED_IMAGES}" != "1" ]; then \
         case "${VLLM_BASE_IMAGE}" in *@sha256:*) ;; *) echo "VLLM_BASE_IMAGE must use an immutable digest" >&2; exit 1;; esac; \
         case "${VLLM_SR_IMAGE}" in *@sha256:*) ;; *) echo "VLLM_SR_IMAGE must use an immutable digest" >&2; exit 1;; esac; \
         case "${DASHBOARD_IMAGE}" in *@sha256:*) ;; *) echo "DASHBOARD_IMAGE must use an immutable digest" >&2; exit 1;; esac; \
       fi \
    && /opt/workshop-venv/bin/pip install --no-cache-dir \
        /tmp/vllm_sr-0.3.0-py3-none-any.whl \
    && rm /tmp/vllm_sr-0.3.0-py3-none-any.whl

COPY .deploy/requirements.txt /tmp/workshop-requirements.txt
RUN /opt/workshop-venv/bin/pip install --no-cache-dir --ignore-requires-python \
      -r /tmp/workshop-requirements.txt \
    && /opt/workshop-venv/bin/python3 -c \
      'import click, jinja2, jsonschema, pydantic, requests, yaml; import cli.commands.runtime_support' \
    && rm /tmp/workshop-requirements.txt

COPY --from=router /usr/local/bin/router /usr/local/bin/router
COPY --from=router /usr/local/lib/libcandle_semantic_router.so /usr/local/lib/
COPY --from=router /usr/local/lib/libnlp_binding.so /usr/local/lib/
COPY --from=router /usr/local/lib/libonnx_semantic_router.so /usr/local/lib/
COPY --from=router /usr/local/lib/libml_semantic_router.so /usr/local/lib/
COPY --from=router /usr/local/lib/libonnxruntime_providers_shared.so /usr/local/lib/
COPY --from=router /usr/local/lib/libonnxruntime.so.1.22.0 /usr/local/lib/
RUN ldconfig
COPY --from=dashboard /app/dashboard-backend /opt/vllm-sr/dashboard-backend
COPY --from=dashboard /app/frontend /opt/vllm-sr/frontend
COPY --from=envoy /usr/local/bin/envoy /usr/local/bin/envoy

# Radeon Cloud: proxy-aware dashboard frontend for jupyter-server-proxy
# index.html lives in .deploy/ so it is hidden from notebook users.
# It includes the __vsr_subpath_shim marker so start-platform.sh skips
# its own Instinct-style patching.
COPY .deploy/index.html /opt/vllm-sr/frontend/index.html
COPY .deploy/dashboard_auth_proxy.py /opt/workshop/bin/dashboard_auth_proxy.py
COPY .deploy/openai_proxy.py /opt/workshop/bin/openai_proxy.py

RUN printf '%s\n' \
      "VLLM_SR_CONTRACT_REVISION=${VLLM_SR_CONTRACT_REVISION}" \
      "VLLM_SR_PYTHON_SPEC=${VLLM_SR_PYTHON_SPEC}" \
      "VLLM_SR_PYTHON_REVISION=${VLLM_SR_PYTHON_REVISION}" \
      "VLLM_BASE_IMAGE=${VLLM_BASE_IMAGE}" \
      "VLLM_SR_IMAGE=${VLLM_SR_IMAGE}" \
      "DASHBOARD_IMAGE=${DASHBOARD_IMAGE}" \
      > /opt/vllm-sr-contract.env

COPY .deploy /opt/workshop/deploy
COPY route-one-agent-across-two-models-v3.ipynb /opt/workshop/templates/
COPY workshop_lab.py /opt/workshop/templates/
COPY agent-demo /opt/workshop/templates/agent-demo

RUN mkdir -p \
      /opt/workshop/bin \
      /opt/workshop/config \
      /opt/workshop/patches \
      /workspace \
      /workspace/generated-config \
      /workspace/logs \
      /workspace/state \
      /models \
    && cp /opt/workshop/deploy/bin/*.sh /opt/workshop/bin/ \
    && cp /opt/workshop/deploy/config/* /opt/workshop/config/ \
    && cp /opt/workshop/deploy/patches/* /opt/workshop/patches/ \
    && chmod +x /opt/workshop/bin/*.sh \
    && SITE_PACKAGES=$(/opt/workshop-venv/bin/python3 -c \
      'import site; print(site.getsitepackages()[0])') \
    && patch -p1 -d "${SITE_PACKAGES}" \
      < /opt/workshop/patches/hermes-agent-0.19-vsr-message-name.patch

ENV PATH="/opt/workshop-venv/bin:${PATH}" \
    HF_HOME="/root/.cache/huggingface" \
    HERMES_HOME="/workspace/state/hermes" \
    VLLM_SR_WORKSHOP_DIR="/workspace/generated-config" \
    ROUTINE_ENDPOINT="http://127.0.0.1:8002" \
    REASONING_ENDPOINT="http://127.0.0.1:8001" \
    ROUTER_MANAGEMENT_API="http://127.0.0.1:8080" \
    ROUTER_API="http://127.0.0.1:8898" \
    DASHBOARD_URL="http://127.0.0.1:9000" \
    ROUTER_CONFIG_PATH="/workspace/generated-config/router.yaml" \
    VLLM_SR_SOURCE_CONFIG_PATH="/workspace/generated-config/router.yaml" \
    VLLM_SR_RUNTIME_CONFIG_PATH="/workspace/generated-config/router.yaml" \
    ROUTINE_PROVIDER_MODEL="gemma-4-12b" \
    REASONING_PROVIDER_MODEL="qwen3.8-27b" \
    VLLM_ROCM_USE_AITER="1" \
    VLLM_ROCM_USE_AITER_FUSION_SHARED_EXPERTS="1"

# Build llama.cpp with ROCm/HIP support for llama-server
# AMDGPU_TARGETS must match the GPU: gfx1100 = Radeon PRO W7900 (RDNA3)
# Clone BEFORE git-wrapper replaces /usr/local/bin/git so we use real git.
ARG LLAMA_CPP_TAG=v0.5.0
ARG AMDGPU_TARGETS=gfx1100
RUN GIT_SSL_NO_VERIFY=true git clone --depth 1 --branch "${LLAMA_CPP_TAG}" \
      https://github.com/ggml-org/llama.cpp.git /usr/local/bin/llama.cpp \
    && cmake -B /usr/local/bin/llama.cpp/build \
        -S /usr/local/bin/llama.cpp \
        -DGGML_HIP=ON \
        -DAMDGPU_TARGETS="${AMDGPU_TARGETS}" \
        -DLLAMA_CURL=OFF \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /usr/local/bin/llama.cpp/build \
        --target llama-server \
        --config Release \
        -j"$(nproc)" \
    && /usr/local/bin/llama.cpp/build/bin/llama-server --version

COPY .deploy/git-wrapper /usr/local/bin/git
RUN chmod +x /usr/local/bin/git && /usr/local/bin/git --version
ENV GH_PROXY_PREFIX="https://gh-test.anruicloud.com/"

EXPOSE 8888 9000 9001

WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/workshop/bin/entrypoint.sh"]

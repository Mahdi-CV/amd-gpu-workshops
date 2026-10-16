#!/usr/bin/env bash
set -euo pipefail

contract=/opt/vllm-sr-contract.env
workspace=${WORKSHOP_VERIFY_WORKSPACE:-/workspace}

if [[ ! -f "${contract}" ]]; then
  echo "Missing image contract: ${contract}" >&2
  exit 1
fi

source "${contract}"

required=(
  VLLM_SR_CONTRACT_REVISION
  VLLM_SR_PYTHON_REVISION
  VLLM_SR_PYTHON_SPEC
  VLLM_BASE_IMAGE
  VLLM_SR_IMAGE
  DASHBOARD_IMAGE
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing ${name} in ${contract}" >&2
    exit 1
  fi
done

if [[ "${VLLM_SR_CONTRACT_REVISION}" != "${VLLM_SR_PYTHON_REVISION}" ]]; then
  echo "CLI and Router revisions differ:" >&2
  echo "  Router: ${VLLM_SR_CONTRACT_REVISION}" >&2
  echo "  CLI:    ${VLLM_SR_PYTHON_REVISION}" >&2
  exit 1
fi

expected_config_path=/workspace/generated-config/router.yaml
for name in \
  ROUTER_CONFIG_PATH \
  VLLM_SR_SOURCE_CONFIG_PATH \
  VLLM_SR_RUNTIME_CONFIG_PATH; do
  if [[ "${!name:-}" != "${expected_config_path}" ]]; then
    echo "${name} must be ${expected_config_path}, got ${!name:-<unset>}" >&2
    exit 1
  fi
done
echo "✓ Dashboard and Router config paths agree"

python3 - <<'PY'
import click
import jinja2
import jsonschema
import pydantic
import requests
import yaml
from cli.commands import runtime_support

print("✓ Python CLI runtime imports")
PY

if vllm-sr config validate --help >/dev/null 2>&1; then
  echo "✓ CLI command: vllm-sr config validate"
elif vllm-sr validate --help >/dev/null 2>&1; then
  echo "✓ CLI command: vllm-sr validate"
else
  echo "The installed CLI exposes no config validation command" >&2
  exit 1
fi

for path in \
  /usr/local/bin/router \
  /usr/local/lib/libcandle_semantic_router.so \
  /usr/local/lib/libnlp_binding.so \
  /usr/local/lib/libonnx_semantic_router.so \
  /usr/local/lib/libml_semantic_router.so; do
  if [[ ! -f "${path}" ]]; then
    echo "Missing Router runtime artifact: ${path}" >&2
    exit 1
  fi
done

if ldd /usr/local/bin/router | grep -q "not found"; then
  echo "Router has unresolved shared libraries:" >&2
  ldd /usr/local/bin/router >&2
  exit 1
fi
echo "✓ Router shared libraries"

mkdir -p "${workspace}/generated-config"
probe_dir=$(mktemp -d "${workspace}/generated-config/.atomic-write-XXXXXX")
trap 'rm -rf "${probe_dir}"' EXIT
printf 'probe\n' >"${probe_dir}/config.yaml.tmp"
mv "${probe_dir}/config.yaml.tmp" "${probe_dir}/config.yaml"
echo "✓ Workspace supports atomic config replacement"

echo
echo "Image contract:"
cat "${contract}"
echo
echo "Runtime SHA-256 fingerprints:"
sha256sum \
  /usr/local/bin/router \
  /usr/local/lib/libcandle_semantic_router.so \
  /usr/local/lib/libnlp_binding.so \
  /usr/local/lib/libonnx_semantic_router.so \
  /usr/local/lib/libml_semantic_router.so

#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${HERMES_HOME}"

hermes config set _config_version 33 >/dev/null
hermes config set model.provider custom >/dev/null
hermes config set model.default vllm-sr/auto >/dev/null
hermes config set model.base_url "${ROUTER_API}/v1" >/dev/null
hermes config set model.api_key no-key-required >/dev/null
hermes config set model.context_length 65536 >/dev/null
hermes config set model.max_tokens 4096 >/dev/null

hermes tools disable \
  web \
  browser \
  vision \
  image_gen \
  tts \
  skills \
  memory \
  session_search \
  clarify \
  delegation \
  cronjob \
  computer_use \
  >/dev/null

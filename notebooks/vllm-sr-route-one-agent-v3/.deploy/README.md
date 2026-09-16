# Hidden workshop deployment assets

Build from the workshop folder so the Dockerfile can copy the visible notebook
and helper:

```bash
docker build \
  -f .deploy/Dockerfile \
  --build-arg VLLM_BASE_IMAGE=vllm/vllm-openai-rocm:<validated-tag-or-digest> \
  --build-arg VLLM_SR_IMAGE=ghcr.io/vllm-project/semantic-router/vllm-sr:<same-revision-tag-or-digest> \
  --build-arg DASHBOARD_IMAGE=ghcr.io/vllm-project/semantic-router/dashboard:<same-revision-tag-or-digest> \
  --build-arg VLLM_SR_CONTRACT_REVISION=<semantic-router-git-sha> \
  --build-arg VLLM_SR_PYTHON_SPEC=<wheel-or-package-built-from-that-git-sha> \
  --build-arg SOURCE_REVISION=<immutable-source-revision> \
  -t vllm-sr-agent-workshop:<version> .
```

The CLI package, Router image, and Dashboard image must come from the same
Semantic Router revision. The Dockerfile deliberately has no independent
default CLI release: mixing `vllm-sr==0.3.0` with an unrelated Router binary
can make a configuration pass `vllm-sr validate` and then fail at Router
startup.

The built image records the selected contract in
`/opt/vllm-sr-contract.env`. Before publishing the workshop image, run the
notebook's schema and Router boot checks against every generated stage.

The image contains the software and workshop assets. Model weights are mounted
at runtime under `/models`; they are not copied into the image.

The participant receives one authenticated Jupyter URL. The event platform may
expose the Dashboard as a sibling route or URL, but participants are not asked
to manage Kubernetes resources, ports, or tunnels.

Before publishing an image, complete every check in
`../IMAGE-PLAN.md` from the collateral source and replace all example image
tags and model revisions with immutable values.

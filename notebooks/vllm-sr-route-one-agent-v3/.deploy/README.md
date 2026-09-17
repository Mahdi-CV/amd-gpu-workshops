# Workshop image build and release contract

This directory contains the hidden deployment assets for the
`vllm-sr-route-one-agent-v3` workshop.

Do not publish an image until its CLI, Router, Dashboard, model images, writable
workspace, and complete notebook flow have passed the checks below.

Presenter delivery instructions are in:

```text
.deploy/PRESENTER-GUIDE.md
```

## Kubernetes branch conventions

This branch runs Dashboard on container port `9000`. When Jupyter Server Proxy
provides browser access, use:

```text
DASHBOARD_URL=http://127.0.0.1:9000
DASHBOARD_BROWSER_URL=/proxy/9000/
```

If the event platform supplies a dedicated application URL, set
`DASHBOARD_BROWSER_URL` to that URL instead.

The Kubernetes manifest mounts the complete `/workspace` directory from one
writable `emptyDir`. Keep that directory mount. Do not replace it with a
single-file `subPath` mount for `router.yaml`.

Before building, choose and document one model-cache strategy:

- prewarmed PVC: set `HF_HOME` to the mounted cache path and ensure every model
  and Router classifier asset is present before the pod starts; or
- image-baked cache: keep `HF_HOME` at the baked cache path and remove the
  unused model-cache PVC from the manifest.

Do not publish a manifest that mounts `/models` while the image uses a
different undocumented cache location.

## 1. Build one coherent Semantic Router stack

Choose one immutable Semantic Router Git revision:

```bash
export VLLM_SR_REVISION=<full-semantic-router-git-sha>
```

Build or obtain all three artifacts from that revision:

```text
Router image
Dashboard image
vllm-sr Python wheel
```

Do not combine a Router from one commit with a PyPI release or wheel from
another commit. The workshop build now requires
`VLLM_SR_CONTRACT_REVISION` and `VLLM_SR_PYTHON_REVISION` to be equal.

An immutable internal wheel URL is preferred. A Git URL is also accepted:

```text
git+https://github.com/vllm-project/semantic-router.git@<full-sha>#subdirectory=src/vllm-sr
```

## 2. Use immutable image digests

Production builds require digest-pinned base, Router, and Dashboard images.
Mutable tags such as `latest` are rejected unless
`ALLOW_UNPINNED_IMAGES=1` is supplied explicitly for local development.

Build from the workshop folder:

```bash
docker build \
  -f .deploy/Dockerfile \
  --build-arg VLLM_BASE_IMAGE='<validated-vllm-rocm-image>@sha256:<digest>' \
  --build-arg VLLM_SR_IMAGE='ghcr.io/vllm-project/semantic-router/vllm-sr@sha256:<digest>' \
  --build-arg DASHBOARD_IMAGE='ghcr.io/vllm-project/semantic-router/dashboard@sha256:<digest>' \
  --build-arg VLLM_SR_CONTRACT_REVISION="${VLLM_SR_REVISION}" \
  --build-arg VLLM_SR_PYTHON_REVISION="${VLLM_SR_REVISION}" \
  --build-arg VLLM_SR_PYTHON_SPEC='<immutable-wheel-url-or-git-spec>' \
  --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  -t '<registry>/vllm-sr-agent-workshop:<version>' \
  .
```

The resulting image records all inputs in:

```text
/opt/vllm-sr-contract.env
```

### Validated Semantic Router inputs

The full image build and notebook acceptance run completed successfully with:

```text
VLLM_SR_CONTRACT_REVISION=c1e00bb0fada18b891cbe20afb663b201cad0cb6
VLLM_SR_PYTHON_REVISION=c1e00bb0fada18b891cbe20afb663b201cad0cb6
VLLM_SR_PYTHON_SPEC=git+https://github.com/vllm-project/semantic-router.git@c1e00bb0fada18b891cbe20afb663b201cad0cb6#subdirectory=src/vllm-sr
VLLM_SR_IMAGE=ghcr.io/vllm-project/semantic-router/vllm-sr@sha256:8f157696dc6d15862eda67908c06e1736a8ee57bdac0fb336f165a8ff8d1e916
DASHBOARD_IMAGE=ghcr.io/vllm-project/semantic-router/dashboard@sha256:0eda445f2af832f209df5963dd13370dcfa100da286cba3b5cffef0bdfc49d86
```

The Router image's embedded CLI source and the Dashboard image metadata both
match `c1e00bb0fada18b891cbe20afb663b201cad0cb6`.

The MI300 base used for the reference build was a local image. Replace
`VLLM_BASE_IMAGE` with the immutable digest of the ROCm/vLLM base published for
the Kubernetes environment.

## 3. Known invalid combination

Do not reproduce this previously deployed combination:

```text
VLLM_SR_CONTRACT_REVISION=502ac1ec62c111aa6c3db4cc00fc8348156b576b
VLLM_SR_PYTHON_SPEC=vllm-sr==0.3.0
```

The Python package is 726 commits newer than the declared Router revision.
That image exposed a CLI/Router schema disagreement around
`providers.defaults.default_model`.

The affected workshop image was:

```text
mahatri/vllm-sr-agent-workshop:v3
sha256:bc9f8212056d11bc16ffd4937e926b65740d1c6c1a34448ff35d7b3e40654ced
```

Treat that digest as rejected.

## 4. Reference-node compatibility fingerprints

The following artifact set completed the full workshop flow on the MI300X
reference node. This is a compatibility reference, not proof that the
upstream CLI/Router schema disagreement has been resolved.

```text
Router image:
ghcr.io/vllm-project/semantic-router/vllm-sr@sha256:8f157696dc6d15862eda67908c06e1736a8ee57bdac0fb336f165a8ff8d1e916

Dashboard image:
ghcr.io/vllm-project/semantic-router/dashboard@sha256:0eda445f2af832f209df5963dd13370dcfa100da286cba3b5cffef0bdfc49d86

CLI source:
c1e00bb0fada18b891cbe20afb663b201cad0cb6
```

Expected Router runtime MD5 fingerprints for that exact Router image:

```text
ef68a627bb059f8758b9e8d27169f181  /usr/local/bin/router
ffbb806ca422b96eb8879e009ca488a8  /usr/local/lib/libcandle_semantic_router.so
ad15e7e2ebef1d0f7fefbb2081cffbf6  /usr/local/lib/libnlp_binding.so
cd99e24493987a5468f795a9cd428a17  /usr/local/lib/libonnx_semantic_router.so
45bf71b731ffc1baec67842ea11a4ba1  /usr/local/lib/libml_semantic_router.so
99949f86ee8cbb9d98465fb68821717b  /usr/local/lib/libonnxruntime_providers_shared.so
2366f571bc9e209b75cf5f82d27cf86e  /usr/local/lib/libonnxruntime.so.1.22.0
```

Prefer the image digest and SHA-256 fingerprints emitted by
`verify-image.sh`; MD5 is included only for comparison with the existing
reference node.

## 5. Writable configuration requirement

Router and Dashboard configuration updates use atomic file replacement.
Therefore, mount a writable directory such as `/workspace`, not an individual
configuration file using `subPath` or a file bind mount.

Correct:

```yaml
volumeMounts:
  - name: workspace
    mountPath: /workspace
```

Incorrect:

```yaml
volumeMounts:
  - name: config
    mountPath: /workspace/generated-config/router.yaml
    subPath: router.yaml
```

The incorrect form fails during Deploy with errors similar to:

```text
rename config.yaml.tmp config.yaml: device or resource busy
```

The active source configuration, Dashboard `-config` path, and Router
`-config` path must all refer to the same writable file.

## 6. Verify the image before Kubernetes deployment

Run the built-in static/runtime contract check:

```bash
/opt/workshop/bin/verify-image.sh
```

It verifies:

- required provenance fields;
- CLI and Router revision equality;
- Python CLI runtime imports, including `pydantic` and `jsonschema`;
- Router binary and shared-library presence;
- shared-library linkage; and
- atomic file replacement under `/workspace/generated-config`.

Then start both vLLM servers and the platform:

```bash
/opt/workshop/bin/start-platform.sh
```

Require HTTP 200 from:

```text
routine model       http://127.0.0.1:8002/v1/models
reasoning model     http://127.0.0.1:8001/v1/models
routed endpoint     http://127.0.0.1:8898/v1/models
management API      http://127.0.0.1:8080/health
Dashboard           value of DASHBOARD_URL
Jupyter             http://127.0.0.1:8888/api
```

## 7. Full notebook acceptance test

Do not approve the image based only on health checks or
`vllm-sr validate`.

With both vLLM model servers and the workshop platform running, execute:

```bash
WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

This test temporarily deploys Stage 5 and a sample custom route. It restores
the baseline Router configuration in a `finally` block and writes the executed
notebook to:

```text
/workspace/state/acceptance/route-one-agent-e2e.executed.ipynb
```

Run the notebook from a clean kernel and verify:

1. Direct calls reach both vLLM backends.
2. Prompt routing produces routine, reasoning, and uncertain outcomes.
3. Hermes edits the visible `agent-demo/` project and reports `3 passed`.
4. The four-turn conversation selects routine, routine, reasoning, routine.
5. Every generated config passes CLI compatibility validation.
6. Every generated config reaches Router `startup_complete`.
7. Stage 5 is imported, compiled, and deployed through Dashboard.
8. `/api/v1/config/hash` reports identical source, generated, and active hashes.
9. The collision prompt selects `incident-fast-lane` and `routine-model`.
10. A completed custom route passes positive, negative, and collision checks.
11. Router Replay IDs appear and Insights contains the requests.
12. The baseline configuration is restored after testing.

Archive the executed notebook and the image contract with the release
artifacts.

## 8. Kubernetes release checks

After deployment, record:

```bash
kubectl get pod <pod-name> \
  -o jsonpath='{.spec.containers[0].image}{"\n"}'

kubectl get pod <pod-name> \
  -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
```

Inside the pod, record:

```bash
cat /opt/vllm-sr-contract.env
/opt/workshop/bin/verify-image.sh
sha256sum /usr/local/bin/router /usr/local/lib/lib*_semantic_router.so
```

The configured image and running `imageID` must be immutable and must match the
release record.

The participant receives one authenticated Jupyter URL. Model weights should
come from a prewarmed read-only PVC or node-local cache; do not copy model
weights into the workshop application layer unless the event explicitly
requires an offline image.

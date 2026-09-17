---
title: Single-MI300 Workshop Image and Kubernetes Lab Plan
description: Runtime contract for one prebuilt participant image containing vLLM, vLLM-SR, Dashboard, Hermes, Jupyter, and observability.
---

# Single-MI300 Workshop Image and Kubernetes Lab Plan

> Architecture plan for the new workshop. This does not replace the repository's
> production Helm or multi-container deployment guidance.

## Goal

Each participant receives one link to one isolated JupyterLab server. The
Jupyter server runs inside the participant's Kubernetes-managed workshop
container, which has:

- one AMD Instinct MI300 GPU;
- one prebuilt software image;
- two vLLM model-serving processes;
- vLLM Semantic Router and Envoy;
- Dashboard;
- Hermes Agent;
- JupyterLab;
- the telemetry services required by Dashboard Insights; and
- all workshop files.

The participant should not:

- install packages;
- clone repositories;
- run Docker inside Kubernetes;
- edit low-level environment variables;
- discover service addresses;
- configure Hermes; or
- troubleshoot process wiring during the workshop.

The participant-facing contract is:

```text
one link
→ one authenticated JupyterLab session
→ notebook + terminals + files + proxied workshop applications
```

Kubernetes, container addressing, Services, ingress, and GPU placement remain
instructor/platform implementation details.

## Important interpretation of “one image”

The image should contain all software, binaries, scripts, configuration
templates, and workshop assets.

Model weights should normally live in:

- a prewarmed read-only PVC;
- a node-local model cache; or
- an equivalent cluster-managed cache.

Baking both checkpoints into the application image makes the image unusually
large, slows scheduling and distribution, and couples software releases to
model revisions. If the event must operate without registry or model-hub
access, publish model weights as separately managed immutable artifacts and
mount them into the participant workload.

## One container, several supervised processes

The requested lab shape is one GPU-bearing container. It should not use
Docker-in-Docker.

The container runs:

```text
JupyterLab
routine vLLM server
reasoning vLLM server
Semantic Router
Envoy
Dashboard backend/frontend
Prometheus
optional Jaeger
```

Use a small process supervisor plus inspectable platform scripts that:

- starts services in dependency order;
- writes one log per service;
- exposes status and restart commands;
- propagates termination;
- marks readiness only when required services pass health checks; and
- never asks the Dashboard to create sibling containers.

Hermes runs on demand from the participant terminal rather than as a permanent
daemon.

## Base image

Use a pinned ROCm vLLM image compatible with the cluster's MI300 driver stack.

The workshop layer adds:

- a pinned vLLM-SR CLI and Router build;
- Envoy;
- Dashboard static assets and backend;
- Hermes Agent pinned to a tested commit or release;
- JupyterLab and the Python kernel;
- the minimal telemetry backend required by Dashboard Insights;
- the `workshop` controller;
- the workshop notebook;
- the exercise repository; and
- configuration templates.

Do not use mutable `latest` tags for the event image, vLLM base, Hermes source,
or model revisions.

## GPU allocation

The Kubernetes container requests and limits one AMD GPU using the resource
name installed by the cluster's AMD device plugin.

Example placeholder:

```yaml
resources:
  requests:
    amd.com/gpu: 1
  limits:
    amd.com/gpu: 1
```

Confirm the actual resource name in the target cluster before producing the
manifest.

Both vLLM processes see the same assigned device. Their combined allocations
must leave headroom for ROCm runtime overhead:

```text
routine model GPU memory utilization:   approximately 0.45
reasoning model GPU memory utilization: approximately 0.47
reserved headroom:                      approximately 0.08
```

These are starting values from the reference environment, not universal
settings. Run cold-start and concurrent-generation tests against the exact
MI300 SKU, vLLM version, checkpoint revisions, context lengths, and maximum
sequence counts used for the event.

The Router's internal classifiers should use CPU unless the tested image has
enough measured GPU headroom to place them on the MI300 without destabilizing
the two vLLM servers.

## Filesystem contract

```text
/opt/workshop/
  bin/
    status.sh
    start-platform.sh
    stop-platform.sh
    reset.sh
    route-counts.sh
  config/
    environment.env
    router-demo.yaml
    telemetry/
    hermes/
  notebooks/
    route-one-agent-across-two-models.ipynb
  fixtures/
    agent-demo/

/models/
  routine/
  reasoning/

/workspace/
  README-FIRST.md
  notebooks/
  agent-demo/
  reference/
  generated-config/
  logs/
  state/
```

Mount `/models` read-only. Give each participant a writable workspace volume
for notebooks, generated configs, logs, Hermes state, and the coding exercise.

## Hidden environment contract

The image owns these values:

```bash
ROUTINE_MODEL_PATH=/models/routine
REASONING_MODEL_PATH=/models/reasoning
ROUTINE_PROVIDER_MODEL=gemma-4-12b
REASONING_PROVIDER_MODEL=qwen3.8-27b

ROUTINE_ENDPOINT=http://127.0.0.1:8002
REASONING_ENDPOINT=http://127.0.0.1:8001
ROUTER_MANAGEMENT_API=http://127.0.0.1:8080
ROUTER_API=http://127.0.0.1:8898
DASHBOARD_URL=http://127.0.0.1:8700
PROMETHEUS_URL=http://127.0.0.1:9090

HERMES_BASE_URL=http://127.0.0.1:8898/v1
HERMES_MODEL=vllm-sr/auto
```

The participant runs `lab.start_platform()` in the first notebook code cell.
The helper returns immediately when the platform is healthy; otherwise it
invokes `/opt/workshop/bin/start-platform.sh`. The script reads this file and
passes values directly to each platform process. Environment variables are
documented but not typed during the workshop.

The model-serving variables are loaded into every Jupyter terminal through the
image's shell profile so participants can run the two real `vllm serve`
commands without manually exporting ROCm or cache settings.

## Hermes contract

Hermes supports custom OpenAI-compatible endpoints. Pin one tested Hermes
version or commit in the image and generate its configuration during image
build or first container startup.

Required values:

```text
provider: custom OpenAI-compatible endpoint
base URL: http://127.0.0.1:8898/v1
model: vllm-sr/auto
API key: a non-secret workshop placeholder if Hermes requires one
context length: at least 64,000
maximum output tokens: 4,096 for the workshop task
```

Hermes has a hard 64K minimum context contract. Both vLLM servers in the event
image must genuinely expose at least that window. Do not declare 64K in Hermes
while launching a smaller backend.

Keep only the coding-task toolsets enabled:

```text
terminal
file
code_execution
todo
```

Install `pytest` and the required shell utilities in the image.

Hermes `0.19.0` tool-result messages include the optional OpenAI
`messages[].name` field, while the currently tested vLLM-SR protocol-neutral
contract rejects it. The workshop package contains a narrow compatibility patch
under:

```text
reference/hermes-agent-0.19-vsr-message-name.patch
```

The image build must apply and test that patch, or use a later compatible
Hermes/vLLM-SR pair where it is unnecessary.

Acceptance test:

1. Hermes sends a tool-bearing request to `vllm-sr/auto`.
2. The Router forwards the request to either backend.
3. The selected backend emits a valid tool call.
4. Hermes executes the tool.
5. Hermes sends the tool result in a later model request.
6. The Router can select a different model for that later request.
7. The task completes.

Because Hermes evolves independently, pin and test the exact CLI command shown
in the notebook. Do not invent a separate workshop agent CLI. If compatibility
glue is required, keep it to configuration generation during image startup.

## Dashboard contract

Run the Dashboard as a local process inside the participant container.

Configure:

```bash
ROUTER_CONFIG_PATH=/workspace/generated-config/router.yaml
DASHBOARD_CONFIG_DIR=/workspace/state/dashboard
TARGET_ROUTER_API_URL=http://127.0.0.1:8080
TARGET_ROUTER_METRICS_URL=http://127.0.0.1:9190
TARGET_ENVOY_URL=http://127.0.0.1:8898
TARGET_PROMETHEUS_URL=http://127.0.0.1:9090
TARGET_GRAFANA_URL=http://127.0.0.1:3000
```

The Dashboard must be tested in the single-process-namespace environment for:

- model and topology display;
- Playground requests;
- Insights/replay;
- configuration validation;
- creation of a draft policy;
- activation or export of the participant policy;
- authentication through the event's ingress or port-forward path.

Disable container-management features. The Dashboard must not require a Docker
or Podman socket in Kubernetes.

OpenClaw provisioning is not part of Workshop 1 and should be disabled unless a
later workshop explicitly tests it.

## Observability contract

The telemetry backend collects:

- Router metrics on `9190`;
- both vLLM servers;
- optional Envoy metrics; and
- workshop process health.

Dashboard Insights must show:

- requests by selected model;
- requests by selected decision;
- request latency;
- time to first token when available;
- prompt and completion tokens;
- backend errors; and
- model request counts before and after the Hermes task.

Grafana is optional instructor-only observability. It is not linked from the
participant notebook and is not required for completing the workshop.

The participant should not configure data sources or import dashboards.

## One-link browser experience

The event platform gives the participant only the Jupyter URL. From that page,
the participant opens:

```text
workshop notebook
Jupyter terminals
vLLM-SR Dashboard
exercise and reference files
```

Dashboard should be made available through Jupyter Server Proxy or an
equivalent event-platform reverse proxy:

```text
<jupyter-origin>/proxy/8700/  → Dashboard
```

The exact path is an implementation detail and must be generated into the
notebook rather than typed by the participant.

Before choosing Jupyter Server Proxy, test:

- Dashboard static assets through the prefix;
- Dashboard API requests;
- authentication cookies and CSRF;
- Insights and replay;
- Playground streaming;
- WebSocket behavior where used;
- links opened from notebook cells.

If either application is not prefix-safe, the event gateway should route
authenticated sibling paths or subdomains while preserving the one-link
participant entry experience.

Only Jupyter and its approved proxied application paths are browser-accessible.
Backend model ports, Router management, Prometheus, Router metrics, and internal
process-control endpoints remain private to the container.

Participants must never need:

- a raw public IP;
- an SSH tunnel;
- a Kubernetes Service name;
- a NodePort;
- `kubectl port-forward`; or
- a manually copied authentication token for a second application.

## Startup sequence

Container entrypoint:

1. validate GPU visibility;
2. validate model mounts;
3. materialize the participant workspace from read-only templates;
4. generate the Hermes configuration;
5. start JupyterLab;
6. register or configure the Dashboard proxy link;
7. start Dashboard in waiting/degraded mode; and
8. report ready for browser access.

Participant commands:

1. the displayed routine-model `vllm serve` command
2. the displayed reasoning-model `vllm serve` command
3. direct backend verification
4. the first notebook code cell, which runs `services = lab.start_platform()`

`start-platform.sh`:

1. waits for both backend health endpoints;
2. validates the Router configuration;
3. starts Router and waits for management health;
4. starts Envoy and waits for `/v1/models`;
5. starts the telemetry support required by Dashboard Insights;
6. verifies Dashboard dependencies;
7. verifies Hermes configuration; and
8. prints only the participant-facing URLs and readiness summary.

## Readiness probes

Kubernetes readiness should represent one-link browser-lab readiness, not model
readiness. Jupyter and the complementary workshop files can become ready before
the participant starts models.

The notebook helper and `/opt/workshop/bin/status.sh` separately report:

```text
jupyter
routine model
reasoning model
router
envoy
dashboard
prometheus
hermes configuration
```

This lets the workshop intentionally teach model startup without making the Pod
unready during that exercise.

## Image acceptance gate

Before the event, run at least:

1. cold Pod scheduling on an MI300 node;
2. Jupyter authentication and notebook/file visibility from the participant
   link;
3. Dashboard access starting from that same Jupyter session;
4. model-cache mount verification;
5. concurrent startup of both vLLM servers;
6. direct text generation from each model;
7. direct tool-call generation from each model;
8. base Router configuration validation;
9. easy prompt routing to the routine model;
10. hard prompt routing to the reasoning model;
11. Dashboard Playground and Insights through the participant access path;
12. Hermes multi-turn task completion;
13. evidence that both backends were used during the task;
14. guided incident-policy creation, collision testing, and activation;
15. participant-defined policy creation with positive, negative, and collision
    tests;
16. Dashboard model-count visualization;
17. notebook execution from first to last cell;
18. `/opt/workshop/bin/reset.sh` recovery; and
19. simultaneous multi-participant load at the expected event scale.

Record exact image digest, model revisions, GPU SKU, ROCm version, vLLM
version, vLLM-SR revision, Hermes revision, and measured startup time.

## Open decisions

- Exact MI300 SKU and allocatable memory.
- Exact routine and reasoning checkpoints.
- Whether model weights use a PVC, node-local cache, or offline artifact
  mount.
- Event authentication and the proxy mechanism used to expose Dashboard from
  the participant's Jupyter entry session.
- Whether configuration changes are activated live or exported and applied by
  `workshop`.
- Whether Jaeger adds enough workshop value to justify another process.
- Exact Hermes command and pinned revision after end-to-end validation.
- Whether participant state must survive Pod replacement.

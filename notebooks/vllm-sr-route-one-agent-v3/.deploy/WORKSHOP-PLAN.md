---
title: Route One Agent Across Two Models
description: An application-first vLLM Semantic Router workshop using a preinstalled Hermes Agent, two vLLM backends on one MI300, the Dashboard, and a participant routing challenge.
---

# Route One Agent Across Two Models

> New workshop draft. The existing workshop files remain unchanged and are
> retained as design references.

## The promise

In ninety minutes, each participant will:

1. start two models with vLLM;
2. send two requests through one vLLM-SR model name;
3. give one task to a preinstalled Hermes Agent;
4. watch different agent turns reach different models;
5. rebuild that behavior from the smallest Router configuration;
6. recognize the result as Select-mode Mixture-of-Models; and
7. implement and explain a new routing policy.

The participant does not install Python packages, clone repositories, configure
Hermes, wire service addresses, or launch infrastructure manually. Those are
properties of the workshop image.

## What the participant receives

Each participant receives one link. That link opens a private JupyterLab server
running inside the participant's workshop container.

The participant does not need to know the Kubernetes workload name, node,
container address, ingress rules, or internal service ports.

The Jupyter environment contains:

- exclusive access to one AMD Instinct MI300 GPU;
- vLLM with ROCm support;
- vLLM Semantic Router;
- Envoy;
- the vLLM-SR Dashboard;
- Hermes Agent;
- the observability support required by Dashboard Insights;
- two model checkpoints available through a mounted cache;
- workshop files and a small coding exercise repository; and
- a few inspectable setup and observability scripts.

The Jupyter file browser opens directly on:

```text
/workspace/
  README-FIRST.md
  route-one-agent-across-two-models.ipynb
  agent-demo/
  reference/
```

Jupyter provides:

- the workshop notebook;
- terminal tabs for starting models and running Hermes;
- all complementary files;
- a link that opens the vLLM-SR Dashboard through the participant's
  authenticated Jupyter access path; and
- generated configuration, logs, and exercise output.

The participant is never asked to browse a raw cluster IP, create an SSH
tunnel, run `kubectl port-forward`, or discover a service address.

Internally, the container still uses:

| Service | Internal port |
| --- | ---: |
| JupyterLab | `8888` |
| vLLM-SR Dashboard | `8700` |
| Routine vLLM backend | `8002` |
| Reasoning vLLM backend | `8001` |
| Router management API | `8080` |
| Routed OpenAI-compatible listener | `8898` |
| Router metrics | `9190` |
| Prometheus | `9090` |

## What is already configured

Hermes is installed and already points to:

```text
base URL: http://127.0.0.1:8898/v1
model:    vllm-sr/auto
```

The participant should not run a Hermes setup wizard. For this workshop,
Hermes has one job:

> Turn one user task into several model requests with tool calls between them.

The workshop image also provides:

```text
/opt/workshop/bin/status.sh
/opt/workshop/bin/start-platform.sh
/opt/workshop/bin/stop-platform.sh
/opt/workshop/bin/reset.sh
/opt/workshop/bin/route-counts.sh
```

These scripts hide platform wiring rather than model serving. Participants run
the two real `vllm serve` commands themselves.

---

# Workshop flow

## 0. Open the lab

Open the participant link. JupyterLab opens directly.

Read `README-FIRST.md`, then select:

```text
route-one-agent-across-two-models.ipynb
```

The notebook opens with the architecture and the two real `vllm serve`
commands. Health checks appear only after participants have launched those
commands.

No socket detection, package installation, service-address discovery, or
environment-variable setup appears before the model-launch experience.

The Dashboard link in the notebook must use the Jupyter server's proxied
application path or the workshop platform's equivalent same-session routing.
It must not show container ports or cluster addresses to the participant.

## 1. Start two models with vLLM

The instructor gives one sentence of context:

> We will use a smaller model for routine work and a stronger model for work
> that benefits from deeper reasoning.

Open two Jupyter terminals. ROCm variables and model-cache locations are
already configured by the image.

Terminal 1:

```bash
vllm serve google/gemma-4-12B-it \
  --host 0.0.0.0 \
  --port 8002 \
  --served-model-name gemma-4-12b \
  --gpu-memory-utilization 0.45 \
  --max-model-len 32768 \
  --max-num-seqs 16 \
  --enable-auto-tool-choice \
  --tool-call-parser gemma4
```

Terminal 2:

```bash
vllm serve Qwen/Qwen3.8-27B-FP8 \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name qwen3.8-27b \
  --gpu-memory-utilization 0.47 \
  --max-model-len 32768 \
  --max-num-seqs 16 \
  --enforce-eager \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

Participants see and run actual vLLM commands. The image hides only
event-specific environment and cache setup, which remains inspectable under:

```text
/opt/workshop/config/
```

Verify each model directly:

```bash
curl --fail http://127.0.0.1:8002/v1/models
curl --fail http://127.0.0.1:8001/v1/models
```

Then generate one short completion from each. Do not continue until direct
generation succeeds.

The notebook's first code cell loads the hidden environment helper, starts the
routing platform, and reports:

```text
GPU                  ready  AMD Instinct MI300
routine model        ready
reasoning model      ready
semantic router      ready
dashboard            ready
hermes               ready  model=vllm-sr/auto
```

## 2. Explain the running routing platform

The first notebook code cell runs:

```python
services = lab.start_platform()
services = lab.status()
```

The cell starts and wires:

- the Router;
- Envoy;
- Dashboard; and
- the storage and telemetry needed by Dashboard Insights.

It also:

- waits for both vLLM backends;
- validates the maintained workshop configuration;
- verifies `vllm-sr/auto` through the routed listener;
- confirms the Dashboard can reach Router, Envoy, and its Insights data; and
- confirms Hermes still targets `vllm-sr/auto`.

If the platform is already healthy, the cell reports that state without
restarting it. Otherwise, it invokes the inspectable
`/opt/workshop/bin/start-platform.sh` script and waits for readiness.

Participants do not need another terminal for this step.

Expected summary:

```text
✓ routine model        http://127.0.0.1:8002
✓ reasoning model      http://127.0.0.1:8001
✓ routed model         vllm-sr/auto
✓ dashboard            http://127.0.0.1:8700
✓ hermes               vllm-sr/auto
```

The hidden environment contract is documented for interested participants, but
the workshop does not make them type or export it.

## 3. Experience routing before learning its schema

Click **Open vLLM-SR Dashboard** in the notebook.

First show:

- the routine and reasoning models;
- the public `vllm-sr/auto` entrypoint; and
- the current two-lane topology.

Open Playground.

Easy prompt:

> Give me a short definition of HTTP.

Ask participants to note:

```text
selected decision
selected model
latency
```

Hard prompt:

> Diagnose the likely causes of cascading failures in a distributed queue,
> compare three remedies, and justify a rollout plan.

Compare the result.

Expected:

```text
easy → routine-traffic         → routine-model
hard → escalate-hard-prompts   → reasoning-model
```

Open the corresponding traces in Insights.

## 4. Prove that this is a normal application endpoint

Repeat both requests with the OpenAI-compatible API:

```bash
curl --include http://127.0.0.1:8898/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'x-vsr-debug: true' \
  -d '{
    "model": "vllm-sr/auto",
    "messages": [
      {"role": "user", "content": "Give me a short definition of HTTP."}
    ],
    "max_tokens": 80
  }'
```

The important observation is:

```text
same URL
+ same requested model
+ different request
= potentially different selected model
```

Playground is the convenient exploration interface. Applications use the
ordinary API.

## 5. Give one task to an agent

Introduce Hermes in one sentence:

> Hermes is the preinstalled agent harness we use to turn one task into several
> model calls and tool actions.

Do not teach Hermes installation, profiles, memory, providers, gateways, or its
larger feature set.

The image contains:

```text
/workspace/agent-demo/
  README.md
  pricing.py
  reporting.py
  test_pricing.py
```

The project has small, understandable duplicated logic and passing tests.

Record model request counts:

```bash
/opt/workshop/bin/route-counts.sh
```

Run one task:

```bash
cd /workspace/agent-demo

hermes -z \
  "Read this project and summarize what it does. Then solve this step by step: \
  compare at least three safe ways to remove the duplicated pricing logic, \
  explain their tradeoffs, choose the safest refactor, apply it, and run \
  python -m pytest -q." \
  --yolo
```

The exact command must be validated against the Hermes version pinned in the
image.

The pinned Hermes configuration and current vLLM-SR compatibility requirements
are documented in:

```text
reference/hermes-vsr-compatibility.md
```

The workshop narrative is:

```text
one user task
→ several agent turns
→ every turn requests vllm-sr/auto
→ different turns may select different models
```

Important precision:

> vLLM-SR does not switch models halfway through one inference request. Hermes
> turns one user task into several requests, and vLLM-SR routes each request.

After the task:

```bash
/opt/workshop/bin/route-counts.sh
```

Then inspect the run in Insights:

| Agent activity | Likely route |
| --- | --- |
| Inspect files | routine model |
| Summarize files | routine model |
| Design the refactor | reasoning model |
| Verify the result | routine model |

This is a prediction, not a promise. Participants compare it with the observed
trace.

## 6. Rebuild what just happened

Now say:

> You have seen the result in Playground, through curl, and inside an agent.
> Let’s rebuild the behavior from the smallest possible policy.

Create a new Dashboard draft rather than editing the working demonstration
route in place.

### 6.1 One model, no choice

```text
application → vllm-sr/auto → routine-model
```

Add:

- one model connection;
- one public entrypoint; and
- one catch-all decision.

Test both prompts. Both should use the routine model.

Reveal only the corresponding YAML fragment.

### 6.2 Connect the reasoning model

Add the second model, but do not change the decisions.

Test again. Both prompts should still use the routine model.

Lesson:

> Connected does not mean eligible.

### 6.3 Add the complexity signal

Add examples of easy and difficult work.

Inspect the signal output, but keep the current decision.

Lesson:

> A signal observes. It does not choose.

### 6.4 Add the reasoning decision

Policy:

```text
if complexity is hard:
    use reasoning-model
otherwise:
    use routine-model
```

Test both prompts again.

| Stage | Easy prompt | Hard prompt |
| --- | --- | --- |
| One model | routine | routine |
| Second model connected | routine | routine |
| Signal added | routine | routine |
| Decision added | routine | reasoning |

Only now introduce the names:

```text
signal → decision → algorithm → model
```

Explain priority and the match-all fallback from the behavior participants just
observed.

## 7. Make the Router fit an application

The first route answered the workshop's requirement:

```text
hard work → reasoning model
everything else → routine model
```

Real applications have different boundaries. Before the final challenge,
participants complete one guided customization so they learn the reusable
method rather than only copying the complexity example.

### 7.1 Start from a requirement, not a Router feature

Guided requirement:

> During an active production incident, acknowledgement speed is more important
> than deep analysis. Route incident-marked requests to the low-latency model,
> even when the prompt is otherwise complex.

Translate the requirement:

| Question | Answer |
| --- | --- |
| What matters? | The request identifies an active incident. |
| How can we observe it? | Exact incident keywords. |
| What should happen? | Use the routine, low-latency model. |
| What could also match? | Hard complexity. |
| Which policy must win? | The incident policy. |
| How will we prove it? | A collision prompt plus Insights. |

This becomes:

```text
requirement
→ keyword signal
→ higher-priority decision
→ routine model
→ test evidence
```

### 7.2 Add one signal in the Dashboard

Create:

```yaml
name: active-incident
operator: OR
keywords:
  - SEV-1
  - production outage
  - service unavailable
```

Explain only what the participant needs:

- the signal observes exact phrases;
- `OR` means any listed phrase is enough; and
- the signal does not select a model.

### 7.3 Add the application policy

Create:

```yaml
name: incident-fast-lane
priority: 300
condition:
  type: keyword
  name: active-incident
model:
  routine-model
```

The Dashboard exposes the actual canonical fields; the simplified fragment
above communicates the policy before showing the complete exported YAML.

Compare priorities:

```text
300  incident-fast-lane
200  reasoning-lane
100  routine fallback
```

### 7.4 Predict before testing

Collision prompt:

> SEV-1 production outage. Diagnose the root cause, compare three remediation
> plans, and recommend a rollout.

It should match:

```text
active-incident
request_complexity:hard
routine fallback
```

Ask participants to predict the winner before sending it.

Expected:

```text
selected decision: incident-fast-lane
selected model:    routine-model
reason:            priority 300 beats priority 200
```

Test in Playground, inspect Insights, and then repeat through the API.

### 7.5 Extract the reusable customization loop

Every custom route follows the same questions:

```text
1. What application behavior do I want?
2. What observable request property represents it?
3. Which signal should detect that property?
4. Which model paths are allowed?
5. Which rule wins when policies overlap?
6. What prompts prove both the positive and negative cases?
```

Participants should leave able to translate:

```text
application requirement
→ observable evidence
→ routing policy
→ measurable result
```

## 8. Recognize the larger Mixture-of-Models idea

Ask:

> What did we actually build?

Answer:

```text
one stable model identity
+ several independently deployed models
+ policy that chooses how a request is fulfilled
= Select-mode Mixture-of-Models
```

Clarify:

- Mixture-of-Experts routes inside one model.
- Mixture-of-Models coordinates separately deployed models.

Preview—but do not configure:

| Mode | What changes |
| --- | --- |
| Select | Choose one model |
| Cascade | Try one path and escalate |
| Fusion | Ask several models and synthesize |
| Workflow | Assign bounded model roles |

Workshop 2 starts from this point:

> Today the Router selected which model answered each request. In the next
> workshop, several models can participate in producing one answer.

## 9. Participant challenge

End with participants working, not listening.

The guided incident rule showed the mechanics. The challenge asks participants
to choose a requirement that resembles their own application.

Choose one:

### Coding specialist

```text
If the request asks for code review or debugging,
use the stronger model.
```

### Privacy boundary

```text
If the request contains sensitive data,
allow only the local model.
```

### Long-context lane

```text
If the request exceeds the routine model's safe context,
use the long-context-capable model.
```

### Conservative quality policy

```text
If complexity is medium or hard,
use the reasoning model.
```

### Participant-defined requirement

Write one routing requirement from your own application. The instructor checks
that it is observable and testable before implementation.

Participants must produce:

1. a one-sentence application requirement;
2. the signal or signals that represent it;
3. the decision and model assignment;
4. the intended priority relative to existing decisions;
5. one positive test that should match;
6. one negative test that should not match;
7. one collision test in which multiple policies match;
8. Playground or API results; and
9. an Insights trace explaining the winner.

The route is not complete merely because one demonstration prompt works.
Participants should explain:

- why they chose the signal;
- what false positive would look like;
- what false negative would look like;
- why the selected priority is correct; and
- whether an uncertain request should favor cost, latency, privacy, or quality.

Each participant finishes with:

```text
requirement
→ signal
→ decision
→ priority
→ model
→ test evidence
```

---

# Ninety-minute schedule

| Time | Section |
| ---: | --- |
| 5 min | Application problem and architecture |
| 10 min | Start and verify two vLLM backends |
| 10 min | Dashboard, Playground, and Insights |
| 8 min | Prove the OpenAI-compatible API |
| 15 min | One task through Hermes |
| 18 min | Rebuild the route incrementally |
| 9 min | Guided application-specific customization |
| 5 min | Select-mode MoM and Workshop 2 preview |
| 10 min | Participant-designed routing challenge |

The challenge can continue as a take-home exercise if the group needs more
time during model startup or agent execution.

# Workshop 2 handoff

Working title:

```text
Build a Mixture-of-Models with vLLM Semantic Router
```

It begins with the Select route from this workshop and adds:

- Recipe and Entrypoint assignment;
- confidence cascade;
- fusion;
- planner-worker-verifier workflow;
- objective-oriented public model names;
- quality, latency, and cost evaluation; and
- comparison with always-small, always-large, and Select baselines.

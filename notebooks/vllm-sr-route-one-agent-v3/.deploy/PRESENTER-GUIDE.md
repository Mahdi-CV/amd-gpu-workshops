# Presenter Guide: Route One Agent Across Two Models

This guide is for instructors delivering the vLLM Semantic Router workshop.
It is intentionally stored under `.deploy/` so it does not appear in the
participant Jupyter file browser.

Completed participant exercises and their verification steps are in the
[presenter solution key](SOLUTION-KEY.md).

## Workshop outcome

Participants should leave able to explain and demonstrate:

```text
application request
→ signal evidence
→ matching decisions
→ priority resolution
→ selected model
→ observable routing record
```

The workshop uses:

- two vLLM model endpoints on one AMD GPU;
- one application-facing model name, `vllm-sr/auto`;
- vLLM Semantic Router and Envoy;
- Dashboard Playground, Builder, and Insights;
- Hermes Agent;
- a visible Python refactoring exercise; and
- a staged Router configuration.

## Recommended presenter roles

For a room larger than 20 participants, use two presenters:

- Lead presenter: explains concepts and performs the main demonstration.
- Lab assistant: monitors chat, model startup, Dashboard access, and participant
  progress.

For a larger event, add one platform operator with Kubernetes access.

## Timing

The planned duration is 90 minutes.

| Segment | Minutes | Running total |
| --- | ---: | ---: |
| Welcome and goal | 5 | 5 |
| 1. Launch two model endpoints | 8 | 13 |
| 2. Start the prebuilt router | 4 | 17 |
| 3. Dashboard demo | 7 | 24 |
| 4. API prediction exercise | 8 | 32 |
| 5. Hermes Agent integration | 10 | 42 |
| 6. Multi-turn simulation | 7 | 49 |
| 7. Build the configuration | 20 | 69 |
| 8. Add and deploy an application rule | 12 | 81 |
| 9. Introduce Mixture of Models | 4 | 85 |
| 10. Custom policy challenge and close | 5 | 90 |

If model startup takes longer than planned, continue the explanation while the
servers initialize. Do not silently skip the direct-model checks.

## Presenter preflight

### One week before

1. Confirm the exact workshop image digest.
2. Confirm the GPU SKU and ROCm compatibility.
3. Confirm the model-cache strategy.
4. Confirm each participant receives one writable `/workspace`.
5. Confirm Dashboard browser routing:
   - Kubernetes branch: port `9000`, usually `/proxy/9000/`.
   - Reference node: port `8700`.
6. Run:

```bash
/opt/workshop/bin/verify-image.sh
```

7. Complete the automated notebook acceptance test:

```bash
WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

8. Archive:

```text
/opt/vllm-sr-contract.env
/workspace/state/acceptance/route-one-agent-e2e.executed.ipynb
the Kubernetes imageID
```

### Thirty minutes before

On the presenter pod:

```bash
/opt/workshop/bin/status.sh
```

Before participants start the model servers, the expected state is:

```text
routine model        not ready
reasoning model      not ready
semantic router      not ready
router management    not ready
dashboard            not ready
Hermes               ready
```

If the presenter wants to avoid waiting during the live demonstration, start
both model servers before the session and use a separate clean participant pod
to show the launch commands.

Verify the visible files:

```text
route-one-agent-across-two-models-v3.ipynb
workshop_lab.py
agent-demo/
```

Keep a clean executed acceptance notebook available as a fallback, but do not
show it unless the live environment fails.

## URLs

### Kubernetes participant environment

Jupyter is provided by the event platform.

Dashboard normally uses:

```text
/proxy/9000/
```

If the platform provides a separate application URL, use that instead.

### Reference node through SSH forwarding

```text
Jupyter:   http://localhost:8888
Dashboard: http://localhost:8700
```

Do not tell Kubernetes participants to use port `8700`.

## Presentation principles

1. Experience routing before explaining configuration.
2. Ask participants to predict before running a request.
3. Treat unexpected `medium` classifications as calibration evidence.
4. Do not call connected models replicas. They are separate model paths with
   different roles.
5. Do not imply that one Hermes tool loop must switch models.
6. Distinguish generating YAML from deploying an active policy.
7. Never use **Run All** for the participant notebook. Dashboard deployment and
   participant prompt edits occur between cells.
8. Do not expose model reasoning traces. Focus on routing evidence and final
   answers.

## Run of show

### Opening: one endpoint, two model paths

Show the diagram in the first notebook cell.

Say:

```text
The application will use one stable model name. vLLM Semantic Router decides
which separately deployed model should handle each request.
```

Do not begin with configuration terminology.

### Section 1: Launch Two Model Endpoints on an AMD GPU

Ask participants to open two Jupyter terminals.

Terminal 1 runs the routine model. Terminal 2 runs the reasoning model.

While the models start, highlight:

- model repository;
- `--served-model-name`;
- endpoint port;
- context length;
- GPU memory allocation;
- reasoning parser; and
- tool-call parser.

Expected readiness:

```text
routine    ['gemma-4-12b']
reasoning  ['qwen3.8-27b']
```

The direct reasoning readiness check disables thinking and should print:

```text
reasoning model ready
```

Presenter message:

```text
At this point there is no routing. We have verified two independent vLLM
backends.
```

### Section 2: Set Up vLLM Semantic Router with Two Models

Explain that the class will use a prebuilt policy before reconstructing it.

Say:

```text
We will use the working router first. In Section 7, we will rebuild the same
pattern from the smallest configuration.
```

Run:

```python
services = lab.start_platform()
```

Expected:

```text
semantic router     ready
router management   ready
dashboard           ready
```

### Section 3: vLLM Semantic Router Dashboard Demo

Open **Dashboard → Playground** and select `vllm-sr/auto`.

Routine control prompt:

```text
Give me a one-sentence definition of HTTP.
```

Expected:

```text
complexity: easy
decision: routine-traffic
model: routine-model
```

Reasoning prompt:

```text
Diagnose cascading failures in a distributed queue, compare multiple
remediation strategies and their tradeoffs, and justify a safe rollout plan.
```

Expected:

```text
complexity: hard
decision: escalate-hard-prompts
model: reasoning-model
```

Open **Build → Outcomes → Insights**. Under **Insight Records**, open the
newest records from **Routing Insights**.

Point out:

- user message;
- matched signal;
- decision;
- selected model;
- replay ID; and
- latency.

### Section 4: Test Routing Through the Application API

Have participants provide:

- one routine prompt;
- one reasoning-heavy prompt; and
- one uncertain prompt.

Do not provide all answers immediately. Ask for predictions first.

Expected control behavior:

| Prompt type | Likely result |
| --- | --- |
| Definition or rewrite | Easy, routine model |
| Diagnosis and tradeoff comparison | Hard, reasoning model |
| Short diagnostic suggestion | Medium, routine fallback |

Say:

```text
If the router disagrees with your prediction, keep the prompt. It is useful
calibration data.
```

### Section 5: Connect Hermes Agent to vLLM Semantic Router

Before running Hermes, open:

```text
agent-demo/pricing.py
agent-demo/test_pricing.py
```

Show the duplicated logic and the tests.

Run the Hermes setup and execution cells.

Success criteria:

```text
Hermes final response
3 passed
```

Say:

```text
This section proves that an existing tool-using agent can work through
vllm-sr/auto without knowing which backend model served the request.
```

Do not ask the room to count Hermes internal model calls. Insights inspection
is optional here.

### Section 6: vLLM Semantic Router Multi-Turn Simulation

Ask for a route prediction for all four turns before running the cell.

Expected sequence:

```text
routine
routine
reasoning
routine
```

Explain:

```text
The router evaluates the latest user message. The hard comparison turn
escalates, while the direct turns remain on the routine path.
```

### Section 7: Build the vLLM Semantic Router Configuration

Do not read the YAML line by line. Use the “Pay attention to” lists.

#### Stage 1

Highlight:

- listener;
- provider model;
- backend endpoint;
- model card;
- `vllm-sr/auto`;
- fallback decision;
- priority 100; and
- static algorithm.

Key statement:

```text
An empty AND condition is the fallback because there is nothing to reject.
```

#### Stage 2

Highlight:

- provider entry and model card are separate but share one logical name;
- `provider_model_id` matches the vLLM served name; and
- connecting a model does not make it selectable.

Key statement:

```text
Connected does not mean eligible.
```

#### Stage 3

Highlight:

- signal name;
- hard candidates;
- easy candidates; and
- threshold.

Write or show:

```text
margin = hard_score - easy_score
```

Explain:

```text
margin > threshold   means hard
margin < -threshold  means easy
otherwise            means medium
```

Tell participants to improve candidate examples before changing the threshold.

#### Stage 4

Highlight:

- condition type;
- exact signal result name;
- priority 200;
- reasoning model reference; and
- static algorithm.

Walk one hard request through signal, matching decisions, priority, algorithm,
and model.

### Section 8: Add an Application-Specific Routing Rule

Generate `05-incident-policy.yaml`.

Point out:

- keyword signal `active-incident`;
- case-insensitive keyword list;
- decision `incident-fast-lane`;
- priority 300; and
- `routine-model`.

Deploy with these exact steps:

1. Open `generated-config/05-incident-policy.yaml` in Jupyter.
2. Copy all YAML.
3. Open **Build → Builder**.
4. Select **Import**.
5. Paste the YAML.
6. Select **Import**.
7. Select **Compile**.
8. Confirm priority 300 and `routine-model`.
9. Select **Deploy**.

Before running the collision cell, verify active decisions if needed:

```bash
curl -s http://127.0.0.1:8080/api/v1/config \
  | python3 -c '
import json, sys
print([d["name"] for d in json.load(sys.stdin)["routing"]["decisions"]])
'
```

Expected:

```text
incident-fast-lane
reasoning-lane
routine-lane
```

Run the collision prompt.

Expected:

```text
complexity: hard
decision: incident-fast-lane
model: routine-model
```

Key statement:

```text
Both rules match. Priority 300 beats priority 200.
```

### Section 9: Introduce Select-Mode Mixture of Models

Keep this short.

Explain:

```text
Select mode chooses one separately deployed model for a request.
Mixture of Experts routes inside one model.
```

Preview Cascade, Fusion, and Workflow as follow-up material.

### Section 10: Build a Custom vLLM Semantic Router Policy

If time allows, give participants five minutes to define:

- one keyword signal;
- one decision;
- one priority;
- one positive prompt;
- one negative prompt; and
- one collision prompt.

If behind schedule, explain the challenge and assign it as follow-up work.

## Expected route reference

| Demonstration | Expected decision | Expected model |
| --- | --- | --- |
| HTTP definition | `routine-traffic` | `routine-model` |
| Hard distributed-queue diagnosis | `escalate-hard-prompts` | `reasoning-model` |
| Multi-turn comparison turn | `escalate-hard-prompts` | `reasoning-model` |
| Incident collision after deploy | `incident-fast-lane` | `routine-model` |
| Custom positive prompt | participant decision | participant model |
| Custom negative prompt | another decision | another model |

## Troubleshooting

### A model endpoint is not ready

Run:

```bash
curl -sS http://127.0.0.1:8002/v1/models
curl -sS http://127.0.0.1:8001/v1/models
```

Check the corresponding Jupyter terminal.

Do not restart both model servers if only one failed.

### Dashboard link returns 404

Inside Kubernetes, verify:

```bash
curl -I http://127.0.0.1:9000/
```

Then verify the browser URL uses:

```text
/proxy/9000/
```

Do not use `/proxy/8700/` on the Kubernetes branch.

### Dashboard page loads without application assets

Check:

```bash
cat /workspace/logs/dashboard.log
curl -I http://127.0.0.1:9000/
```

Confirm the pod is running the image digest approved during preflight.

### Dashboard Deploy fails

If the error contains:

```text
device or resource busy
```

the config is probably mounted as one file or Kubernetes `subPath`. The entire
`/workspace` directory must be writable.

Check:

```bash
/opt/workshop/bin/verify-image.sh
```

### Collision still selects the reasoning model

The generated file has not been deployed.

Check active decisions:

```bash
curl -s http://127.0.0.1:8080/api/v1/config \
  | python3 -c '
import json, sys
print([d["name"] for d in json.load(sys.stdin)["routing"]["decisions"]])
'
```

If `incident-fast-lane` is absent, repeat Import, Compile, and Deploy.

### Hermes takes too long

Allow at least one minute on the reference models. If it exceeds three minutes:

1. interrupt the cell;
2. rerun the setup cell to recreate the clean exercise;
3. check `/workspace/logs` and Hermes diagnostic output; and
4. continue with Section 6 if necessary.

The learning objective is application integration, not waiting for an
unbounded agent run.

### Hermes edits the wrong files

Confirm the working directory printed by the setup cell. It should end with:

```text
agent-demo-working
```

Rerun the setup cell to reset it.

### Reasoning route returns no final answer text

The notebook will display:

```text
[The model completed reasoning but did not return final answer text within
this response limit.]
```

The routing result is still valid. Focus on decision and selected model.

### Replay IDs are absent

Confirm Router Replay is enabled in the active configuration. Refresh
**Build → Outcomes → Insights** and inspect Router logs.

### Validation command differs

The image supports both:

```text
vllm-sr config validate
vllm-sr validate
```

The scripts automatically select the command exposed by the installed CLI.
If neither exists, the image is invalid.

## Reset between sessions

Stop model-server terminal processes with `Ctrl+C` if the next cohort should
launch them.

Then run:

```bash
/opt/workshop/bin/reset.sh
```

This:

- stops Router, Envoy, and Dashboard;
- clears generated configs and logs;
- restores the clean notebook and helper;
- restores the visible `agent-demo/`; and
- reconfigures Hermes.

It does not stop vLLM terminal processes.

After reset:

```bash
/opt/workshop/bin/status.sh
```

## If the session is running behind

Cut in this order:

1. Reduce the custom challenge to explanation only.
2. Show one participant prompt instead of three in Section 4.
3. Make Insights inspection instructor-only.
4. Do not cut the four staged configuration concepts.
5. Do not skip the Stage 5 deploy and collision verification.

## Closing message

End with:

```text
The application kept one model name. We connected multiple model paths,
measured request intent, expressed policy, resolved conflicts with priority,
and verified every decision with evidence.
```

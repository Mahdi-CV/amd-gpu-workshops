# Presenter guide: From Rules to Reasoning

This guide matches the keyword-first Decision 3.0 D3 Lite notebook.

## Workshop outcome

Participants should leave able to explain:

```text
application requirement
-> observable fact
-> signal
-> eligible decision
-> priority
-> route
-> task model
-> evidence
```

They should distinguish:

- a **decision**, which is application policy;
- a **decision model**, which supplies routing evidence; and
- a **task model**, which writes the user-facing answer.

## Recommended timing

The beginner path, including the final tuning challenge, is approximately
105 minutes.
The optional Vela PII span extension adds about 10 minutes.

| Segment | Minutes | Running total |
| --- | ---: | ---: |
| Orientation and environment check | 10 | 10 |
| Exact keyword route | 15 | 25 |
| Follow one request | 10 | 35 |
| Expose the exact rule's limitation | 5 | 40 |
| D3 Lite semantic routing | 20 | 60 |
| Prompt Laboratory and customization | 15 | 75 |
| Priority collision | 10 | 85 |
| Application integration | 5 | 90 |
| Tune the launch router | 15 | 105 |

For a 75-minute delivery:

- prestart the container before participants arrive;
- use four Prompt Laboratory prompts;
- keep the narrower-question exercise instructor-led; and
- preserve the six-prompt tuning challenge as the closing exercise.

## Presenter principles

1. Start with one exact fact, not model inference.
2. Ask for a prediction before every preview.
3. Introduce terminology only after participants see a route.
4. Read policy as a sentence before discussing YAML fields.
5. Keep the same launch-assistant story throughout.
6. In the core path, say **D3 Lite** for the default decision model. In the
   optional PII extension, call **Vela 3.0** the span-capable signal model.
7. Say **routine-model** and **reasoning-model** for task models.
8. Treat probabilities near the threshold as calibration evidence.
9. Keep the core path on routing previews; show the raw chat-completions call
   only in the final application appendix.
10. Use only the two participant operations:
    `preview_route` and `apply_recipe`.
11. State what participants are changing, why it matters, and what successful
    output looks like before each section.

## Preflight

The production image must provide:

- `FOUNDRY_ENDPOINT` and `FOUNDRY_API_KEY` from the Microsoft lab;
- `FW-Qwen3.8-27B` as the routine Azure Foundry deployment;
- `FW-GLM-5.3-Flash` as the reasoning Azure Foundry deployment;
- local OpenAI-compatible relays on `8002` and `8001`;
- the pinned CPU Router/runtime image;
- pinned D3 Lite files under `/opt/models/d3-lite`;
- pinned Vela 3.0 files under `/opt/models/vela3-fast`;
- D3 Lite listening on `127.0.0.1:8100`;
- the Foundry relay on `8001` and `8002`;
- the Router listener on `8898`;
- management API on `8080`;
- Dashboard on `9000`; and
- a writable `/workspace`.

Run:

```bash
/opt/workshop/bin/start-platform.sh
WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

Final acceptance target:

```text
Challenge complete: 6/6 routing checks passed
```

## Run of show

### Opening

Frame the application:

> The application has one model name. The Router chooses between a Routine
> route and a Reasoning route.

Do not introduce System One or D3 Lite yet.

State explicitly:

> The two task models are already deployed on Azure Foundry. Participants do
> not download or launch them. The VM exposes them through local relays so the
> Router can use ordinary OpenAI-compatible provider connections.

### Section 1: exact keyword route

Requirement:

```text
[SECURITY-REVIEW] -> security-review -> Reasoning route
otherwise         -> routine-fallback -> Routine route
```

The positive prompt must use the Reasoning route. A definition containing the
words “security review” without the exact marker must stay routine.

Keep the notebook order: define the two HTTP helpers, introduce the Section 1
prompt, walk through the recipe, run `apply_recipe(keyword_recipe)`, and then
preview that prompt exactly once. The preview must print:

```text
Decision: security-review
Route: Reasoning route
Task model: reasoning-model
```

Do not generate a task-model answer here and do not rerun the tagged prompt in
the controls or Section 2. Reuse `tagged_result`.

### Section 2: follow one request

Trace:

```text
marker
-> keyword signal
-> security-review
-> priority 200
-> reasoning-model
```

Only now introduce signal, decision, priority, route, and task model.

### Section 3: exact matching has a limit

Remove the marker while keeping the request reasoning-heavy. The expected
result is the Routine fallback.

Say:

> The Router followed the policy correctly. The policy simply does not
> understand meaning yet.

### Section 4: D3 Lite and System One

Explain:

```text
System One = typed question interface
D3 Lite    = decision model answering the question
```

The core uses one `noul` yes/no question. Avoid surveying every question type.

Rerun the untagged security-design prompt. It should now use semantic
reasoning. Run the definition control to show that semantic routing does not
send everything to the stronger model.

Measured controls on the pinned 20-core CPU reference:

```text
untagged security analysis  0.86 -> reasoning
rollback definition        0.04 -> routine
checkout diagnosis         0.92 -> reasoning
deployment choice          0.63 -> reasoning
brief troubleshooting      0.22 -> routine
```

Each D3 preview took roughly 0.17–0.25 seconds inside the final production CPU
image on the reference host.

### Prompt Laboratory

Use:

- two routine controls;
- two reasoning controls; and
- two boundary prompts.

Do not teach `0.50` as a universal threshold. It is the workshop's tested
starting point for this pinned D3 Lite revision.

### Custom question

Narrow the requirement to technical comparison and recommendation. The
definition and diagnosis-without-comparison controls should fall through.

### Section 5: priority

Add:

```text
[PRIVATE] -> private-local, priority 300
semantic-reasoning, priority 200
routine-fallback, priority 100
```

Compare a public analysis prompt with the same prompt marked `[PRIVATE]`.

### Section 6: deploy a recipe

Show that the same recipe can be deployed either:

- as a Python dictionary through the management API; or
- as YAML imported through Dashboard Builder.

The default notebook path uses Python so automated execution remains
repeatable. Demonstrate Dashboard import during delivery when time permits.

Point out that raw D3 Lite does not support span extraction. If time allows,
run the optional Vela extension:

```text
fictional PII prompt
-> Vela span extraction
-> personal-data signal
-> pii-local, priority 400
-> Routine route
```

The notebook finds the Vela deployment in the model catalog, whether it is
named `vela3-fast` or something else. It saves `06-vela-pii-recipe.yaml`,
which can also be imported through Dashboard Builder, and activates it.
The Router serves only the models the active recipe uses, so Vela starts
when this recipe is activated; on the Microsoft VM it stops after the first
`apply_recipe` in Section 1 and is not available until then. Skip the
extension if the catalog has no Vela deployment.

### Final challenge: tune the launch router

Frame this as a change request against the working `private_recipe`, not a
blank configuration exercise.

The participants receive six prompts and required model outcomes. The current
recipe should pass four and fail two:

```text
diagnosis-only       currently reasoning, required routine
explicit [INCIDENT]  currently routine, required reasoning
```

Give only these hints:

```text
start from private_recipe
tune existing semantic evidence
add exact application evidence where needed
a signal alone does not change routing
private behavior must remain intact
```

Participants may modify an existing decision or add a new one. Do not require
specific signal names, decision names, or priorities; the scorecard checks the
selected model.

Do not reveal the comparison-specific question or `[INCIDENT]` signal before
participants attempt the challenge. If the room is blocked:

1. first point out that diagnosis and comparison are different requirements;
2. then point out that brackets indicate an exact application fact;
3. only then show one recommended policy shape.

The presenter-only solution key documents four passing solutions, including:

- a dedicated incident decision;
- an `OR` branch on the existing reasoning decision;
- threshold-only tuning on the pinned model; and
- a second narrow System One signal.

Completion requires:

```text
Challenge complete: 6/6 routing checks passed
```

Afterward, open the six records in Dashboard Insights and ask participants to
explain the observed decisions, especially the private incident collision.

## Troubleshooting

### D3 Lite is still loading

```bash
tail -f /workspace/logs/d3-lite.log
curl -s http://127.0.0.1:8100/health
```

### A semantic prompt falls through

Inspect:

- the active question;
- `signal_values`;
- the threshold;
- D3 Lite health; and
- the active recipe returned by `GET /api/v1/config`.

### The optional Vela PII extension skips

Inspect the model capabilities:

```bash
curl -s http://127.0.0.1:8080/api/v1/diagnostics/models/systemone
```

The optional section needs a Vela deployment in the model catalog:

```bash
curl -s http://127.0.0.1:8080/api/v1/config \
  | python3 -c 'import json,sys; print(list(json.load(sys.stdin)["global"]["model_catalog"]["deployments"]))'
```

The diagnostics list above shows only the models the active recipe uses, so
Vela is missing from it until the PII recipe is active. A span call made
before that returns `The selected deployment is not published`.

### A Foundry model connection is missing

Do not ask participants to start a model server. Confirm:

```bash
test -n "$FOUNDRY_ENDPOINT"
test -n "$FOUNDRY_API_KEY"
curl -s http://127.0.0.1:8002/v1/models
curl -s http://127.0.0.1:8001/v1/models
tail -n 100 /workspace/logs/foundry-relay.log
```

### Dashboard and notebook disagree

The notebook hot-reloads through:

```text
PUT /api/v1/config
```

Refresh Dashboard after activation. Editing a YAML file alone does not prove
the in-memory Router accepted it.

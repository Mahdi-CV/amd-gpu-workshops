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

The beginner path, including Launch Control, is approximately 100 minutes.

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
| Launch Control | 10 | 100 |

For a 75-minute delivery:

- prestart the container before participants arrive;
- use four Prompt Laboratory prompts;
- keep the narrower-question exercise instructor-led; and
- preserve Launch Control as the closing exercise.

## Presenter principles

1. Start with one exact fact, not model inference.
2. Ask for a prediction before every preview.
3. Introduce terminology only after participants see a route.
4. Read policy as a sentence before discussing YAML fields.
5. Keep the same launch-assistant story throughout.
6. Say **D3 Lite** only for the decision model.
7. Say **routine-model** and **reasoning-model** for task models.
8. Treat probabilities near the threshold as calibration evidence.
9. Show the raw OpenAI-compatible request once.
10. Use only the three participant operations:
    `preview_route`, `send_prompt`, and `apply_recipe`.
11. State what participants are changing, why it matters, and what successful
    output looks like before each section.

## Preflight

The production image must provide:

- the pinned CPU Router/runtime image;
- pinned D3 Lite files under `/opt/models/d3-lite`;
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

Expected final lines:

```text
PASS Launch Control -> ROUTE-CONTROL-GREEN
PASS baseline restored
```

## Run of show

### Opening

Frame the application:

> The application has one model name. The Router chooses between a Routine
> route and a Reasoning route.

Do not introduce System One or D3 Lite yet.

### Section 1: exact keyword route

Requirement:

```text
[SECURITY-REVIEW] -> security-review -> Reasoning route
otherwise         -> routine-fallback -> Routine route
```

The positive prompt must use the Reasoning route. A definition containing the
words “security review” without the exact marker must stay routine.

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

### Section 6: application integration

The application still requests:

```json
{"model": "vllm-sr/auto"}
```

### Launch Control

Participants infer:

```text
private > security > semantic > fallback
```

One valid solution is:

```text
400 private-local
300 security-review
200 semantic-reasoning
100 routine-fallback
```

Completion requires:

```text
Score: 6/6
Completion code: ROUTE-CONTROL-GREEN
```

Ask the participant to explain the three-way collision, not merely show the
completion code.

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

### Dashboard and notebook disagree

The notebook hot-reloads through:

```text
PUT /api/v1/config
```

Refresh Dashboard after activation. Editing a YAML file alone does not prove
the in-memory Router accepted it.

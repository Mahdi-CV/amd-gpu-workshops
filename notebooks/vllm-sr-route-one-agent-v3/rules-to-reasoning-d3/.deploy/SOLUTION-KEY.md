# Presenter solution key

Keep this file under `.deploy/`.

Values are for the pinned production D3 Lite revision. Re-record probabilities
whenever the model revision, question wording, or rendering changes.

## Exact keyword recipe

Expected:

```text
[SECURITY-REVIEW] ... -> security-review -> reasoning-model
Define a security review. -> routine-fallback -> routine-model
```

The brackets are part of the marker.

## Broad D3 Lite question

```python
DECISION_QUESTION = (
    "Does answering this request well require multi-step reasoning, "
    "comparison of alternatives, diagnosis, or a justified plan?"
)
DECISION_THRESHOLD = 0.50
```

Expected on the pinned CPU runtime:

| Prompt | Approx. P(yes) | Model |
| --- | ---: | --- |
| Untagged security analysis | 0.86 | reasoning |
| Rollback definition | 0.04 | routine |
| Launch rewrite | 0.07 | routine |
| Duplicate-checkout diagnosis | 0.92 | reasoning |
| Deployment choice | 0.63 | reasoning |
| Brief troubleshooting | 0.22 | routine |
| Cache teaching example | 0.07 | routine |

The measured decision-model latency was roughly 0.17–0.25 seconds per preview
inside the final production CPU image on the reference host.

## Narrow comparison question

```text
Does the user ask to compare competing technical approaches and recommend or
justify one?
```

Expected:

```text
deployment comparison -> reasoning-model, approximately 0.99
deployment definition -> routine-model, approximately 0.07
migration diagnosis without comparison -> routine-model, approximately 0.01
```

## Guided private collision

```text
300 private-local
200 semantic-reasoning
100 routine-fallback
```

Expected:

```text
public reasoning-heavy -> semantic-reasoning -> reasoning-model
[PRIVATE] same request -> private-local -> routine-model
```

## Launch Control

One valid solution:

```python
PRIVATE_PRIORITY = 400
SECURITY_PRIORITY = 300
SEMANTIC_PRIORITY = 200
```

Required order:

```text
private-local        400
security-review      300
semantic-reasoning   200
routine-fallback     100
```

Expected:

| Case | Decision | Model |
| --- | --- | --- |
| Launch update | `routine-fallback` | `routine-model` |
| Architecture choice | `semantic-reasoning` | `reasoning-model` |
| Security review | `security-review` | `reasoning-model` |
| Private note | `private-local` | `routine-model` |
| Private analysis | `private-local` | `routine-model` |
| Three-way collision | `private-local` | `routine-model` |

Completion:

```text
Score: 6/6
Completion code: ROUTE-CONTROL-GREEN
```

## Recovery

Restore the image starter recipe by restarting a fresh workshop container, or
activate the exact keyword recipe from Section 1.

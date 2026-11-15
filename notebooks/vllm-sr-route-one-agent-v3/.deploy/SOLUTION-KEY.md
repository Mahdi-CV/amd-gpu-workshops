# Presenter solution key: From Rules to Reasoning

This is the solution key for
`route-one-agent-across-two-models-v3.ipynb` in the parent folder.
Keep it under `.deploy/` and do not expose it during the participant exercise.

Values are for the pinned production D3 Lite revision. Re-record probabilities
whenever the model revision, question wording, or rendering changes.

## Exact keyword recipe

Run the participant flow in this order:

```text
define preview_route and apply_recipe
-> apply_recipe(keyword_recipe)
-> preview the tagged prompt exactly once
-> reuse tagged_result in Section 2
```

Expected first preview:

```text
Decision: security-review
Route: Reasoning route
Task model: reasoning-model
```

Expected controls:

```text
Define a security review. -> routine-fallback -> routine-model
Rewrite the launch update.  -> routine-fallback -> routine-model
```

The brackets are part of `[SECURITY-REVIEW]`. The core exercise does not
generate a task-model answer and does not rerun the tagged prompt.

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
| Untagged security analysis | 0.88 | reasoning |
| Signing-key definition | 0.03 | routine |
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

The notebook saves:

```text
/workspace/generated-config/05-private-recipe.yaml
```

Participants may deploy it through `apply_recipe(private_recipe)` or import it
through Dashboard **Routing → Builder**.

## Optional Vela PII span extension

The fictional prompt should produce three spans:

```text
PERSON         Jane Doe
EMAIL_ADDRESS  jane.doe@example.com
PHONE_NUMBER   415-555-0134
```

The recipe adds:

```text
400 pii-local
300 private-local
200 semantic-reasoning
100 routine-fallback
```

Expected:

```text
PII demo prompt                 -> pii-local -> routine-model
Signing-key rotation definition -> routine-fallback -> routine-model
```

The notebook saves:

```text
/workspace/generated-config/06-vela-pii-recipe.yaml
```

This is optional because raw D3 Lite does not answer span questions. The
exercise runs only when the model catalog includes a Vela 3.0 deployment.
The Router serves only the models the active recipe uses, so the cell
activates the PII recipe first; that starts Vela, and then the span call runs.

## Final challenge solutions

Do not reveal a solution until participants have attempted the six acceptance
prompts. The scorecard checks selected models, so more than one policy shape is
valid.

Measured with the pinned D3 Lite revision:

| Prompt family | Broad question P(yes) | Comparison question P(yes) |
| --- | ---: | ---: |
| Routine rewrite | 0.09 | 0.01 |
| Compare and recommend | 0.82 | 0.99 |
| Diagnosis-only queue problem | 0.80 | 0.03 |
| Simple `[INCIDENT]` update | 0.05 | 0.00 |
| “incident” near miss | 0.10 | 0.01 |

The current recipe therefore starts at `4/6`: diagnosis-only is over-routed
and the explicit incident is under-routed.

### Solution A — recommended: tune the question and add an incident decision

```python
challenge_recipe = copy.deepcopy(private_recipe)

challenge_recipe["signals"]["systemone"][0]["question"]["instructions"] = (
    "Does the user ask to compare competing technical approaches "
    "and recommend or justify one?"
)

challenge_recipe["signals"]["keywords"].append(
    {
        "name": "incident-marker",
        "operator": "OR",
        "keywords": ["[INCIDENT]"],
        "case_sensitive": False,
    }
)

challenge_recipe["decisions"].insert(
    1,
    {
        "name": "incident-response",
        "description": "Explicit incidents use the Reasoning route.",
        "priority": 250,
        "rules": {
            "operator": "AND",
            "conditions": [
                {"type": "keyword", "name": "incident-marker"}
            ],
        },
        "modelRefs": [
            {"model": "reasoning-model", "use_reasoning": True}
        ],
        "algorithm": {"type": "static"},
    },
)

apply_recipe(challenge_recipe)
```

This gives:

```text
private-local        300
incident-response    250
semantic-reasoning   200
routine-fallback     100
```

### Solution B — update the existing reasoning decision

Add the same `incident-marker`, tune the D3 question, and change
`semantic-reasoning` to match either source of evidence:

```yaml
rules:
  operator: OR
  on_unknown: no_match
  conditions:
    - type: keyword
      name: incident-marker
    - type: systemone
      name: needs-deep-reasoning
```

This needs no new decision. The private decision still wins because its
priority is higher.

### Solution C — threshold-only D3 tuning

On the pinned model, keeping the broad question and changing its threshold to
approximately `0.81` separates the measured comparison (`0.82`) from the
diagnosis-only prompt (`0.80`). Add the incident signal through Solution A or
B.

This passes the six tests but is fragile: the margin is small and should be
recalibrated after any model, batching, or prompt-rendering change. Prefer
changing the question because it expresses the requirement directly.

### Solution D — add a second narrow System One signal

Leave the broad signal in place, add a new `systemone` signal with the
comparison-and-recommendation question, and make `semantic-reasoning` read the
new signal. Then add the incident marker through a dedicated decision or an
`OR` condition.

This also passes, but it leaves unused or overlapping semantic evidence unless
the broad signal serves another decision.

### Behavior expected from every solution

| Case | Required model |
| --- | --- |
| Routine control | `routine-model` |
| Semantic comparison | `reasoning-model` |
| Diagnosis only | `routine-model` |
| Explicit incident | `reasoning-model` |
| Near miss | `routine-model` |
| Private incident | `routine-model` |

Completion:

```text
Challenge complete: 6/6 routing checks passed
```

Reject solutions that merely overfit the visible prompt wording with unrelated
keywords. Accept different signal names, decision names, rule trees, or
priorities when they express the application requirement and pass the
scorecard.

## Recovery

Restore the image starter recipe by restarting a fresh workshop container, or
activate the exact keyword recipe from Section 1.

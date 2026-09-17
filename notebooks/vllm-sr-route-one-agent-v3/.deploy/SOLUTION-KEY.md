# Presenter Solution Key: Route One Agent Across Two Models

This file is for presenters only. Keep it under `.deploy/` and do not link it
from the participant notebook or other participant-visible files.

It contains the completed participant exercises and the checks that prove each
policy is active.

## Confirm the environment is ready

Both model terminals must be running before testing the routed exercises.

```bash
/opt/workshop/bin/status.sh
```

Expected:

```text
routine model        ready
reasoning model      ready
semantic router      ready
router management    ready
dashboard            ready
Hermes               ready
```

## Section 4 solution: routing prediction experiment

Replace the participant placeholders with:

```python
routing_experiment = [
    {
        "label": "control",
        "prompt": "Give me a short definition of HTTP.",
        "prediction": "routine",
    },
    {
        "label": "clearly routine",
        "prompt": "Rewrite this sentence clearly: retries can run a job twice.",
        "prediction": "routine",
    },
    {
        "label": "clearly reasoning-heavy",
        "prompt": (
            "Diagnose cascading failures in a distributed queue, compare "
            "multiple remediation strategies and their tradeoffs, and "
            "justify a safe rollout plan."
        ),
        "prediction": "reasoning",
    },
    {
        "label": "intentionally uncertain",
        "prompt": (
            "A Python API became slower after deployment. "
            "Suggest what I should check first."
        ),
        "prediction": "uncertain",
    },
]
```

Run this cell and the following comparison cell.

Expected on the approved workshop image:

| Label | Expected complexity | Expected decision | Expected model |
| --- | --- | --- | --- |
| control | easy or medium | `routine-lane` | `routine-model` |
| clearly routine | easy or medium | `routine-lane` | `routine-model` |
| clearly reasoning-heavy | hard | `reasoning-lane` | `reasoning-model` |
| intentionally uncertain | medium | `routine-lane` | `routine-model` |

The uncertain prompt is calibration evidence. If its exact class changes after
updating Router artifacts, confirm that it still falls back to the routine
path and record the new result before presenting.

## Section 5 check: Hermes Agent

Run the setup cell and:

```python
agent_run = lab.run_agent(AGENT_TASK, exercise_dir)
```

Success requires both:

```text
Hermes final response
3 passed
```

One Hermes task does not need to switch between models. Section 6 demonstrates
route changes across separate user turns.

## Section 6 check: multi-turn routing

Expected sequence:

| Turn | Request type | Expected model |
| ---: | --- | --- |
| 1 | Definition | `routine-model` |
| 2 | Rewrite | `routine-model` |
| 3 | Strategy comparison and tradeoffs | `reasoning-model` |
| 4 | One-sentence summary | `routine-model` |

The expected model sequence is:

```text
routine
routine
reasoning
routine
```

## Section 8 check: deploy the incident policy

After generating `generated-config/05-incident-policy.yaml`:

1. Open the file in Jupyter.
2. Copy all YAML.
3. Open **Dashboard → Build → Builder**.
4. Select **Import**.
5. Paste the YAML and select **Import** again.
6. Select **Compile**.
7. Confirm `incident-fast-lane` has priority 300 and selects
   `routine-model`.
8. Select **Deploy**.
9. Return to the notebook and rerun the collision cell.

Confirm that the policy is active:

```bash
curl -s http://127.0.0.1:8080/api/v1/config \
  | python3 -c '
import json, sys
print([d["name"] for d in json.load(sys.stdin)["routing"]["decisions"]])
'
```

Expected decision names:

```text
incident-fast-lane
reasoning-lane
routine-lane
```

Expected collision result:

```text
decision: incident-fast-lane
selected_model: routine-model
```

Both the incident and complexity rules match. Priority 300 wins over priority
200.

## Section 10 solution: custom policy challenge

Replace the participant values with:

```python
MY_KEYWORDS = ["CONFIDENTIAL"]
MY_ROUTE_NAME = "my-route"
MY_PRIORITY = 250
MY_MODEL = "reasoning-model"

challenge_prompts = {
    "positive": "CONFIDENTIAL: summarize this internal deployment note.",
    "negative": "Define idempotency in one sentence.",
    "collision": (
        "CONFIDENTIAL: compare multiple rollout strategies "
        "and justify the safest plan."
    ),
}
POLICY_IS_PUBLISHED = False
```

Run the cell once. It should generate:

```text
generated-config/06-my-policy.yaml
```

Deploy it through **Dashboard → Build → Builder** using the same Import,
Compile, and Deploy sequence as Section 8.

Then change:

```python
POLICY_IS_PUBLISHED = True
```

Rerun the cell. Expected:

| Test | Expected decision | Expected model |
| --- | --- | --- |
| positive | `my-route` | `reasoning-model` |
| negative | `routine-lane` | `routine-model` |
| collision | `my-route` | `reasoning-model` |

The collision chooses `my-route` because priority 250 is higher than
`reasoning-lane` priority 200.

The final line should be:

```text
✓ Positive, negative, and collision checks passed.
```

## Full presenter acceptance test

With both model endpoints and the workshop platform running:

```bash
/opt/workshop/bin/verify-image.sh

WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

The executed acceptance notebook is saved to:

```text
/workspace/state/acceptance/route-one-agent-e2e.executed.ipynb
```

The acceptance script temporarily publishes the incident and custom policies,
checks their live behavior, and restores the original Router configuration.

## Recovery and reset

If a routing assertion fails, first inspect the active decisions with the
management API command above. A generated YAML file has no effect until it is
deployed.

To restore a clean participant environment:

```bash
/opt/workshop/bin/reset.sh
/opt/workshop/bin/status.sh
```

`reset.sh` restores the notebook, helper, demo project, generated
configuration, logs, and baseline Router policy. It does not stop the two vLLM
processes running in participant terminals.

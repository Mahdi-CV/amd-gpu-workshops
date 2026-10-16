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
2. Copy the routing YAML.
3. Open **Dashboard → Build → Builder**.
4. Select **Import**.
5. Paste the YAML and select **Import** again.
6. Select **Compile**.
7. Confirm `incident-fast-lane` has priority 300 and selects
   `routine-model`.
8. Select **Deploy**.
9. Return to the notebook and rerun the collision cell.

The visible file is routing-only. The complete configuration used by the
notebook's validation and boot check remains in a hidden internal directory.

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

## Section 10 solutions: keep private finance requests local

Do not reveal either solution until participants have attempted the challenge.
Both solutions below satisfy the same behavior-only scorecard.

Create this keyword signal in
**Dashboard → Build → Routing → Signals**:

```yaml
name: private-financial-data
operator: OR
keywords:
  - PRIVATE
  - ACCOUNT-ID
case_sensitive: false
```

Then use either Solution A or Solution B.

### Solution A: exclude private data from the reasoning decision

Edit `reasoning-lane` under
**Dashboard → Build → Routing → Decisions** so its rule is:

```yaml
rules:
  operator: AND
  conditions:
    - type: complexity
      name: request_complexity:hard
    - operator: NOT
      conditions:
        - type: keyword
          name: private-financial-data
```

This keeps the existing decision set small. A hard public request matches
`reasoning-lane`, while a hard private request is excluded and falls through
to `routine-lane`.

### Solution B: add a dedicated privacy decision

Leave `reasoning-lane` unchanged and add:

```yaml
name: private-finance-lane
description: Keep private financial requests on the local model.
priority: 300
rules:
  operator: AND
  conditions:
    - type: keyword
      name: private-financial-data
modelRefs:
  - model: routine-model
algorithm:
  type: static
```

This policy is more explicit. Its higher priority makes the privacy route win
when a private request is also hard. It is a better shape when privacy traffic
will later need separate plugins, retention rules, auditing, or other
route-specific behavior.

### Verify either solution

Compile and deploy the policy, then run the notebook scorecard. Expected:

| Test | Expected model |
| --- | --- |
| `public_simple` | `routine-model` |
| `public_hard` | `reasoning-model` |
| `private_simple` | `routine-model` |
| `private_hard` | `routine-model` |

The decision names may differ because the scorecard checks behavior, not one
specific policy shape.

The final line must be:

```text
Challenge complete: 4/4 routing checks passed
```

## Full presenter acceptance test

With both model endpoints and the workshop platform running:

```bash
/opt/workshop/bin/verify-image.sh
```

Then run the participant notebook from a clean kernel:

```text
Kernel → Restart Kernel and Run All Cells
```

At Section 8, deploy the incident policy and verify the priority result. At
Section 10, privately apply either solution above and confirm the `4/4`
scorecard. Restore the original Router configuration after the acceptance run.

The tracked `verify-notebook-e2e.py` still targets the previous challenge and
is intentionally unchanged in this content-only revision.

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

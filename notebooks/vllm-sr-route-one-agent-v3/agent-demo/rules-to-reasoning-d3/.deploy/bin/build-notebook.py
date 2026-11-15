#!/usr/bin/env python3
"""Build the participant notebook from small, reviewable cells."""

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[2]
WORKSHOP_ROOT = ROOT.parents[1]
OUTPUT = WORKSHOP_ROOT / "route-one-agent-across-two-models-v3.ipynb"


def md(source: str):
    return nbf.v4.new_markdown_cell(source.strip())


def code(source: str):
    return nbf.v4.new_code_cell(source.strip())


cells = [
    md(
        r"""
<div style="background:linear-gradient(125deg,#080b12 0%,#151b2c 58%,#4b102d 100%);border:1px solid #343b52;border-radius:18px;padding:30px 34px;color:#fff">
  <div style="font-size:13px;font-weight:700;letter-spacing:.16em;color:#ff7478">AMD × vLLM SEMANTIC ROUTER</div>
  <div style="font-size:38px;line-height:1.15;font-weight:800;margin-top:10px">From Rules to Reasoning</div>
  <div style="font-size:18px;color:#d7dbea;margin-top:8px">Build an intelligent model router, starting with one exact rule and progressing to Decision 3.0 D3 Lite.</div>
</div>

# Why build a model router?

You are building the routing policy for an engineering assistant used during
software launches. It has two task-model routes:

| Route | Azure Foundry deployment | Logical Router name | Best for |
| --- | --- | --- | --- |
| **Routine route** | `FW-Qwen3.8-27B` | `routine-model` | Definitions, rewriting, formatting, and direct answers |
| **Reasoning route** | `FW-GLM-5.3-Flash` | `reasoning-model` | Diagnosis, comparison, architecture, and justified plans |

The application should not contain model-selection logic. It always requests:

```text
vllm-sr/auto
```

The Router observes each request, applies policy, selects a route, and records
why that route won.
"""
    ),
    md(
        r"""
## What you will build

The workshop grows one policy in a deliberate order:

```text
EXACT MARKER
→ SEE ITS LIMIT
→ ROUTE BY MEANING WITH D3 LITE
→ COMBINE RULES WITH PRIORITY
→ LAUNCH CONTROL
→ EXPORT YOUR ROUTER
```

By the end, you will be able to:

1. preview how an ordinary prompt will route through the Router;
2. explain signal → decision → route → task model;
3. create an exact application rule;
4. ask D3 Lite a semantic routing question through System One;
5. test and tune the decision boundary;
6. resolve overlapping rules with priority; and
7. export the policy as a runnable Router starter.
"""
    ),
    md(
        r"""
## The system we are building

<div style="max-width:940px;margin:18px auto;padding:8px">
<svg viewBox="0 0 940 430" role="img" aria-label="Application sends one model name to vLLM Semantic Router. D3 Lite supplies routing evidence. The Router selects either the Routine route and routine-model or the Reasoning route and reasoning-model." style="width:100%;height:auto;font-family:Inter,Segoe UI,Arial,sans-serif">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#697386"/>
    </marker>
    <filter id="shadow" x="-10%" y="-20%" width="120%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-opacity=".13"/>
    </filter>
  </defs>

  <rect x="28" y="168" width="180" height="94" rx="16" fill="#f8fafc" stroke="#64748b" stroke-width="2" filter="url(#shadow)"/>
  <text x="118" y="204" text-anchor="middle" font-size="20" font-weight="700" fill="#172033">Your application</text>
  <text x="118" y="232" text-anchor="middle" font-size="15" fill="#526072">model: vllm-sr/auto</text>

  <rect x="320" y="142" width="260" height="146" rx="18" fill="#fff7f7" stroke="#e34d59" stroke-width="3" filter="url(#shadow)"/>
  <text x="450" y="184" text-anchor="middle" font-size="22" font-weight="800" fill="#8d2230">vLLM Semantic Router</text>
  <text x="450" y="220" text-anchor="middle" font-size="16" fill="#5c3340">signals + decisions + priority</text>
  <text x="450" y="251" text-anchor="middle" font-size="15" fill="#6b4a53">selects one task-model route</text>

  <rect x="346" y="20" width="208" height="82" rx="16" fill="#fffaf0" stroke="#d39b21" stroke-width="2" filter="url(#shadow)"/>
  <text x="450" y="53" text-anchor="middle" font-size="20" font-weight="700" fill="#76530c">D3 Lite</text>
  <text x="450" y="78" text-anchor="middle" font-size="14" fill="#695a35">local CPU decision model</text>

  <rect x="688" y="72" width="220" height="118" rx="18" fill="#eff8ff" stroke="#2879bd" stroke-width="3" filter="url(#shadow)"/>
  <text x="798" y="108" text-anchor="middle" font-size="20" font-weight="800" fill="#155b91">Routine route</text>
  <text x="798" y="140" text-anchor="middle" font-size="17" font-weight="700" fill="#244b68">routine-model</text>
  <text x="798" y="165" text-anchor="middle" font-size="14" fill="#4b6477">Azure Foundry deployment</text>

  <rect x="688" y="242" width="220" height="118" rx="18" fill="#f6f0ff" stroke="#7749bd" stroke-width="3" filter="url(#shadow)"/>
  <text x="798" y="278" text-anchor="middle" font-size="20" font-weight="800" fill="#583094">Reasoning route</text>
  <text x="798" y="310" text-anchor="middle" font-size="17" font-weight="700" fill="#493967">reasoning-model</text>
  <text x="798" y="335" text-anchor="middle" font-size="14" fill="#66597b">Azure Foundry deployment</text>

  <line x1="208" y1="215" x2="312" y2="215" stroke="#697386" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="450" y1="102" x2="450" y2="134" stroke="#d39b21" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M580 183 C628 183, 635 131, 680 131" fill="none" stroke="#2879bd" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M580 247 C628 247, 635 301, 680 301" fill="none" stroke="#7749bd" stroke-width="3" marker-end="url(#arrow)"/>

  <text x="259" y="202" text-anchor="middle" font-size="13" fill="#526072">one endpoint</text>
  <text x="613" y="153" text-anchor="middle" font-size="13" fill="#2879bd">routine</text>
  <text x="616" y="282" text-anchor="middle" font-size="13" fill="#7749bd">reasoning</text>
</svg>
</div>

There are two different model jobs:

| Model role | Job |
| --- | --- |
| **Decision model** | Answers small routing questions before generation |
| **Task model** | Produces the user-facing answer |

This workshop uses Decision 3.0 **`d3-lite`** as the decision model.

### Read the model cards

- [Decision 3.0 D3 Lite on Hugging Face](https://huggingface.co/vllm-sr/d3-lite)
- [Vela 3.0 `vela3-fast` on Hugging Face](https://huggingface.co/vllm-sr/vela3-fast)

D3 Lite drives the core routing exercises. An optional extension after
Section 6 uses `vela3-fast` because Vela can locate exact text spans.
"""
    ),
    md(
        r"""
## 0. Connect to the models on Azure Foundry

The two task models are already deployed on Azure Foundry:

| Route | Azure Foundry model | Local OpenAI-compatible relay |
| --- | --- | --- |
| Routine route | `FW-Qwen3.8-27B` | `http://127.0.0.1:8002` |
| Reasoning route | `FW-GLM-5.3-Flash` | `http://127.0.0.1:8001` |

The lab VM receives `FOUNDRY_ENDPOINT` and `FOUNDRY_API_KEY` from the Microsoft
lab environment. A small relay translates the local OpenAI-compatible requests
into Foundry requests.

```text
Router → local relay → Azure Foundry deployment
```

You do **not** download, launch, or serve either task model in this workshop.

D3 Lite is different: it is the small local CPU decision model used only for
routing judgments. It does not write the user-facing answer. The image also
contains `vela3-fast`; the core path does not need it, but the optional PII
extension uses its span-extraction capability.

### Verify the preconfigured environment

The Foundry relay, Router, D3 Lite, Dashboard, and JupyterLab start with the
workshop container. Run the next cell to verify their connections.
"""
    ),
    code(
        r"""
import copy
import json
import os
import time
from pathlib import Path
from pprint import pprint

import requests
import yaml
from IPython.display import HTML, display

ROUTER_API = os.getenv("ROUTER_API", "http://127.0.0.1:8898")
MANAGEMENT_API = os.getenv("ROUTER_MANAGEMENT_API", "http://127.0.0.1:8080")
DASHBOARD_URL = os.getenv("DASHBOARD_BROWSER_URL", "http://localhost:9000")
ROUTINE_ENDPOINT = os.getenv("ROUTINE_ENDPOINT", "http://127.0.0.1:8002")
REASONING_ENDPOINT = os.getenv("REASONING_ENDPOINT", "http://127.0.0.1:8001")
ROUTINE_FOUNDRY_MODEL = os.getenv(
    "ROUTINE_PROVIDER_MODEL",
    "FW-Qwen3.8-27B",
)
REASONING_FOUNDRY_MODEL = os.getenv(
    "REASONING_PROVIDER_MODEL",
    "FW-GLM-5.3-Flash",
)
ROUTED_MODEL = "vllm-sr/auto"

services = {
    "Routine Foundry connection": f"{ROUTINE_ENDPOINT}/v1/models",
    "Reasoning Foundry connection": f"{REASONING_ENDPOINT}/v1/models",
    "Semantic Router": f"{ROUTER_API}/v1/models",
    "Router management API": f"{MANAGEMENT_API}/health",
    "Dashboard": "http://127.0.0.1:9000",
}

service_status = {}
for name, url in services.items():
    try:
        response = requests.get(url, timeout=5)
        service_status[name] = response.ok
        marker = "✓" if response.ok else "✗"
        print(f"{marker} {name}")
    except requests.RequestException as exc:
        service_status[name] = False
        print(f"✗ {name}: {type(exc).__name__}")

# D3 Lite runs inside the Router, so ask the Router whether it is loaded.
try:
    deployments = requests.get(
        f"{MANAGEMENT_API}/api/v1/diagnostics/models/systemone",
        timeout=10,
    ).json().get("deployments", [])
    d3_ready = any(
        item.get("id") == "d3-lite" and item.get("ready")
        for item in deployments
    )
except requests.RequestException:
    d3_ready = False
service_status["D3 Lite decision model"] = d3_ready
print(f"{'✓' if d3_ready else '✗'} D3 Lite decision model")

print()
print("Configured task-model connections:")
for route, endpoint, expected_model in (
    ("Routine route", ROUTINE_ENDPOINT, ROUTINE_FOUNDRY_MODEL),
    ("Reasoning route", REASONING_ENDPOINT, REASONING_FOUNDRY_MODEL),
):
    try:
        response = requests.get(f"{endpoint}/v1/models", timeout=10)
        response.raise_for_status()
        discovered = [
            item["id"]
            for item in response.json().get("data", [])
        ]
        print(f"  {route}: {expected_model}")
        print(f"    relay: {endpoint}")
        print(f"    reported models: {discovered}")
    except requests.RequestException as exc:
        print(f"  {route}: unavailable ({type(exc).__name__})")

display(
    HTML(
        f'<a href="{DASHBOARD_URL}" target="_blank" rel="noopener" '
        'style="display:inline-block;margin-top:10px;padding:9px 14px;'
        'border:1px solid #888;border-radius:7px;text-decoration:none">'
        "Open vLLM-SR Dashboard</a>"
    )
)
print("Dashboard login:", os.getenv("DASHBOARD_ADMIN_EMAIL", "admin@workshop.local"))
print("Dashboard password:", os.getenv("DASHBOARD_ADMIN_PASSWORD", "workshop2026"))
"""
    ),
    md(
        r"""
### Environment checkpoint

Continue when all six service lines begin with `✓` and both Foundry relay
connections report their expected model.

The application-facing model is:

```text
vllm-sr/auto
```

### If a connection is missing

Do not start a task-model server. The task models remain on Azure Foundry.

Open a Jupyter terminal and run:

```bash
/opt/workshop/bin/start-platform.sh
```

Then inspect the startup log:

```bash
tail -n 100 /workspace/logs/start-platform.log
```

For an individual service:

```bash
tail -n 100 /workspace/logs/router.log
tail -n 100 /workspace/logs/d3-lite.log
tail -n 100 /workspace/logs/foundry-relay.log
tail -n 100 /workspace/logs/dashboard.log
```

If a Foundry relay is missing, confirm that the lab instructions supplied
`FOUNDRY_ENDPOINT` and `FOUNDRY_API_KEY`, then rerun
`/opt/workshop/bin/start-platform.sh`.

Rerun the environment-check cell after the missing connection becomes ready.
"""
    ),
    md(
        r"""
## Section 1 — Route an explicit request

Start with a requirement that needs no model judgment:

> A request marked `[SECURITY-REVIEW]` must use the reasoning route.

<div style="border:2px solid #7749bd;border-radius:12px;padding:15px 18px;margin:16px 0;background:#f8f4ff">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#583094">PROMPT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#24153b">[SECURITY-REVIEW] Our API rotates signing keys every 30 days. During rollout, services accept both the old and new key for 24 hours, and the old key is disabled manually. Review the design and recommend two mitigations.</div>
</div>

The application already supplied the fact. Exact matching is the clearest
policy:

```text
[SECURITY-REVIEW] present
→ keyword signal matches
→ security-review decision
→ Reasoning route

otherwise
→ routine-fallback decision
→ Routine route
```
"""
    ),
    md(
        r"""
### Run the first prompt

The starter recipe is now active. Use the workshop helper to inspect the route
without generating a long task-model answer:
"""
    ),
    code(
        r"""
tagged_security_request = (
    "[SECURITY-REVIEW] Our API rotates signing keys every 30 days. "
    "During rollout, services accept both the old and new key for "
    "24 hours, and the old key is disabled manually. Review the "
    "design and recommend two mitigations."
)

tagged_result = preview_route(tagged_security_request)
"""
    ),
    md(
        r"""
`preview_route` asks the Router which policy path would win and shows the
evidence. It also sends the prompt through the Router once, with a very short
answer, so every request appears in **Dashboard → Insights**. That keeps this
section focused on routing evidence rather than the quality or length of a
generated answer.

Insights shows the requests sent since the last recipe change: applying a
recipe reloads the Router and starts a new list.

The application-facing model name remains `vllm-sr/auto`. A real application
uses the standard chat-completions endpoint shown in the final appendix.

### The minimal working vLLM-SR flow

This first preview contains the smallest useful Router:

```text
PROMPT
→ SIGNAL observes a fact
→ DECISION says what to do when that fact is true
→ ROUTE selects the task model
```

<div style="border:2px solid #e34d59;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fff6f6">
  <div style="font-size:15px;font-weight:800;color:#8d2230">The two essential policy parts</div>
  <div style="margin-top:8px"><b>Signal:</b> observes a fact about the request.</div>
  <div style="margin-top:5px"><b>Decision:</b> turns that fact into an eligible route.</div>
</div>

| Term | Meaning in the first preview |
| --- | --- |
| Prompt | The user text sent to `vllm-sr/auto` |
| Signal | Did the exact `[SECURITY-REVIEW]` marker appear? |
| Decision | If it appeared, make `security-review` eligible |
| Priority | `security-review` outranks the routine fallback |
| Route | Use the Reasoning route |
| Task model | `reasoning-model` would produce the answer |

Signals are not limited to keywords. A Router can use one signal or combine
several, depending on the application:

| Signal family | Example observation |
| --- | --- |
| `keyword` | Does an exact application marker appear? |
| `systemone` | Does the request require comparison or diagnosis? |
| `complexity` | Is the request easy, medium, or hard? |
| `context` | Is the request too large for a model? |
| `metadata` | Did the application label the workload? |
| `pii` | Where does personal information appear? |
| `jailbreak` | Does the prompt look like an attack? |
| `input_modality` | Does the request contain an image or audio? |
| `conversation` | Is this a multi-turn or tool-heavy request? |

Signals can be combined with `AND`, `OR`, and `NOT`. Decisions use priority
when several rules match.

> **Model compatibility matters:** PII commonly needs span extraction. Raw
> D3 Lite supports `noul`, `choice`, and `score`, but not span extraction. A
> span-capable signal model is required before activating a PII recipe.

### Define helper functions

To reduce repeated HTTP code, the next cell defines two small convenience
functions. They are workshop wrappers—not additional vLLM-SR concepts:

```python
preview_route(prompt)   # route without generating an answer
apply_recipe(recipe)    # validate and hot-reload routing policy
```

Both call the real Router management APIs directly.
"""
    ),
    code(
        r"""
def _selected_route(model):
    if model == "routine-model":
        return "Routine route"
    if model == "reasoning-model":
        return "Reasoning route"
    return "Unknown route"


def _preview_selection(body):
    result = body.get("decision_result") or {}
    decision = (
        result.get("decision_name")
        or result.get("decision")
        or result.get("name")
        or body.get("selected_decision")
        or body.get("decision")
    )
    model = (
        result.get("model")
        or result.get("selected_model")
        or body.get("selected_model")
        or body.get("model")
    )
    if isinstance(decision, dict):
        decision = decision.get("name")
    if isinstance(model, dict):
        model = model.get("name")
    return decision, model


def _record_in_insights(prompt):
    # Send the prompt through the Router for real (short answer), so the
    # request is recorded and appears in Dashboard -> Insights.
    try:
        response = requests.post(
            f"{ROUTER_API}/v1/chat/completions",
            json={
                "model": ROUTED_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16,
            },
            timeout=180,
        )
    except requests.RequestException as exc:
        return {"recorded": False, "detail": type(exc).__name__}
    if not response.ok:
        return {"recorded": False, "detail": f"HTTP {response.status_code}"}
    return {
        "recorded": True,
        "decision": response.headers.get("x-vsr-selected-decision"),
    }


def _preview_route(prompt):
    # Internal request used by the public preview and the final scorecard.
    response = requests.post(
        f"{MANAGEMENT_API}/api/v1/routing/preview?trace=true",
        json={"model": ROUTED_MODEL, "text": prompt},
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    decision, model = _preview_selection(body)
    decision_result = body.get("decision_result") or {}
    result = {
        "prompt": prompt,
        "signal_values": body.get("signal_values", {}),
        "matched_signals": decision_result.get("matched_signals", {}),
        "decision": decision,
        "route": _selected_route(model),
        "task_model": model,
        "decision_ranking": body.get("decision_ranking", {}),
        "raw": body,
        "insights": _record_in_insights(prompt),
    }
    return result


def preview_route(prompt):
    # Show the routing evidence; the request is also recorded in Insights.
    result = _preview_route(prompt)
    print("=" * 72)
    print("PROMPT")
    print(" ", prompt)
    print("-" * 72)
    print("Signal evidence:")
    if result["signal_values"]:
        for name, value in result["signal_values"].items():
            if isinstance(value, float):
                value = f"{value:.3f}"
            print(f"  {name} = {value}")
    elif result["matched_signals"]:
        for signal_type, names in result["matched_signals"].items():
            for name in names:
                print(f"  {signal_type}:{name} = matched")
    else:
        print("  no named signal matched; fallback remained eligible")
    print("Decision:", result["decision"])
    runner_up = result["decision_ranking"].get("runner_up")
    if runner_up:
        print(
            "Resolution:",
            f"{result['decision']} won over {runner_up}",
        )
    print("Route:", result["route"])
    print("Task model:", result["task_model"])
    insights = result["insights"]
    if insights["recorded"]:
        print("Dashboard → Insights: recorded as", insights["decision"])
    else:
        print("Dashboard → Insights: not recorded", f"({insights['detail']})")
    print("=" * 72)
    return result


def apply_recipe(recipe):
    # Validate and hot-reload only the default recipe.
    current = requests.get(f"{MANAGEMENT_API}/api/v1/config", timeout=30)
    current.raise_for_status()
    config = current.json()
    etag = current.headers.get("ETag")

    recipes = config.setdefault("recipes", [])
    active_recipe = next(
        (item for item in recipes if item.get("name") == "default"),
        recipes[0] if len(recipes) == 1 else None,
    )
    if active_recipe is None:
        raise RuntimeError("The active configuration has no default recipe.")

    active_recipe["strategy"] = "priority"
    active_recipe["signals"] = copy.deepcopy(recipe.get("signals", {}))
    active_recipe["decisions"] = copy.deepcopy(recipe.get("decisions", []))

    yaml_text = yaml.safe_dump(config, sort_keys=False)
    validation = requests.post(
        f"{MANAGEMENT_API}/api/v1/config/validate",
        json={"yaml": yaml_text},
        timeout=180,
    )
    if validation.status_code != 404:
        validation.raise_for_status()

    headers = {"If-Match": etag} if etag else {}
    update = requests.put(
        f"{MANAGEMENT_API}/api/v1/config",
        headers=headers,
        json={"yaml": yaml_text},
        timeout=180,
    )
    update.raise_for_status()

    expected = {
        decision["name"]
        for decision in recipe.get("decisions", [])
    }
    deadline = time.monotonic() + 180
    last_ready = None
    while time.monotonic() < deadline:
        active = requests.get(
            f"{MANAGEMENT_API}/api/v1/config",
            timeout=30,
        )
        active.raise_for_status()
        active_config = active.json()
        active_recipe = next(
            item
            for item in active_config.get("recipes", [])
            if item.get("name") == "default"
        )
        observed = {
            decision.get("name")
            for decision in active_recipe.get("decisions", [])
        }
        ready_response = requests.get(
            f"{MANAGEMENT_API}/ready",
            timeout=10,
        )
        if ready_response.ok:
            last_ready = ready_response.json()
        if observed == expected and last_ready and last_ready.get("ready") is True:
            print("✓ Recipe validated and activated")
            for decision in sorted(
                recipe.get("decisions", []),
                key=lambda item: item.get("priority", 0),
                reverse=True,
            ):
                models = ", ".join(
                    ref.get("model", "?")
                    for ref in decision.get("modelRefs", [])
                )
                print(
                    f"  {decision.get('priority', 0):>3}  "
                    f"{decision.get('name')} → {models}"
                )
            return active_recipe
        time.sleep(1)

    raise RuntimeError(
        f"The Router did not activate the recipe. Last readiness: {last_ready}"
    )
"""
    ),
    md(
        r"""
### vLLM-SR recipe

A **recipe** groups the signals and decisions for one application entrypoint.
Infrastructure such as listeners, task-model connections, and Dashboard
settings remains outside the recipe.

The first recipe reads as a sentence:

```text
IF the security-review-marker signal matches
THEN the security-review decision enables reasoning-model
OTHERWISE routine-fallback enables routine-model
```

```yaml
signals:
  keywords:
    - name: security-review-marker
      keywords: ["[SECURITY-REVIEW]"]

decisions:
  - name: security-review
    priority: 200
    rules:
      operator: AND
      conditions:
        - type: keyword
          name: security-review-marker
    modelRefs:
      - model: reasoning-model
    algorithm:
      type: static

  - name: routine-fallback
    priority: 100
    rules:
      operator: AND
      conditions: []
    modelRefs:
      - model: routine-model
    algorithm:
      type: static
```

| Recipe field | Purpose |
| --- | --- |
| `signals` | Facts the Router can observe |
| `decisions` | Routes made eligible by those facts |
| `priority` | Resolves overlapping eligible decisions |
| `modelRefs` | Task models available to a decision |
| `algorithm` | Chooses among the decision's eligible models |

The next cell creates and activates that recipe.

Only signals and decisions change; the Foundry model connections remain active.
"""
    ),
    code(
        r"""
keyword_recipe = {
    "signals": {
        "keywords": [
            {
                "name": "security-review-marker",
                "operator": "OR",
                "keywords": ["[SECURITY-REVIEW]"],
                "case_sensitive": False,
            }
        ]
    },
    "decisions": [
        {
            "name": "security-review",
            "description": "Explicit security reviews use the reasoning route.",
            "priority": 200,
            "rules": {
                "operator": "AND",
                "conditions": [
                    {
                        "type": "keyword",
                        "name": "security-review-marker",
                    }
                ],
            },
            "modelRefs": [
                {
                    "model": "reasoning-model",
                    "use_reasoning": True,
                }
            ],
            "algorithm": {"type": "static"},
        },
        {
            "name": "routine-fallback",
            "description": "Everything else uses the routine route.",
            "priority": 100,
            "rules": {"operator": "AND", "conditions": []},
            "modelRefs": [{"model": "routine-model"}],
            "algorithm": {"type": "static"},
        },
    ],
}

apply_recipe(keyword_recipe)
"""
    ),
    md(
        r"""
The tagged prompt already passed. Predict two controls without running that
same prompt again:

| **Prompt** | Prediction |
| --- | --- |
| **Define a security review in one sentence.** | Routine route |
| **Rewrite this clearly: the launch paused while the team checks elevated retries.** | Routine route |
"""
    ),
    code(
        r"""
keyword_control_prompts = [
    "Define a security review in one sentence.",
    "Rewrite this clearly: the launch paused while the team checks elevated retries.",
]

for prompt in keyword_control_prompts:
    preview_route(prompt)
    print()
"""
    ),
    md(
        r"""
The marker includes brackets deliberately. A prompt that merely defines
“security review” should not trigger the reasoning route.

The rule is deterministic:

```text
marker present → reasoning
marker absent  → fallback
```
"""
    ),
    md(
        r"""
## Section 2 — Follow one request through the Router

Reuse `tagged_result` from Section 1—no second Router request is sent. Follow
that captured result through every step:

```text
request text
→ exact marker observed
→ keyword signal matches
→ security-review decision becomes eligible
→ priority 200 beats fallback 100
→ reasoning-model is selected
```
"""
    ),
    md(
        r"""
### Inspect the active recipe

The following is the policy currently active in the Router—not a separate
workshop representation.
"""
    ),
    code(
        r"""
active_config = requests.get(
    f"{MANAGEMENT_API}/api/v1/config",
    timeout=30,
)
active_config.raise_for_status()
active_recipe = next(
    item
    for item in active_config.json()["recipes"]
    if item["name"] == "default"
)
print(yaml.safe_dump(active_recipe, sort_keys=False))
"""
    ),
    md(
        r"""
### Signal and decision checkpoint

At this point you should be able to say:

```text
signal         = observed fact
decision       = application policy using that fact
decision model = model that can supply semantic evidence
task model     = model that answers the user
```

Every later section changes the signal or combines decisions. The basic flow
does not change.
"""
    ),
    md(
        r"""
## Section 3 — See why exact rules are not enough

Now remove the marker while keeping the request reasoning-heavy:

<div style="border:2px solid #7749bd;border-radius:12px;padding:15px 18px;margin:16px 0;background:#f8f4ff">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#583094">PROMPT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#24153b">Our API rotates signing keys every 30 days. During rollout, services accept both the old and new key for 24 hours, and the old key is disabled manually. Identify attack paths, compare mitigations, and recommend a rollout.</div>
</div>

Predict the result before running the cell.
"""
    ),
    code(
        r"""
untagged_security_request = (
    "Our API rotates signing keys every 30 days. During rollout, services "
    "accept both the old and new key for 24 hours, and the old key is disabled "
    "manually. Identify attack paths, compare mitigations, and recommend a rollout."
)

exact_policy_limit = preview_route(untagged_security_request)
"""
    ),
    md(
        r"""
The Router followed the exact policy correctly. The marker was absent, so the
fallback won.

The policy cannot recognize meaning yet. That gives us a reason to introduce a
decision model.
"""
    ),
    md(
        r"""
## Section 4 — Route by meaning with D3 Lite

System One is the typed question interface. D3 Lite is the decision model that
answers the question.

We need only a yes/no question, called `noul`:

<div style="border:2px solid #d39b21;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fffaf0">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#76530c">SYSTEM ONE ROUTING QUESTION</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#3f300d">Does answering this request well require multi-step reasoning, comparison of alternatives, diagnosis, or a justified plan?</div>
</div>

D3 Lite returns the probability of **yes**. Application policy decides what
probability is high enough.
"""
    ),
    code(
        r"""
DECISION_QUESTION = (
    "Does answering this request well require multi-step reasoning, "
    "comparison of alternatives, diagnosis, or a justified plan?"
)

# D3 Lite is zero-shot. Start at 0.50 and calibrate from real application prompts.
DECISION_THRESHOLD = 0.50

semantic_recipe = {
    "signals": {
        "systemone": [
            {
                "name": "needs-deep-reasoning",
                "description": "D3 Lite judges whether deeper reasoning is useful.",
                "question": {
                    "type": "noul",
                    "instructions": DECISION_QUESTION,
                },
                "predicate": {"gte": DECISION_THRESHOLD},
                "timeout_ms": 60000,
            }
        ]
    },
    "decisions": [
        {
            "name": "semantic-reasoning",
            "description": "Meaning indicates that the reasoning route is useful.",
            "priority": 200,
            "rules": {
                "operator": "AND",
                "on_unknown": "no_match",
                "conditions": [
                    {
                        "type": "systemone",
                        "name": "needs-deep-reasoning",
                    }
                ],
            },
            "modelRefs": [
                {
                    "model": "reasoning-model",
                    "use_reasoning": True,
                }
            ],
            "algorithm": {"type": "static"},
        },
        {
            "name": "routine-fallback",
            "description": "Everything else uses the routine route.",
            "priority": 100,
            "rules": {"operator": "AND", "conditions": []},
            "modelRefs": [{"model": "routine-model"}],
            "algorithm": {"type": "static"},
        },
    ],
}

apply_recipe(semantic_recipe)
"""
    ),
    md(
        r"""
### Rerun the request the exact policy could not recognize

The text is unchanged. Only the observation method changed:

```text
before: exact marker
after:  D3 Lite answers a question about meaning
```

<div style="border:2px solid #7749bd;border-radius:12px;padding:15px 18px;margin:16px 0;background:#f8f4ff">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#583094">PROMPT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#24153b">Our API rotates signing keys every 30 days. During rollout, services accept both the old and new key for 24 hours, and the old key is disabled manually. Identify attack paths, compare mitigations, and recommend a rollout.</div>
</div>
"""
    ),
    code(
        r"""
semantic_result = preview_route(untagged_security_request)
print()
routine_control = preview_route(
    "Define token rotation in one sentence for a new engineer."
)
"""
    ),
    md(
        r"""
For the semantic signal:

```text
probability >= threshold → semantic-reasoning matches
probability <  threshold → routine-fallback wins
```

Routing happens before the task model generates an answer.
"""
    ),
    md(
        r"""
### Prompt laboratory

Predict each route. The last two prompts are boundary cases rather than right
or wrong answers.

| Label | **Prompt** | Prediction |
| --- | --- | --- |
| Definition | **Define a software rollback in one sentence.** | Routine route |
| Rewrite | **Rewrite this clearly: the launch paused while checks are running.** | Routine route |
| Checkout diagnosis | **A checkout sometimes charges customers twice after a timeout. Diagnose likely causes, compare three fixes, and recommend a safe rollout.** | Reasoning route |
| Deployment choice | **Compare canary, blue-green, and rolling deployment for a small team. Recommend one and explain the tradeoffs.** | Reasoning route |
| Brief troubleshooting | **Our application became slower after deployment. What should I check first?** | Boundary |
| Teaching example | **Explain a cache with one shopping-cart example and one tradeoff.** | Boundary |
"""
    ),
    code(
        r"""
prompt_lab = [
    {
        "label": "definition",
        "prompt": "Define a software rollback in one sentence.",
        "prediction": "Routine route",
    },
    {
        "label": "rewrite",
        "prompt": "Rewrite this clearly: the launch paused while checks are running.",
        "prediction": "Routine route",
    },
    {
        "label": "checkout diagnosis",
        "prompt": (
            "A checkout sometimes charges customers twice after a timeout. "
            "Diagnose likely causes, compare three fixes, and recommend a safe rollout."
        ),
        "prediction": "Reasoning route",
    },
    {
        "label": "deployment choice",
        "prompt": (
            "Compare canary, blue-green, and rolling deployment for a small team. "
            "Recommend one and explain the tradeoffs."
        ),
        "prediction": "Reasoning route",
    },
    {
        "label": "brief troubleshooting",
        "prompt": "Our application became slower after deployment. What should I check first?",
        "prediction": "Boundary",
    },
    {
        "label": "teaching example",
        "prompt": "Explain a cache with one shopping-cart example and one tradeoff.",
        "prediction": "Boundary",
    },
]

prompt_lab_results = []
for item in prompt_lab:
    print(f"{item['label']} — predicted: {item['prediction']}")
    result = preview_route(item["prompt"])
    prompt_lab_results.append({**item, **result})
    print()
"""
    ),
    md(
        r"""
### Calibrate from evidence

D3 Lite is a zero-shot decision model. Do not copy a threshold from another
model and assume it represents your application.

For production:

1. collect representative requests;
2. label the desired route;
3. preview every request;
4. inspect false positives and false negatives;
5. improve the question before moving the threshold; and
6. record the quality, latency, and capacity tradeoff.

A probability near the threshold is useful evidence. It reveals where the
application requirement needs clarification.
"""
    ),
    md(
        r"""
### Customize the semantic question

Suppose the reasoning route should be used only when a request compares
technical approaches and recommends one.

<div style="border:2px solid #d39b21;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fffaf0">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#76530c">CUSTOM SYSTEM ONE QUESTION</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#3f300d">Does the user ask to compare competing technical approaches and recommend or justify one?</div>
</div>

Test it with:

| **Prompt** | Expected route |
| --- | --- |
| **Compare canary and blue-green deployment for a small team and recommend one.** | Reasoning route |
| **Define blue-green deployment in one sentence.** | Routine route |
| **Why might a deployment fail after a database migration?** | Routine route |
"""
    ),
    code(
        r"""
comparison_recipe = copy.deepcopy(semantic_recipe)
comparison_recipe["signals"]["systemone"][0]["question"]["instructions"] = (
    "Does the user ask to compare competing technical approaches "
    "and recommend or justify one?"
)

apply_recipe(comparison_recipe)

comparison_tests = [
    "Compare canary and blue-green deployment for a small team and recommend one.",
    "Define blue-green deployment in one sentence.",
    "Why might a deployment fail after a database migration?",
]

for prompt in comparison_tests:
    preview_route(prompt)
    print()
"""
    ),
    md(
        r"""
The application requirement changed, so the routing question changed. This is
the main customization skill:

```text
application requirement
→ question D3 Lite can answer
→ representative tests
→ explicit threshold
```
"""
    ),
    code(
        r"""
# Return to the broad semantic question for the remaining workshop.
apply_recipe(semantic_recipe)
"""
    ),
    md(
        r"""
## Section 5 — Combine rules with priority

Semantic judgment is useful, but hard application constraints should remain
exact.

Add:

<div style="border:2px solid #e34d59;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fff6f6">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#8d2230">APPLICATION REQUIREMENT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#43151b">A request marked [PRIVATE] must stay on the Routine route, even if it asks for difficult analysis.</div>
</div>

The private request can match two decisions:

```text
private-local       priority 300
semantic-reasoning  priority 200
routine-fallback    priority 100
```
"""
    ),
    code(
        r"""
private_recipe = copy.deepcopy(semantic_recipe)
private_recipe["signals"]["keywords"] = [
    {
        "name": "private-marker",
        "operator": "OR",
        "keywords": ["[PRIVATE]"],
        "case_sensitive": False,
    }
]
private_recipe["decisions"].insert(
    0,
    {
        "name": "private-local",
        "description": "Private requests must stay on the Routine route.",
        "priority": 300,
        "rules": {
            "operator": "AND",
            "conditions": [
                {
                    "type": "keyword",
                    "name": "private-marker",
                }
            ],
        },
        "modelRefs": [{"model": "routine-model"}],
        "algorithm": {"type": "static"},
    },
)
"""
    ),
    md(
        r"""
### Save the recipe as YAML

Dashboard Builder imports YAML. Save the same recipe used by the Python
management-API path:
"""
    ),
    code(
        r"""
generated_config_dir = Path("/workspace/generated-config")
generated_config_dir.mkdir(parents=True, exist_ok=True)

private_recipe_path = generated_config_dir / "05-private-recipe.yaml"
private_recipe_path.write_text(
    yaml.safe_dump(
        {
            "recipes": [
                {
                    "name": "default",
                    "strategy": "priority",
                    **copy.deepcopy(private_recipe),
                }
            ]
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)

print("Saved Dashboard-ready recipe:")
print(private_recipe_path)
print()
print(private_recipe_path.read_text(encoding="utf-8"))
"""
    ),
    md(
        r"""
## Section 6 — Deploy a vLLM-SR recipe

You can deploy the same recipe in either of two ways.

### Option A — Python and the management API

`apply_recipe(private_recipe)` validates the active configuration and sends a
JSON request to `PUT /api/v1/config`.

### Option B — YAML through Dashboard

1. Open **Routing → Builder**.
2. Select **Import**.
3. Paste or upload `generated-config/05-private-recipe.yaml`.
4. Select **Compile**.
5. Confirm the three decisions and their priorities.
6. Select **Deploy**.

Choose the method below. The default keeps notebook execution automatic:

```python
DEPLOY_METHOD = "python"       # or "dashboard"
```

<div style="border:2px solid #7749bd;border-radius:12px;padding:15px 18px;margin:16px 0;background:#f8f4ff">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#583094">PUBLIC PROMPT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#24153b">Compare three strategies for reducing a service outage, explain their tradeoffs, and recommend a safe rollout.</div>
</div>

<div style="border:2px solid #e34d59;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fff6f6">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#8d2230">PRIVATE PROMPT</div>
  <div style="font-size:17px;font-weight:700;margin-top:6px;color:#43151b">[PRIVATE] Compare three strategies for reducing a service outage, explain their tradeoffs, and recommend a safe rollout.</div>
</div>
"""
    ),
    code(
        r"""
DEPLOY_METHOD = "python"  # change to "dashboard" to deploy the YAML manually

if DEPLOY_METHOD == "python":
    apply_recipe(private_recipe)
elif DEPLOY_METHOD == "dashboard":
    print("Deploy this file in Dashboard, then rerun this cell:")
    print(private_recipe_path)
else:
    raise ValueError("DEPLOY_METHOD must be 'python' or 'dashboard'")

active = requests.get(f"{MANAGEMENT_API}/api/v1/config", timeout=30)
active.raise_for_status()
active_recipe = next(
    item
    for item in active.json().get("recipes", [])
    if item.get("name") == "default"
)
active_decisions = {
    item.get("name")
    for item in active_recipe.get("decisions", [])
}
required_decisions = {
    "private-local",
    "semantic-reasoning",
    "routine-fallback",
}

if not required_decisions.issubset(active_decisions):
    print("The private recipe is not active yet.")
    print("Deploy it in Dashboard, then rerun this cell.")
    private_deployed = False
else:
    private_deployed = True
    public_analysis = (
        "Compare three strategies for reducing a service outage, "
        "explain their tradeoffs, and recommend a safe rollout."
    )
    private_analysis = "[PRIVATE] " + public_analysis

    public_result = preview_route(public_analysis)
    print()
    private_result = preview_route(private_analysis)
"""
    ),
    md(
        r"""
The important result is not merely that the private prompt used
`routine-model`. It is that the trace explains why:

```text
private-local matched
semantic-reasoning may also have matched
priority 300 beat priority 200
```

### Signal example — PII

PII is another signal family. Unlike our yes/no routing question, a useful
PII detector should locate the exact text spans that caused the match.

```yaml
signals:
  pii:
    - name: personal-data
      deployment: vela3-fast
      predicate:
        gte: 0.5
      ignore_labels: []

decisions:
  - name: pii-local
    priority: 400
    rules:
      operator: AND
      conditions:
        - type: pii
          name: personal-data
    modelRefs:
      - model: routine-model
    algorithm:
      type: static
```

`deployment` selects a model for this signal only. `ignore_labels: []` means
that no detected PII category is ignored.

<div style="border:2px solid #d39b21;border-radius:12px;padding:15px 18px;margin:16px 0;background:#fffaf0">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#76530c">OPTIONAL — IF TIME ALLOWS</div>
  <div style="margin-top:7px"><b>Use Vela 3.0 for exact PII spans.</b> D3 Lite
  handles the core <code>noul</code> routing question, but raw D3 Lite does not
  answer <code>span</code> questions. This environment also includes the
  span-capable <code>vela3-fast</code> model. The next cell finds its
  deployment name automatically, adds it to a PII signal, activates the recipe,
  and shows the spans Vela found.</div>
</div>

Use only fictional data in the demonstration prompt.
"""
    ),
    code(
        r"""
# Optional: wire Vela into a PII signal and see the spans it finds.
PII_DEMO_PROMPT = (
    "Demo record: update Jane Doe at jane.doe@example.com "
    "and call 415-555-0134."
)

VELA_PII_SPANS = []

# The Router serves only the models the active recipe uses, so look for Vela
# in the model catalog rather than in the list of models running right now.
catalog = (
    requests.get(f"{MANAGEMENT_API}/api/v1/config", timeout=30)
    .json()
    .get("global", {})
    .get("model_catalog", {})
    .get("deployments", {})
)
VELA_DEPLOYMENT = next(
    (
        name
        for name, deployment in catalog.items()
        if "vela3" in f"{name} {deployment.get('artifact', '')}".lower()
    ),
    None,
)

if VELA_DEPLOYMENT is None:
    print("Optional Vela span extension is not installed on this host; skip it.")
else:
    pii_recipe = copy.deepcopy(private_recipe)
    pii_recipe["signals"]["pii"] = [
        {
            "name": "personal-data",
            "description": "Vela locates personal-data spans in the request.",
            "deployment": VELA_DEPLOYMENT,
            "predicate": {"gte": 0.5},
            "ignore_labels": [],
            "timeout_ms": 60000,
        }
    ]
    pii_recipe["decisions"].insert(
        0,
        {
            "name": "pii-local",
            "description": "Requests containing personal data stay on the Routine route.",
            "priority": 400,
            "rules": {
                "operator": "AND",
                "conditions": [
                    {"type": "pii", "name": "personal-data"}
                ],
            },
            "modelRefs": [{"model": "routine-model"}],
            "algorithm": {"type": "static"},
        },
    )

    pii_recipe_path = generated_config_dir / "06-vela-pii-recipe.yaml"
    pii_recipe_path.write_text(
        yaml.safe_dump(
            {
                "recipes": [
                    {
                        "name": "default",
                        "strategy": "priority",
                        **copy.deepcopy(pii_recipe),
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print("Saved optional Dashboard-ready recipe:")
    print(pii_recipe_path)

    # Activating a recipe that uses Vela is what starts it.
    apply_recipe(pii_recipe)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        deployments = requests.get(
            f"{MANAGEMENT_API}/api/v1/diagnostics/models/systemone",
            timeout=30,
        ).json().get("deployments", [])
        if any(
            item.get("id") == VELA_DEPLOYMENT and item.get("ready")
            for item in deployments
        ):
            break
        time.sleep(2)
    else:
        raise RuntimeError(f"{VELA_DEPLOYMENT} did not become ready.")

    span_response = requests.post(
        f"{MANAGEMENT_API}/api/v1/diagnostics/models/systemone",
        json={
            "deployment": VELA_DEPLOYMENT,
            "request": {
                "state": PII_DEMO_PROMPT,
                "questions": {
                    "personal_data_spans": {
                        "type": "span",
                        "instructions": "Which spans are personal information?",
                        "criteria": [
                            "PERSON",
                            "EMAIL_ADDRESS",
                            "PHONE_NUMBER",
                        ],
                    }
                },
                "options": {"return_meta": True},
            },
        },
        timeout=90,
    )
    span_response.raise_for_status()
    VELA_PII_SPANS = span_response.json().get("spans", {}).get(
        "personal_data_spans",
        [],
    )

    print()
    print("Vela deployment:", VELA_DEPLOYMENT)
    print("PROMPT")
    print(" ", PII_DEMO_PROMPT)
    print("Detected spans:")
    for span in VELA_PII_SPANS:
        print(
            f"  {span['label']:14} {span['text']!r} "
            f"characters {span['start']}:{span['end']} "
            f"score={span['probability']:.3f}"
        )
"""
    ),
    md(
        r"""
Activating the recipe is what started Vela: the Router serves only the models
that the active policy uses. The span call above asked Vela directly. The next
cell sends prompts through the routing policy itself:

```text
PROMPT
→ Vela locates PII spans
→ personal-data signal matches
→ pii-local decision wins by priority
→ Routine route
```
"""
    ),
    code(
        r"""
# Optional: route the PII prompt and a clean control.
if VELA_DEPLOYMENT is None:
    print("Skip this cell because Vela is not installed on this host.")
else:
    pii_route_result = preview_route(PII_DEMO_PROMPT)
    print()
    clean_route_result = preview_route(
        "Explain signing-key rotation in one sentence."
    )
"""
    ),
    md(
        r"""
The PII prompt should select `pii-local`; the clean control should select
`routine-fallback`. Both may use the same task-model route, but for different
policy reasons.

The explicit `deployment` changes only the PII signal. Signals without one
continue using the configured default decision model. The final challenge
below rebuilds its recipe, so running this optional extension does not change
the challenge.
"""
    ),
    md(
        r"""
## Final challenge — Keep Launch Control green

It is 02:00 UTC during a production launch. Six requests arrive through the
same endpoint.

Your policy must satisfy four requirements:

1. `[PRIVATE]` must stay on the Routine route.
2. `[SECURITY-REVIEW]` should use the Reasoning route unless privacy also matches.
3. Untagged requests needing comparison, diagnosis, or a justified plan should
   use semantic reasoning.
4. Everything else should use the Routine route.

The hardest request matches all three specific policies:

<div style="border:3px solid #e34d59;border-radius:12px;padding:16px 19px;margin:16px 0;background:#fff6f6">
  <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#8d2230">THREE-WAY COLLISION PROMPT</div>
  <div style="font-size:17px;font-weight:800;margin-top:6px;color:#43151b">[PRIVATE] [SECURITY-REVIEW] Investigate leaked credentials, compare containment strategies, and recommend a rollout.</div>
</div>

Choose priorities for:

```text
private-local
security-review
semantic-reasoning
routine-fallback (already 100)
```

Then choose how to deploy:

```text
python     → apply the recipe through the management API
dashboard  → import the generated YAML in Routing → Builder
```
"""
    ),
    code(
        r"""
# Replace None with priorities that express the requirements.
PRIVATE_PRIORITY = None
SECURITY_PRIORITY = None
SEMANTIC_PRIORITY = None
CHALLENGE_DEPLOY_METHOD = "python"  # or "dashboard"

if None in (PRIVATE_PRIORITY, SECURITY_PRIORITY, SEMANTIC_PRIORITY):
    print("Choose all three priorities, then rerun this cell.")
    print("The routine fallback already has priority 100.")
    launch_recipe = None
    launch_recipe_path = None
else:
    launch_recipe = copy.deepcopy(semantic_recipe)
    launch_recipe["signals"]["keywords"] = [
        {
            "name": "private-marker",
            "operator": "OR",
            "keywords": ["[PRIVATE]"],
            "case_sensitive": False,
        },
        {
            "name": "security-review-marker",
            "operator": "OR",
            "keywords": ["[SECURITY-REVIEW]"],
            "case_sensitive": False,
        },
    ]
    launch_recipe["decisions"] = [
        {
            "name": "private-local",
            "description": "Private requests must stay on the Routine route.",
            "priority": PRIVATE_PRIORITY,
            "rules": {
                "operator": "AND",
                "conditions": [
                    {"type": "keyword", "name": "private-marker"}
                ],
            },
            "modelRefs": [{"model": "routine-model"}],
            "algorithm": {"type": "static"},
        },
        {
            "name": "security-review",
            "description": "Explicit security reviews use the Reasoning route.",
            "priority": SECURITY_PRIORITY,
            "rules": {
                "operator": "AND",
                "conditions": [
                    {
                        "type": "keyword",
                        "name": "security-review-marker",
                    }
                ],
            },
            "modelRefs": [
                {
                    "model": "reasoning-model",
                    "use_reasoning": True,
                }
            ],
            "algorithm": {"type": "static"},
        },
        {
            **copy.deepcopy(semantic_recipe["decisions"][0]),
            "priority": SEMANTIC_PRIORITY,
        },
        copy.deepcopy(semantic_recipe["decisions"][1]),
    ]

    launch_recipe_path = (
        generated_config_dir / "launch-control-recipe.yaml"
    )
    launch_recipe_path.write_text(
        yaml.safe_dump(
            {
                "recipes": [
                    {
                        "name": "default",
                        "strategy": "priority",
                        **copy.deepcopy(launch_recipe),
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print("Saved Launch Control recipe:")
    print(launch_recipe_path)

    if CHALLENGE_DEPLOY_METHOD == "python":
        apply_recipe(launch_recipe)
    elif CHALLENGE_DEPLOY_METHOD == "dashboard":
        print()
        print("Import this YAML in Dashboard → Routing → Builder.")
        print("Compile and Deploy it, then run the scorecard.")
    else:
        raise ValueError(
            "CHALLENGE_DEPLOY_METHOD must be 'python' or 'dashboard'"
        )
"""
    ),
    md(
        r"""
<details>
<summary><b>Hint 1 — reason from constraints</b></summary>

Privacy is a hard boundary, so it must outrank every route that can send a
request to the reasoning model.

The explicit security-review rule should outrank the general semantic rule.

</details>

<details>
<summary><b>Hint 2 — required ordering</b></summary>

```text
private-local
> security-review
> semantic-reasoning
> routine-fallback
```

You choose the numeric values.

</details>
"""
    ),
    md(
        r"""
### Launch Control test traffic

The scorecard verifies both the decision and task model.

| Case | **Prompt** | Required decision |
| --- | --- | --- |
| Launch update | **Rewrite this launch update clearly: rollout paused at 40 percent while the team checks elevated retry volume.** | `routine-fallback` |
| Architecture | **Compare canary, blue-green, and rolling deployment. Recommend one and justify rollback criteria.** | `semantic-reasoning` |
| Security review | **`[SECURITY-REVIEW]` Our API accepts old and new signing keys for 24 hours during rotation. Identify attack paths and recommend mitigations.** | `security-review` |
| Private note | **`[PRIVATE]` Summarize an overdue-invoice note.** | `private-local` |
| Private analysis | **`[PRIVATE]` Compare customer-recovery options and recommend a rollout.** | `private-local` |
| Three-way collision | **`[PRIVATE] [SECURITY-REVIEW]` Investigate leaked credentials and recommend a rollout.** | `private-local` |
"""
    ),
    code(
        r"""
launch_cases = {
    "launch_update": {
        "prompt": (
            "Rewrite this launch update clearly: rollout paused at 40 percent "
            "while the team checks elevated retry volume."
        ),
        "decision": "routine-fallback",
        "model": "routine-model",
    },
    "architecture": {
        "prompt": (
            "Compare canary, blue-green, and rolling deployment for this "
            "service. Recommend one and justify rollback criteria."
        ),
        "decision": "semantic-reasoning",
        "model": "reasoning-model",
    },
    "security_review": {
        "prompt": (
            "[SECURITY-REVIEW] Our API accepts old and new signing keys for "
            "24 hours during rotation. Identify attack paths and recommend mitigations."
        ),
        "decision": "security-review",
        "model": "reasoning-model",
    },
    "private_note": {
        "prompt": (
            "[PRIVATE] ACCOUNT-ID 4821: summarize this payment note in one "
            "sentence: the invoice is 12 days overdue."
        ),
        "decision": "private-local",
        "model": "routine-model",
    },
    "private_analysis": {
        "prompt": (
            "[PRIVATE] Compare three customer-recovery options, explain their "
            "tradeoffs, and recommend a rollout."
        ),
        "decision": "private-local",
        "model": "routine-model",
    },
    "three_way_collision": {
        "prompt": (
            "[PRIVATE] [SECURITY-REVIEW] Investigate leaked credentials, "
            "compare containment strategies, and recommend a rollout."
        ),
        "decision": "private-local",
        "model": "routine-model",
    },
}

active = requests.get(f"{MANAGEMENT_API}/api/v1/config", timeout=30)
active.raise_for_status()
active_recipe = next(
    item
    for item in active.json().get("recipes", [])
    if item.get("name") == "default"
)
active_decisions = {
    item.get("name")
    for item in active_recipe.get("decisions", [])
}
launch_decisions = {
    "private-local",
    "security-review",
    "semantic-reasoning",
    "routine-fallback",
}

if launch_recipe is None:
    print("Build and activate the Launch Control recipe first.")
    launch_score = None
elif not launch_decisions.issubset(active_decisions):
    print("The Launch Control recipe is not active yet.")
    print("Deploy the generated YAML in Dashboard, then rerun this cell:")
    print(launch_recipe_path)
    launch_score = None
else:
    passed = 0
    launch_results = {}
    for name, case in launch_cases.items():
        observed = _preview_route(case["prompt"])
        ok = (
            observed["decision"] == case["decision"]
            and observed["task_model"] == case["model"]
        )
        passed += int(ok)
        launch_results[name] = observed
        marker = "✓" if ok else "✗"
        print(
            f"{marker} {name:20} "
            f"{observed['decision']} → {observed['task_model']}"
        )

    launch_score = {
        "passed": passed,
        "total": len(launch_cases),
        "results": launch_results,
    }
    print()
    print(f"Score: {passed}/{len(launch_cases)}")
    if passed == len(launch_cases):
        print("Completion code: ROUTE-CONTROL-GREEN")
"""
    ),
    md(
        r"""
Launch Control is green only when the notebook prints:

```text
Score: 6/6
Completion code: ROUTE-CONTROL-GREEN
```

Explain the three-way collision:

```text
which facts matched
→ which decisions were eligible
→ why private-local won
→ which task model served the request
```
"""
    ),
    code(
        r"""
if launch_score and launch_score["passed"] == launch_score["total"]:
    collision = preview_route(
        launch_cases["three_way_collision"]["prompt"]
    )

    export_dir = Path("/workspace/generated-config/my-semantic-router")
    export_dir.mkdir(parents=True, exist_ok=True)

    active = requests.get(
        f"{MANAGEMENT_API}/api/v1/config",
        timeout=30,
    )
    active.raise_for_status()
    export_config = active.json()

    catalog = (
        export_config
        .setdefault("global", {})
        .setdefault("model_catalog", {})
    )
    catalog["deployments"] = {
        "d3-lite": {
            "provider": "model_runtime",
            "artifact": "vllm-sr/d3-lite",
            "device": "auto",
            "public_name": "d3-lite",
        }
    }
    catalog["system"] = {
        "decision_model": {"deployment": "d3-lite"}
    }

    (export_dir / "config.yaml").write_text(
        yaml.safe_dump(export_config, sort_keys=False),
        encoding="utf-8",
    )
    (export_dir / "routing-tests.yaml").write_text(
        yaml.safe_dump(
            {
                "model": ROUTED_MODEL,
                "cases": [
                    {
                        "name": name,
                        "prompt": case["prompt"],
                        "expected_decision": case["decision"],
                        "expected_model": case["model"],
                    }
                    for name, case in launch_cases.items()
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    start_script = export_dir / "start.sh"
    start_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "vllm-sr config validate --config config.yaml\n"
        "vllm-sr serve --config config.yaml\n",
        encoding="utf-8",
    )
    start_script.chmod(0o755)
    (export_dir / "README.md").write_text(
        "# My Semantic Router\n\n"
        "1. Update the two task-model endpoints in config.yaml.\n"
        "2. Run ./start.sh.\n"
        "3. Run the prompts in routing-tests.yaml.\n",
        encoding="utf-8",
    )
    print("Exported:", export_dir)
"""
    ),
    md(
        r"""
## Workshop complete

You built one policy from the smallest mechanism to a semantic Router:

```text
exact application fact
→ keyword signal
→ decision
→ route

natural-language meaning
→ System One question
→ D3 Lite probability
→ decision
→ route

overlapping rules
→ priority
→ one winning route
```

The learning goal is not memorizing YAML. It is translating an application
requirement into observable, testable routing behavior.
"""
    ),
    md(
        r"""
<details>
<summary><b>Optional deep dive — other D3 Lite question types</b></summary>

The core workshop used `noul`, a yes/no question. D3 Lite can also answer:

| Type | Meaning | Example |
| --- | --- | --- |
| `choice` | Pick one option | Which task model should answer? |
| `score` | Position on an ordered scale | How difficult is this? |
| `set` | Evaluate several labels | Which capabilities are needed? |

Raw D3 Lite does not perform span extraction. Use a span-capable model when the
application must locate exact text such as PII spans.

</details>
"""
    ),
    md(
        r"""
## Appendix — Run your own Router

After Launch Control:

```bash
cd /workspace/generated-config/my-semantic-router
```

Edit only the task-model entries in `config.yaml`:

```text
provider_model_id
backend_refs[].endpoint
```

Then run:

```bash
./start.sh
```

Verify:

```bash
curl http://127.0.0.1:8080/ready
curl http://127.0.0.1:8898/v1/models
```

Send an application request:

```bash
curl http://127.0.0.1:8898/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "vllm-sr/auto",
    "messages": [
      {"role": "user", "content": "Compare two deployment strategies."}
    ]
  }'
```

The same configuration can be deployed through Docker or Kubernetes after
replacing the workshop task-model endpoints.
"""
    ),
]


def one_cell_containing(marker: str):
    matches = [cell for cell in cells if marker in cell.source]
    if len(matches) != 1:
        raise RuntimeError(f"{marker!r}: expected one cell, found {len(matches)}")
    return matches[0]


# Define the two reusable HTTP helpers once, then begin Section 1. The visible
# participant-authored recipe must be active before the prompt is previewed.
# Keep the terminology walkthrough immediately after that one successful
# preview.
section_one = one_cell_containing("## Section 1 — Route an explicit request")
send_intro = one_cell_containing("### Run the first prompt")
send_request = one_cell_containing(
    "tagged_result = preview_route(tagged_security_request)"
)
flow_and_helpers = one_cell_containing("### The minimal working vLLM-SR flow")
helper_code = one_cell_containing("def _selected_route(model):")
recipe_intro = one_cell_containing("### vLLM-SR recipe")
recipe_code = one_cell_containing("keyword_recipe = {")

flow_source, helper_source = flow_and_helpers.source.split(
    "### Define helper functions",
    1,
)
flow_walkthrough = md(flow_source)
helper_intro = md("### Define helper functions" + helper_source)

section_start = cells.index(section_one)
section_end = cells.index(recipe_code)
cells[section_start : section_end + 1] = [
    helper_intro,
    helper_code,
    section_one,
    recipe_intro,
    recipe_code,
    send_intro,
    send_request,
    flow_walkthrough,
]


notebook = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3",
        },
    },
)
nbf.write(notebook, OUTPUT)
print(f"Wrote {OUTPUT} ({len(cells)} cells)")

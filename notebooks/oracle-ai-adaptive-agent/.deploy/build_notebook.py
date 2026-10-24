#!/usr/bin/env python3
"""Generate the final workshop-style ReviewBench/OpenClaw notebook."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "workshop.ipynb"


def lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(text)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(text),
    }


cells = [
    md(
        """# Build the Review Team, Route the Work

## Multi-Agent OpenClaw with vLLM Semantic Router on AMD GPUs

---

## What You'll Learn Today

You're going to build a real multi-agent code-review team with **OpenClaw** and
connect the whole team to one model name:

```text
vllm-sr/auto
```

Then you'll watch **vLLM Semantic Router** choose a different model and
reasoning effort for each part of the workflow.

### The Steps

**0. Setup**
Connect securely to the prebuilt vLLM-SR endpoint and load the frozen public PR.

**1. Meet your OpenClaw agent**
See the coordinator workspace and the operating rules that make the agent persistent.

**2. Meet the pull request**
Inspect a real public Go change with multiple correctness and performance risks.

**3. Build the review team**
Create correctness, reliability, and integration specialists and let `main`
coordinate them.

**4. Route the work**
Run the same capable team through `vllm-sr/auto` and inspect every model choice
in the Dashboard.

**5. The challenge**
Apply the same review team to a second public PR and predict its route mix and cost.

### What You'll Walk Away With

- A working OpenClaw multi-agent review architecture
- A public, reproducible PR review workload
- One OpenAI-compatible application endpoint
- Visible model and reasoning-effort decisions
- A measured compute comparison against an all-GLM policy
- A reusable pattern for routing other agentic workflows
"""
    ),
    md(
        """---
## Section 0: Setup

Connect any OpenAI-compatible endpoint. To reproduce the routing results in
this workshop, use an endpoint that exposes the `decision-balance` recipe
through a model such as `vllm-sr/auto`.

Configuration is read from:

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
VLLM_SR_DASHBOARD_URL   optional
```

When no endpoint is configured, the notebook loads the included measured
results so the complete workshop remains readable.
"""
    ),
    code(
        """import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
ARTIFACTS = ROOT / ".deploy" / "artifacts"

summary = json.loads(
    (ARTIFACTS / "reviewbench-demo-summary.json").read_text()
)
packet = json.loads((ARTIFACTS / "task-packet.json").read_text())

print("Workshop:", "Build the Review Team, Route the Work")
print("Requested model:", summary["requested_model"])
print("Routing recipe:", summary["recipe"])
"""
    ),
    md(
        """### Configure an OpenAI-compatible endpoint

You can export the variables before starting Jupyter or edit the values in the
next cell. API keys are read with `getpass` and are never printed.
"""
    ),
    code(
        """import getpass

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "vllm-sr/auto").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
VLLM_SR_DASHBOARD_URL = os.getenv("VLLM_SR_DASHBOARD_URL", "").strip()

if OPENAI_BASE_URL and not OPENAI_API_KEY:
    OPENAI_API_KEY = getpass.getpass(
        "OpenAI-compatible endpoint key: "
    ).strip()

endpoint_ready = bool(OPENAI_BASE_URL and OPENAI_API_KEY and OPENAI_MODEL)

if endpoint_ready:
    print("Endpoint configured:", OPENAI_BASE_URL)
    print("Model:", OPENAI_MODEL)
else:
    print("No endpoint configured. Included measured results are available.")
"""
    ),
    md(
        """### Check the measured workflow contract

The application always asks for one model:

```text
vllm-sr/auto
```

No OpenClaw agent names a physical backend.
"""
    ),
    code(
        """[
    {
        "phase": row["display"],
        "decision": row["decision"],
        "model": row["model"],
        "reasoning": row["reasoning"],
    }
    for row in summary["rows"]
]
"""
    ),
    md(
        """You should see three physical model families appear:

```text
Qwen3.8-27B
Qwen3.8-Flash-Next
GLM-5.3-Flash
```

That model mix comes from the included measured workflow.
"""
    ),
    md(
        """---
## Section 1: Meet your OpenClaw agent

OpenClaw is the application and orchestration layer. It owns:

- agent identities;
- workspace instructions;
- tools;
- delegation;
- child sessions;
- conversation state;
- final responses.

vLLM-SR sits beneath OpenClaw and decides which model should handle each
inference request.
"""
    ),
    md(
        """### Connect OpenClaw to one model name

In the prepared environment, OpenClaw uses a custom OpenAI-compatible provider:

```bash
openclaw onboard --non-interactive \
  --mode local \
  --auth-choice custom-api-key \
  --custom-base-url http://127.0.0.1:19090/v1 \
  --custom-model-id "$OPENAI_MODEL" \
  --custom-provider-id vllm-sr
```

The local URL is a sanitizing proxy. It forwards requests to your configured
endpoint while recording route, usage, latency, and relative cost—never the key.
"""
    ),
    code(
        """openclaw_provider = {
    "provider": "vllm-sr",
    "base_url": "http://127.0.0.1:19090/v1",
    "model": OPENAI_MODEL,
}
openclaw_provider
"""
    ),
    md(
        """### 🖥️ Meet your agent

In a terminal, OpenClaw's TUI starts with:

```bash
openclaw tui
```

Whenever you see the 🦞 icon in this workshop, that instruction is sent to an
OpenClaw agent.
"""
    ),
    md(
        """### 👀 Behind the scenes

Each specialist has its own workspace and operating manual:

```text
review-team/
├── main/
├── rb_correctness/
├── rb_reliability/
└── rb_integration/
```

The reviewers are intentionally tool-free. They receive a complete frozen
review packet from the coordinator, so they can reason about code without
re-reading the same repository independently.
"""
    ),
    code(
        """review_agents = {
    "main": "coordinate triage, delegation, and reporting",
    "rb_correctness": "correctness, security, testing",
    "rb_reliability": "reliability, performance, API behavior",
    "rb_integration": "call ordering, state mutation, cross-file behavior",
}
review_agents
"""
    ),
    md(
        """---
## Section 2: Meet the Pull Request

The review target is a frozen public PR:

```text
k1LoW/gh-copilot-review#9
```

It changes logic that decides whether GitHub Copilot has already reviewed the
current pull-request head.

Why this PR works well:

- two changed files;
- a small readable diff;
- exact external API semantics;
- pagination and performance concerns;
- a high-severity cross-function ordering issue.
"""
    ),
    code(
        """task = packet["task"]
{
    "repository": task["nwo"],
    "pr_number": task["pr_number"],
    "title": task["title"],
    "language": task["language"],
    "changed_files": packet["changed_files"],
    "lines_added": task["lines_added"],
    "lines_removed": task["lines_removed"],
}
"""
    ),
    md(
        """### Inspect the proposed change

The reviewers see the same base-to-head diff and line-numbered head files.
They do not receive upstream comments, later fixes, or golden findings.
"""
    ),
    code(
        """print(packet["diff"][:5000])
"""
    ),
    md(
        """Before building the panel, ask the audience:

> What kinds of review expertise would you want before merging this change?

The answer becomes the agent roster.
"""
    ),
    md(
        """---
## Section 3: Build the OpenClaw Review Team

The coordinator creates three independent review lanes:

```text
                         main
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   correctness       reliability      integration
    / security       / performance    / control flow
```

Each reviewer gets one narrow job. Narrow jobs make outputs easier to merge and
let vLLM-SR recognize the code-review workload.
"""
    ),
    md(
        """### Step 1: Add the specialist agents

The setup script creates isolated OpenClaw agents and assigns the same virtual
model to all of them:

```bash
python3 .deploy/bin/setup_openclaw_agents.py \
  --state-dir /tmp/reviewbench-openclaw-state \
  --workspace-root /tmp/reviewbench-openclaw-agents
```

Every agent requests `vllm-sr/auto`.
"""
    ),
    code(
        """setup_command = [
    sys.executable,
    str(ROOT / ".deploy/bin/setup_openclaw_agents.py"),
    "--state-dir",
    "/tmp/reviewbench-openclaw-state",
    "--workspace-root",
    "/tmp/reviewbench-openclaw-agents",
    "--model",
    OPENAI_MODEL,
]

if endpoint_ready:
    subprocess.run(setup_command, check=True)
else:
    print("Set OPENAI_BASE_URL and OPENAI_API_KEY to configure agents.")
"""
    ),
    md(
        """### Step 2: Let `main` delegate

`main` uses OpenClaw's child-session tools:

```text
sessions_spawn(agentId="rb_correctness",
               context="isolated",
               completionTarget="parent")

sessions_spawn(agentId="rb_reliability",
               context="isolated",
               completionTarget="parent")

sessions_spawn(agentId="rb_integration",
               context="isolated",
               completionTarget="parent")

sessions_yield()
```

The children return privately to `main`. A Gateway can run the three reviewers
concurrently. Embedded OpenClaw serializes local writes because it uses one
SQLite owner.
"""
    ),
    code(
        """review_protocol = {
    "context": "isolated",
    "completionTarget": "parent",
    "agents": ["rb_correctness", "rb_reliability", "rb_integration"],
    "execution": "parallel under Gateway; serialized in embedded mode",
}
review_protocol
"""
    ),
    md(
        """### Step 3: Give each reviewer one job

| Agent | Review lens |
| --- | --- |
| `rb_correctness` | Behavioral bugs, security, and missing tests |
| `rb_reliability` | Performance, duplicate calls, and operational failures |
| `rb_integration` | Call ordering, state mutation, and early-return hazards |

The final output uses a strict findings contract:

```json
{
  "file": "internal/github/github.go",
  "start_line": 84,
  "end_line": 91,
  "message": "Specific actionable issue and why it matters."
}
```
"""
    ),
    md(
        """### Step 4: Run the review panel

The workshop harness mirrors the OpenClaw delegation protocol and emits one
deduplicated findings file.
"""
    ),
    code(
        """if endpoint_ready:
    live_dir = ROOT / ".deploy" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    proxy_env = {
        **os.environ,
        "OPENAI_BASE_URL": OPENAI_BASE_URL,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "OPENAI_MODEL": OPENAI_MODEL,
    }

    proxy = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / ".deploy/bin/logging_proxy.py"),
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            "19090",
            "--base-url",
            OPENAI_BASE_URL,
            "--log-jsonl",
            str(live_dir / "routes.jsonl"),
        ],
        env=proxy_env,
    )
    time.sleep(2)

    panel_dir = live_dir / "panel"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / ".deploy/bin/run_openclaw_panel.py"),
            "--packet",
            str(ARTIFACTS / "task-packet.json"),
            "--output-dir",
            str(panel_dir),
            "--state-dir",
            "/tmp/reviewbench-openclaw-state",
        ],
        check=True,
    )
    findings = json.loads((panel_dir / "findings.json").read_text())
else:
    findings = json.loads(
        (ARTIFACTS / "findings.json").read_text()
    )

findings
"""
    ),
    md(
        """### 👀 What just happened

Three OpenClaw agents reviewed the same PR independently:

- The correctness reviewer found pagination and freshness bugs.
- The reliability reviewer found redundant API requests and failure modes.
- The integration reviewer found the high-severity ordering bug.

The host removed duplicate findings deterministically. It did not spend another
model call only to reformat JSON.
"""
    ),
    code(
        """[
    {
        "file": item["file"],
        "lines": f"{item['start_line']}-{item['end_line']}",
        "finding": item["message"],
    }
    for item in findings["findings"]
]
"""
    ),
    md(
        """---
## Section 4: Route the Work with vLLM Semantic Router

Now that the OpenClaw team works, inspect how its inference was allocated.

The current `decision-balance` recipe gives us these useful lanes:

| Decision | Intended work |
| --- | --- |
| `fast` | Short requests that need little reasoning |
| `agentic` | Tool use, files, systems, and active tool loops |
| `facts` | Exact facts that are easy to misremember |
| `code` | Code writing, review, and debugging |
| `hard` / `frontier` | High-effort reasoning |
| `recovery` | Correct a prior answer with stronger effort |
"""
    ),
    md(
        """### Open the vLLM-SR Dashboard

If your endpoint provides the vLLM-SR Dashboard, open the URL configured in
`VLLM_SR_DASHBOARD_URL` beside the notebook.

Open **Insights** and watch the newest records. If no Dashboard URL is
configured, use the route table captured by the local proxy.

Before revealing each record, ask:

> Which model and effort should this phase receive?
"""
    ),
    code(
        """[
    {
        "phase": row["display"],
        "decision": row["decision"],
        "model": row["model"],
        "reasoning": row["reasoning"],
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "cost_xxx": row["relative_cost_xxx"],
    }
    for row in summary["rows"]
]
"""
    ),
    md(
        """### The route reveal

```text
Coordinator plan   → fast    → 27B          → thinking off
Repository triage  → agentic → GLM          → high effort
Code reviewers     → code    → Flash-Next   → medium effort
Exact API check    → facts   → GLM          → low effort
Final report       → fast    → 27B          → thinking off
```

OpenClaw requested only `vllm-sr/auto`.
"""
    ),
    md(
        """### Compare compute

![Measured routed cost versus all-GLM token-equivalent](.deploy/artifacts/reviewbench-cost.svg)
"""
    ),
    code(
        """summary["totals"]
"""
    ),
    md(
        """Measured rehearsal result:

```text
Calls:                         7
Prompt tokens:                24,327
Completion tokens:             8,258
Reasoning tokens:              6,449
vllm-sr/auto measured cost:    0.02136 XXX
all-GLM token-equivalent:      0.04651 XXX
estimated reduction:           54.1%
```

`XXX` is a relative GPU-cost unit, not dollars.

The routed value is measured. The all-GLM value remains an estimate until the
static `vllm-sr/all-glm` baseline is run.
"""
    ),
    md(
        """---
## Section 5: The Challenge

You've built one review team. Now make the routing policy prove itself on a
different public change.

### Your mission

1. Pick one task from `reviewbench/selected-tasks.json`.
2. Predict the route for every OpenClaw phase.
3. Run the same agent roster without changing its prompts.
4. Open Dashboard Insights.
5. Record model, effort, tokens, and relative cost.
6. Compare the result with an all-GLM policy.

Good starting tasks:

```text
AA-Factory/aafactory-prototype#17        Python
brexhq/CrabTrap#15                      Go
allan-mobley-jr/gimmes#468              Python
Marvell-Consulting/statswales-frontend#626 TypeScript
```
"""
    ),
    md(
        """<details>
<summary>💡 Hint 1 — Preserve the experiment</summary>

Keep these fixed:

- agent roster;
- prompts;
- review packet;
- output contract;
- generation limits.

Change only the inference policy.

</details>

<details>
<summary>💡 Hint 2 — Make the route visible</summary>

Track:

```text
phase
decision
selected model
reasoning effort
prompt tokens
completion tokens
relative cost
```

</details>

<details>
<summary>💡 Hint 3 — Trigger recovery honestly</summary>

If one finding is incorrect, continue the same conversation:

```text
That finding is wrong because <evidence>. Correct the review.
```

The `recovery` lane should move the correction to GLM at maximum effort.

</details>
"""
    ),
    md(
        """### The goal

A capable OpenClaw review team running through one stable endpoint:

```text
OpenClaw team
     |
     v
vllm-sr/auto
     |
     +--> 27B/off for cheap coordination
     +--> Flash-Next/medium for code review
     +--> GLM/high for tools
     +--> GLM/low for exact facts
     +--> GLM/max only for recovery
```

The team stays capable. The inference policy becomes efficient.
"""
    ),
    md(
        """## Your Mission

Build the OpenClaw review team, run it on a frozen public PR, and use the
vLLM-SR Dashboard to explain every model and reasoning-effort decision.

Then answer one question:

> Which calls truly needed the strongest model, and how much compute did the
> router avoid spending on the rest?
"""
    ),
]

for index, cell in enumerate(cells):
    cell["id"] = f"styled-rb-{index:02d}"

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
        "workshop": {
            "title": "Build the Review Team, Route the Work",
            "generated": "2026-10-24",
            "recipe": "decision-balance",
            "style_reference": "notebooks/open-claw/workshop.ipynb",
            "requested_model": "vllm-sr/auto",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

TARGET.write_text(json.dumps(notebook, indent=1) + "\n")
print(TARGET)

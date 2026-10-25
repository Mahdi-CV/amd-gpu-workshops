#!/usr/bin/env python3
"""Generate the baked-runtime OpenClaw + vLLM-SR workshop notebook."""

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
        """# Build an OpenClaw Debugging Team

## Route Every Role with vLLM Semantic Router

This workshop has two goals:

1. Build and operate a visible OpenClaw multi-agent team.
2. Show how one `vllm-sr/auto` endpoint assigns model capability per role.

```text
bug_reviewer   focused code diagnosis
test_reviewer  focused regression reasoning
fixer          file editing and pytest
main           one-sentence verified report
```

Expected Decision Balance routes:

```text
reviewers → code    → Qwen3.8-Flash-Next
fixer     → agentic → GLM-5.3-Flash
reporter  → fast    → Qwen3.8-27B, thinking off
```

The Docker runtime already contains OpenClaw, the fixture, endpoint proxy,
state paths, and lifecycle scripts. The notebook contains only workshop actions.
"""
    ),
    md(
        """---
## Section 0 — Ready Check

One cell verifies the baked runtime. It does not print or read endpoint keys.
"""
    ),
    code(
        """from workshop_lab import lab

runtime_status = lab.check_ready()
"""
    ),
    md(
        """The Gateway is intentionally stopped during team creation. It will be
started once, immediately before the TUI exercise.
"""
    ),
    md(
        """---
## Section 1 — Meet the Bug

Reset the frozen `open_type_faster` project and prove its starting state.
"""
    ),
    code(
        """baseline = lab.baseline_demo()
"""
    ),
    md(
        """Expected:

```text
5 failed, 102 passed
```

The quality gate at the end is exactly:

```text
107 passed
```
"""
    ),
    code(
        """stats_text = (lab.demo_repo / "stats.py").read_text()
start = stats_text.index("def _accuracy")
end = stats_text.index("\\ndef _count_correct", start)
print(stats_text[start:end])
"""
    ),
    md(
        """---
## Section 2 — Build the OpenClaw Team

This creates three isolated agents and specializes `main` as the reporter.

The helper prints every `openclaw agents add` and `openclaw config set` command,
so the mechanics remain visible.
"""
    ),
    code(
        """role_files = lab.add_team()

for agent_id, instructions in role_files.items():
    print("=" * 72)
    print(agent_id)
    print("=" * 72)
    print(instructions[:1800])
    print()
"""
    ),
    md(
        """Tool policy is ordinary OpenClaw least privilege:

| Agent | Profile | Why |
| --- | --- | --- |
| `bug_reviewer` | `minimal` | Complete artifact is supplied |
| `test_reviewer` | `minimal` | Complete contract is supplied |
| `fixer` | `coding` | Must read, edit, and run tests |
| `main` | `minimal` | Receives the verified result |

Every agent uses the same normal provider and requests `vllm-sr/auto`.
"""
    ),
    md(
        """### Start the Gateway once
"""
    ),
    code(
        """gateway_pid = lab.start_gateway()
print("Gateway PID:", gateway_pid)
print()
print("Open a Jupyter terminal and run:")
print(f'OPENCLAW_STATE_DIR="{lab.state}" openclaw tui')
"""
    ),
    md(
        """Keep this TUI open for the remaining exercise. Use `/agent <id>` to
switch identities.
"""
    ),
    md(
        """---
## Section 3 — Run the Interactive Team

Clear old telemetry before the first workshop turn.
"""
    ),
    code(
        """lab.clear_routes()
"""
    ),
    md(
        """### Turn 1 — Bug Reviewer

Run the marker cell, then switch in the TUI:

```text
/agent bug_reviewer
```
"""
    ),
    code(
        """lab.mark_phase("bug_reviewer")
"""
    ),
    md(
        """Send:

```text
Carefully review the Python accuracy implementation against the three failing
examples. Give the root cause and smallest correct source fix in two bullets.
```

Copy its complete answer.
"""
    ),
    code(
        """BUG_REVIEW = '''
'''
"""
    ),
    md(
        """Edit the cell above and paste the Bug Reviewer answer between triple
quotes before continuing.
"""
    ),
    md(
        """### Turn 2 — Test Reviewer

```text
/agent test_reviewer
```
"""
    ),
    code(
        """lab.mark_phase("test_reviewer")
"""
    ),
    md(
        """Send:

```text
Design a compact regression matrix for zero input, perfect accuracy, partial
accuracy, rounding, and SessionResult propagation. Explain what each case
catches in five bullets.
```

Copy its complete answer.
"""
    ),
    code(
        """TEST_REVIEW = '''
'''
"""
    ),
    md(
        """Edit the cell above and paste the Test Reviewer answer before
continuing.
"""
    ),
    md(
        """### Turn 3 — Fixer

The next cell creates a real handoff from the two reviewer outputs.
"""
    ),
    code(
        """fixer_prompt = lab.build_fixer_prompt(BUG_REVIEW, TEST_REVIEW)
lab.mark_phase("fixer")
print(fixer_prompt)
"""
    ),
    md(
        """Switch and send the generated prompt:

```text
/agent fixer
```

Wait until the Fixer reports that it has run the complete test suite.
"""
    ),
    md(
        """### Independent quality gate

The notebook checks the result independently. It requires:

- exactly `107 passed`;
- byte-identical tests;
- only `stats.py` changed; and
- a minimal accepted source correction.
"""
    ),
    code(
        """verification = lab.verify_demo()
"""
    ),
    md(
        """### Turn 4 — Main Reporter

The report prompt is generated from the actual verification object, so `main`
cannot claim success after a failed quality gate.
"""
    ),
    code(
        """assert verification["passed"], "Stop: the quality gate did not pass."
main_prompt = lab.build_main_prompt(verification)
lab.mark_phase("main")
print(main_prompt)
"""
    ),
    md(
        """Switch and send the generated prompt:

```text
/agent main
```
"""
    ),
    md(
        """---
## Section 4 — Reveal the Live Routes

Every row is attributed using the explicit phase marker set before each TUI
turn. Tool counts are displayed but are not used to guess the agent.
"""
    ),
    code(
        """live_routes = lab.route_report(source="live")
live_routes
"""
    ),
    md(
        """### Live estimated relative compute

This is a token-based relative estimate using the versioned Decision Balance
`0.3.2` rates. It is not a cloud bill.
"""
    ),
    code(
        """live_cost = lab.cost_summary(source="live")
live_cost
"""
    ),
    md(
        """Expected route families:

```text
bug_reviewer   code      Flash-Next
test_reviewer  code      Flash-Next
fixer          agentic   GLM
main           fast      27B
```

Fixer continuations may route as `recovery`; they should remain on GLM.
"""
    ),
    md(
        """---
## Section 5 — Precomputed Auto vs Direct GLM

The live run above proves the routing behavior. This precomputed matched
comparison answers the second workshop question: what changed when the same
OpenClaw team used `vllm-sr/auto` instead of sending every request directly to
GLM?

Every included matched workflow passed the same deterministic quality gate.
The output separates:

- empirical policy-level savings from actual auto and direct-GLM executions;
- same-auto-token backend-mix savings, which is a counterfactual sensitivity;
- reliability and route distribution.

`XXX` is relative compute, not money.
"""
    ),
    code(
        """policy_comparison = lab.policy_comparison()
policy_comparison
"""
    ),
    md(
        """---
## Section 6 — Verified Rehearsal

This section is explicitly separate from the live session. Use it only as a
presentation fallback.
"""
    ),
    code(
        """rehearsal_routes = lab.route_report(source="rehearsal")
rehearsal_cost = lab.cost_summary(source="rehearsal")

rehearsal_routes, rehearsal_cost
"""
    ),
    md(
        """---
## Challenge — Automate the Handoff

The main exercise used human-in-the-loop orchestration so every role and route
was visible.

As a follow-up:

1. allow `main` to spawn the two reviewers and Fixer;
2. keep each child task short;
3. preserve the same explicit phase markers and quality gate; and
4. compare automated workflow cost with the interactive run.
"""
    ),
    md(
        """## Your Mission

Explain:

> Which OpenClaw roles needed GLM, which roles used cheaper models, and how much
> estimated relative compute routing avoided while the deterministic tests
> still finished at 107/107 passing?
"""
    ),
]

for index, cell in enumerate(cells):
    cell["id"] = f"baked-vsr-{index:02d}"

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
            "title": "Build an OpenClaw Debugging Team",
            "generated": "2026-10-25",
            "recipe": "decision-balance",
            "recipe_version": "0.3.2",
            "requested_model": "vllm-sr/auto",
            "runtime": "baked Docker workshop",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

TARGET.write_text(json.dumps(notebook, indent=1) + "\n")
print(TARGET)

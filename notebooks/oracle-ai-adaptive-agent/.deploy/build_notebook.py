#!/usr/bin/env python3
"""Generate the simple interactive OpenClaw + vLLM-SR workshop notebook."""

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

---

This workshop has two goals:

1. **Learn OpenClaw** by creating agents, giving them separate roles, switching
   between them in the TUI, and letting a tool-capable Fixer change real code.
2. **Learn vLLM Semantic Router** by watching the same model name,
   `vllm-sr/auto`, select a different physical model and reasoning effort for
   each role.

The team:

```text
                         you
                          |
               OpenClaw TUI agent switch
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
    bug_reviewer     test_reviewer       fixer
     no tools          no tools          tools
          |               |               |
          +---------------+---------------+
                          |
                          v
                         main
                    short final report
```

Expected vLLM-SR behavior:

```text
focused code review  → Qwen3.8-Flash-Next
tool-using fixer     → GLM-5.3-Flash
one-sentence report  → Qwen3.8-27B, thinking off
```

Every OpenClaw agent requests only:

```text
vllm-sr/auto
```
"""
    ),
    md(
        """---
## Section 0 — Connect One Endpoint

The active recipe is **Decision Balance 0.3.2**.

The parts we use today:

| Router decision | Request shape | Model |
| --- | --- | --- |
| `code` | Code reasoning with no tools | Qwen3.8-Flash-Next |
| `agentic` | Declared tools or active tool loop | GLM-5.3-Flash |
| `recovery` | Correcting a failed prior answer | GLM-5.3-Flash |
| `fast` | Simple fallback or brief answer | Qwen3.8-27B |

Configure:

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL              defaults to vllm-sr/auto
VLLM_SR_DASHBOARD_URL     optional
```
"""
    ),
    code(
        """import copy
import getpass
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / ".deploy").is_dir():
    candidate = ROOT / "notebooks" / "oracle-ai-adaptive-agent"
    if candidate.is_dir():
        ROOT = candidate.resolve()

DEPLOY = ROOT / ".deploy"
FIXTURE = DEPLOY / "fixture" / "open_type_faster"
LIVE = DEPLOY / "live"
LIVE.mkdir(parents=True, exist_ok=True)
MEASURED_PATH = DEPLOY / "artifacts" / "simple-route-results.json"
measured_result = (
    json.loads(MEASURED_PATH.read_text())
    if MEASURED_PATH.is_file()
    else None
)
tests_passed = None

STATE_DIR = Path(
    os.getenv(
        "OPENCLAW_WORKSHOP_STATE_DIR",
        "/tmp/openclaw-vsr-simple-state",
    )
)
WORKSPACE_ROOT = Path(
    os.getenv(
        "OPENCLAW_WORKSHOP_WORKSPACES",
        "/tmp/openclaw-vsr-simple-agents",
    )
)
DEMO_ROOT = Path(
    os.getenv(
        "OPENCLAW_WORKSHOP_DEMO_ROOT",
        "/tmp/openclaw-vsr-simple-demo",
    )
)
DEMO_REPO = DEMO_ROOT / "open_type_faster"

OPENCLAW = shutil.which("openclaw")
if not OPENCLAW:
    raise RuntimeError("openclaw is not available on PATH")

OC_ENV = {
    **os.environ,
    "OPENCLAW_STATE_DIR": str(STATE_DIR),
}

def oc(*args, capture=False, check=True):
    command = [OPENCLAW, *map(str, args)]
    print("$", shlex.join(command))
    return subprocess.run(
        command,
        env=OC_ENV,
        text=True,
        capture_output=capture,
        check=check,
    )

print(subprocess.check_output(
    [OPENCLAW, "--version"], text=True
).strip())
print("Workshop state:", STATE_DIR)
print("Demo project:", DEMO_REPO)
"""
    ),
    md(
        """### Configure the endpoint

The API key is read privately and never printed.
"""
    ),
    code(
        """OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "vllm-sr/auto").strip()
VLLM_SR_DASHBOARD_URL = os.getenv(
    "VLLM_SR_DASHBOARD_URL", ""
).strip()

if OPENAI_BASE_URL and not OPENAI_API_KEY:
    OPENAI_API_KEY = getpass.getpass(
        "OpenAI-compatible endpoint key: "
    ).strip()

endpoint_ready = bool(
    OPENAI_BASE_URL and OPENAI_API_KEY and OPENAI_MODEL
)

if endpoint_ready:
    print("Endpoint:", OPENAI_BASE_URL)
    print("Application model:", OPENAI_MODEL)
    if VLLM_SR_DASHBOARD_URL:
        print("Dashboard:", VLLM_SR_DASHBOARD_URL)
else:
    print("Set OPENAI_BASE_URL and OPENAI_API_KEY for the live workshop.")
"""
    ),
    md(
        """### Start the route logger

The local proxy forwards OpenClaw requests to your endpoint and records:

- router decision;
- selected model;
- reasoning effort;
- tools;
- token usage;
- latency; and
- relative compute cost.

It does not store prompt text or the endpoint key.
"""
    ),
    code(
        """PROXY_PID = LIVE / "proxy.pid"
PROXY_LOG = LIVE / "proxy.log"
ROUTES = LIVE / "routes.jsonl"

def pid_is_running(path):
    if not path.is_file():
        return False
    try:
        os.kill(int(path.read_text()), 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False

if endpoint_ready:
    if pid_is_running(PROXY_PID):
        print("Route logger is already running.")
    else:
        proxy_env = {
            **os.environ,
            "ADAPTIVE_AI_BASE_URL": OPENAI_BASE_URL,
            "ADAPTIVE_AI_API_KEY": OPENAI_API_KEY,
        }
        log_handle = PROXY_LOG.open("a")
        proxy = subprocess.Popen(
            [
                sys.executable,
                str(DEPLOY / "bin" / "logging_proxy.py"),
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                "19090",
                "--log-jsonl",
                str(ROUTES),
            ],
            env=proxy_env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        PROXY_PID.write_text(str(proxy.pid))
        time.sleep(2)
        print("Route logger PID:", proxy.pid)
"""
    ),
    md(
        """### Onboard `main`

This creates an isolated OpenClaw state for the workshop. Your normal
`~/.openclaw` configuration is not changed.
"""
    ),
    code(
        """if endpoint_ready:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    if not (STATE_DIR / "openclaw.json").is_file():
        oc(
            "onboard",
            "--non-interactive",
            "--mode",
            "local",
            "--workspace",
            WORKSPACE_ROOT / "main",
            "--auth-choice",
            "custom-api-key",
            "--custom-base-url",
            "http://127.0.0.1:19090/v1",
            "--custom-model-id",
            OPENAI_MODEL,
            "--custom-provider-id",
            "vllm-sr",
            "--custom-compatibility",
            "openai",
            "--custom-api-key",
            "proxy-local",
            "--secret-input-mode",
            "plaintext",
            "--skip-channels",
            "--skip-search",
            "--skip-hooks",
            "--skip-ui",
            "--skip-health",
            "--accept-risk",
        )

    oc("config", "set", "memory.search.enabled", "false")
    oc("config", "set", "tools.profile", "coding")
    oc("agents", "list")
"""
    ),
    md(
        """---
## Section 1 — Meet OpenClaw

### Start the Gateway
"""
    ),
    code(
        """GATEWAY_PID = LIVE / "gateway.pid"
GATEWAY_LOG = LIVE / "gateway.log"

def gateway_is_reachable():
    try:
        with socket.create_connection(
            ("127.0.0.1", 18789),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False

def stop_gateway():
    if not pid_is_running(GATEWAY_PID):
        return
    pid = int(GATEWAY_PID.read_text())
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.2)
    else:
        os.kill(pid, signal.SIGKILL)
    GATEWAY_PID.unlink(missing_ok=True)

def start_gateway():
    if pid_is_running(GATEWAY_PID) and gateway_is_reachable():
        print("Gateway is already running.")
        return

    log_handle = GATEWAY_LOG.open("a")
    process = subprocess.Popen(
        [OPENCLAW, "gateway"],
        env=OC_ENV,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    GATEWAY_PID.write_text(str(process.pid))

    for _ in range(120):
        if gateway_is_reachable():
            print("Gateway ready. PID:", process.pid)
            return
        if process.poll() is not None:
            raise RuntimeError(
                f"Gateway exited. Inspect {GATEWAY_LOG}."
            )
        time.sleep(1)
    raise TimeoutError(f"Gateway did not start. Inspect {GATEWAY_LOG}.")

if endpoint_ready:
    start_gateway()
"""
    ),
    md(
        """### 🦞 Open the TUI

Open a terminal:

```bash
export OPENCLAW_STATE_DIR="/tmp/openclaw-vsr-simple-state"
openclaw tui
```

Say:

```text
Hi. What is an OpenClaw workspace?
```

Then return to the notebook.
"""
    ),
    md(
        """### Inspect the agent workspace

OpenClaw behavior is shaped by visible files:

```text
SOUL.md       personality
IDENTITY.md   name and identity
AGENTS.md     operating policy
USER.md       user context
```
"""
    ),
    code(
        """main_workspace = WORKSPACE_ROOT / "main"

for filename in ["IDENTITY.md", "SOUL.md", "AGENTS.md"]:
    path = main_workspace / filename
    print("=" * 72)
    print(path)
    print("=" * 72)
    if path.is_file():
        text = path.read_text()
        print(text[:1400])
        if len(text) > 1400:
            print("\\n... truncated ...")
    print()
"""
    ),
    md(
        """---
## Section 2 — See the Bug

The workshop includes a frozen snapshot of the public
`Mahdi-CV/open_type_faster` typing application.

Reset the project and run its test suite.
"""
    ),
    code(
        """if DEMO_ROOT.exists():
    shutil.rmtree(DEMO_ROOT)
DEMO_ROOT.mkdir(parents=True)
shutil.copytree(FIXTURE, DEMO_REPO)

print("Prepared:", DEMO_REPO)

test_before = subprocess.run(
    [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
    cwd=DEMO_REPO,
    text=True,
    capture_output=True,
)
print(test_before.stdout)
print(test_before.stderr)
"""
    ),
    md(
        """The expected starting point is:

```text
5 failed, 102 passed
```

All failures come from one accuracy calculation.
"""
    ),
    code(
        """stats_text = (DEMO_REPO / "stats.py").read_text()
start = stats_text.index("def _accuracy")
end = stats_text.index("\\ndef _count_correct", start)
accuracy_source = stats_text[start:end].strip()

tests_text = (DEMO_REPO / "tests" / "test_stats.py").read_text()
test_start = tests_text.index("class TestAccuracy")
test_end = tests_text.index("# ── _count_correct", test_start)
accuracy_tests = tests_text[test_start:test_end].strip()

print("CURRENT IMPLEMENTATION")
print("-" * 72)
print(accuracy_source)
print()
print("EXPECTED BEHAVIOR")
print("-" * 72)
print(accuracy_tests)
"""
    ),
    md(
        """---
## Section 3 — Build the Team

Exit the TUI with `Ctrl+C`, then stop the Gateway before changing the roster.
"""
    ),
    code(
        """if endpoint_ready:
    stop_gateway()
    print("Gateway stopped.")
"""
    ),
    md(
        """### Create a tool-free provider alias

This alias uses the **same endpoint** and the **same model name**. It only tells
OpenClaw not to send tool schemas for roles that already have all required
evidence in their workspace instructions.

```text
vllm-sr             tools enabled
vllm-sr-no-tools    tools disabled
```
"""
    ),
    code(
        """if endpoint_ready:
    provider_result = oc(
        "config",
        "get",
        "models.providers.vllm-sr",
        "--json",
        capture=True,
    )
    provider = json.loads(provider_result.stdout)
    no_tools_provider = copy.deepcopy(provider)
    no_tools_provider["apiKey"] = "proxy-local"

    for model in no_tools_provider.get("models", []):
        if model.get("id") == OPENAI_MODEL:
            model["name"] = f"{OPENAI_MODEL} — no tools"
            model["contextWindow"] = 128000
            model["maxTokens"] = 3000
            model["reasoning"] = False
            model.setdefault("compat", {})["supportsTools"] = False

    oc(
        "config",
        "set",
        "models.providers.vllm-sr-no-tools",
        json.dumps(no_tools_provider, separators=(",", ":")),
        "--strict-json",
    )
"""
    ),
    md(
        """### Add three agents

You are creating real OpenClaw agents with isolated workspaces:

```text
bug_reviewer
test_reviewer
fixer
```
"""
    ),
    code(
        """TEAM = ["bug_reviewer", "test_reviewer", "fixer"]

def configured_agent_ids():
    result = oc("agents", "list", "--json", capture=True)
    body = json.loads(result.stdout)
    rows = body.get("agents", body) if isinstance(body, dict) else body
    return {item.get("id") for item in rows}

if endpoint_ready:
    existing = configured_agent_ids()
    for agent_id in TEAM:
        model = (
            f"vllm-sr-no-tools/{OPENAI_MODEL}"
            if agent_id != "fixer"
            else f"vllm-sr/{OPENAI_MODEL}"
        )
        if agent_id not in existing:
            oc(
                "agents",
                "add",
                agent_id,
                "--non-interactive",
                "--workspace",
                WORKSPACE_ROOT / agent_id,
                "--model",
                model,
            )
        oc(
            "config",
            "set",
            f"agents.entries.{agent_id}.model",
            model,
        )
        oc(
            "config",
            "set",
            f"agents.entries.{agent_id}.skills",
            "[]",
            "--strict-json",
        )

    # The reporter and reviewers do not need tools.
    for agent_id in ["main", "bug_reviewer", "test_reviewer"]:
        oc(
            "config",
            "set",
            f"agents.entries.{agent_id}.model",
            f"vllm-sr-no-tools/{OPENAI_MODEL}",
        )
        oc(
            "config",
            "set",
            f"agents.entries.{agent_id}.tools.profile",
            "minimal",
        )
        oc(
            "config",
            "set",
            f"agents.entries.{agent_id}.skills",
            "[]",
            "--strict-json",
        )

    # The Fixer needs filesystem, editing and execution tools.
    oc(
        "config",
        "set",
        "agents.entries.fixer.tools.profile",
        "coding",
    )

    oc("agents", "list")
"""
    ),
    md(
        """### Give every agent one clear role

The reviewers receive a small frozen artifact directly in `AGENTS.md`. They
need reasoning, not tools.

The Fixer receives the real project path and the authority to edit source and
run tests.
"""
    ),
    code(
        """ROLE_FILES = {
    "main": '''# Team Reporter

You write the final verified summary for the debugging team.
Use no tools. Keep the answer to the length the user requests.
''',
    "bug_reviewer": f'''# Bug Reviewer

Your only job is to review this Python implementation against the observed
accuracy failures. Do not use tools. Identify the root cause and the smallest
source-only fix.

## Implementation

```python
{accuracy_source}
```

## Observed failures

- perfect: expected 100.0, got 0
- half correct: expected 50.0, got 0
- two of three: expected 66.7, got 0
''',
    "test_reviewer": f'''# Test Reviewer

Your only job is to define the behavioral contract and regression tests for
the accuracy calculation. Do not use tools.

## Implementation under review

```python
{accuracy_source}
```

## Existing test contract

```python
{accuracy_tests}
```
''',
    "fixer": f'''# Fixer

Work only in:

{DEMO_REPO}

Use your filesystem and execution tools. Run the tests, inspect the failing
accuracy implementation, make the smallest source-only correction, and rerun
the complete test suite. Preserve all test files.
''',
}

for agent_id, instructions in ROLE_FILES.items():
    workspace = WORKSPACE_ROOT / agent_id
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text(instructions)
    (workspace / "SOUL.md").write_text(
        "# Soul\\n\\nBe precise, calm, and evidence-driven.\\n"
    )
    (workspace / "IDENTITY.md").write_text(
        f"# Identity\\n\\nName: {agent_id}\\n"
    )
    (workspace / "USER.md").write_text(
        "# User\\n\\nPrefer minimal changes and verified results.\\n"
    )
    (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)

for agent_id in ROLE_FILES:
    print("=" * 72)
    print(agent_id)
    print((WORKSPACE_ROOT / agent_id / "AGENTS.md").read_text()[:1800])
    print()
"""
    ),
    md(
        """### Restart the Gateway
"""
    ),
    code(
        """if endpoint_ready:
    start_gateway()
"""
    ),
    md(
        """### 🦞 Reopen the TUI

```bash
export OPENCLAW_STATE_DIR="/tmp/openclaw-vsr-simple-state"
openclaw tui
```

OpenClaw now has four visible identities:

```text
main
bug_reviewer
test_reviewer
fixer
```
"""
    ),
    md(
        """---
## Section 4 — Run the Interactive Team

Open vLLM-SR **Dashboard → Insights** beside the TUI.

The next cell clears only the live route log.
"""
    ),
    code(
        """if endpoint_ready:
    ROUTES.write_text("")
    print("Route log cleared:", ROUTES)
"""
    ),
    md(
        """### Turn 1 — Bug Reviewer

In the TUI:

```text
/agent bug_reviewer
```

Then:

```text
Carefully review the Python accuracy implementation against the three failing
examples. Give the root cause and smallest correct source fix in two bullets.
```

Expected route:

```text
code → Qwen3.8-Flash-Next → medium effort
```
"""
    ),
    md(
        """### Turn 2 — Test Reviewer

```text
/agent test_reviewer
```

Then:

```text
Design a compact regression matrix for zero input, perfect accuracy, partial
accuracy, rounding, and SessionResult propagation. Explain what each case
catches in five bullets.
```

Expected route:

```text
code → Qwen3.8-Flash-Next → medium effort
```
"""
    ),
    md(
        """### Turn 3 — Fixer

Copy the two short review answers, then switch:

```text
/agent fixer
```

Send:

```text
Use the reviewers' conclusions as guidance. Fix the prepared
open_type_faster accuracy bug, run the complete pytest suite, and report the
verified result.
```

Expected route:

```text
agentic/tool loop → GLM-5.3-Flash → high effort
```
"""
    ),
    md(
        """### Verify independently

This notebook—not an LLM judge—checks the result.
"""
    ),
    code(
        """test_after = subprocess.run(
    [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
    cwd=DEMO_REPO,
    text=True,
    capture_output=True,
)
print(test_after.stdout)
print(test_after.stderr)

tests_passed = test_after.returncode == 0
print("QUALITY GATE:", "PASS" if tests_passed else "FAIL")
"""
    ),
    md(
        """### Turn 4 — Main Reporter

```text
/agent main
```

After the quality gate passes:

```text
In one sentence, summarize this verified result: the accuracy defect was fixed
and all 107 tests passed.
```

Expected route:

```text
fast → Qwen3.8-27B → thinking off
```
"""
    ),
    md(
        """---
## Section 5 — Reveal Every Route

The requests below came from one OpenClaw TUI and one model name.
"""
    ),
    code(
        """def load_jsonl(path):
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]

route_rows = [
    row
    for row in load_jsonl(ROUTES)
    if row.get("method") == "POST"
]

no_tool_indices = [
    index
    for index, row in enumerate(route_rows)
    if int(row.get("tool_count") or 0) == 0
]

phase_names = {}
if no_tool_indices:
    phase_names[no_tool_indices[0]] = "bug_reviewer"
if len(no_tool_indices) > 1:
    phase_names[no_tool_indices[1]] = "test_reviewer"
if len(no_tool_indices) > 2:
    phase_names[no_tool_indices[-1]] = "main_reporter"

fixer_step = 0
route_table = []
for index, row in enumerate(route_rows):
    tool_count = int(row.get("tool_count") or 0)
    if index in phase_names:
        phase = phase_names[index]
    elif tool_count:
        fixer_step += 1
        phase = f"fixer_{fixer_step}"
    else:
        phase = "extra_no_tool_turn"

    headers = row.get("routing_headers", {})
    usage = row.get("usage", {})
    route_table.append(
        {
            "call": index + 1,
            "phase": phase,
            "tools": tool_count,
            "decision": headers.get("x-vsr-selected-decision"),
            "model": headers.get("x-vsr-selected-model"),
            "reasoning": headers.get("x-vsr-selected-reasoning"),
            "finish": row.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": usage.get("reasoning_tokens"),
            "latency_s": row.get("latency_seconds"),
            "cost_xxx": row.get("estimated_relative_cost_xxx"),
        }
    )

if not route_rows and measured_result:
    print("No live route log found. Showing the verified rehearsal.")
    route_table = []
    call_index = 0
    for phase, rows in measured_result["routes"].items():
        for step, row in enumerate(rows, start=1):
            call_index += 1
            phase_name = phase if len(rows) == 1 else f"{phase}_{step}"
            route_table.append(
                {
                    "call": call_index,
                    "phase": phase_name,
                    "tools": row["tools"],
                    "decision": row["decision"],
                    "model": row["model"],
                    "reasoning": row["reasoning"],
                    "finish": row["finish_reason"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "reasoning_tokens": row["reasoning_tokens"],
                    "latency_s": row["latency_seconds"],
                    "cost_xxx": row["cost_xxx"],
                }
            )
    tests_passed = measured_result["quality"]["pytest_passed"]

route_table
"""
    ),
    md(
        """### Routing distribution
"""
    ),
    code(
        """{
    "calls": len(route_table),
    "decisions": dict(Counter(
        str(row["decision"]) for row in route_table
    )),
    "models": dict(Counter(
        str(row["model"]) for row in route_table
    )),
    "quality_gate": (
        "PASS" if tests_passed
        else "FAIL" if tests_passed is False
        else "NOT RUN"
    ),
}
"""
    ),
    md(
        """### Compare relative compute

The routed number is measured from response headers.

The comparison asks what the same prompt and completion token counts would cost
if every call used GLM's relative factor. `XXX` is not dollars.
"""
    ),
    code(
        """if route_rows:
    routed_cost = sum(
        float(row.get("estimated_relative_cost_xxx") or 0)
        for row in route_rows
    )

    all_glm_cost = 0.0
    for row in route_rows:
        usage = row.get("usage", {})
        token_units = (
            int(usage.get("prompt_tokens") or 0) * 0.1
            + int(usage.get("completion_tokens") or 0)
        )
        all_glm_cost += token_units * 4.35 / 1_000_000

    cost_comparison = {
        "routed_measured_xxx": round(routed_cost, 8),
        "all_glm_same_tokens_xxx": round(all_glm_cost, 8),
        "estimated_reduction_percent": round(
            (1 - routed_cost / all_glm_cost) * 100,
            1,
        ) if all_glm_cost else None,
        "tests": "PASS" if tests_passed else "FAIL",
    }
elif measured_result:
    cost_comparison = {
        **measured_result["cost"],
        "tests": (
            "PASS"
            if measured_result["quality"]["pytest_passed"]
            else "FAIL"
        ),
    }
else:
    cost_comparison = {"status": "No live or measured result available."}

cost_comparison
"""
    ),
    md(
        """---
## Section 6 — What You Built

You created:

- four separate OpenClaw identities;
- four separate workspaces and operating policies;
- two focused code-review agents;
- one autonomous tool-using Fixer;
- one inexpensive final Reporter; and
- one application-facing model name.

You did **not** make every role use the cheapest model.

You let vLLM Semantic Router reserve expensive inference for the part of the
workflow that actually needed tools.

### Optional challenge: automate the handoff

The workshop used human-in-the-loop orchestration so every role and route was
visible.

As a follow-up, teach `main` to use `sessions_spawn` to call the two reviewers
and the Fixer automatically. Keep each child task short and keep the same
quality gate.
"""
    ),
    md(
        """## Your Mission

Build the OpenClaw team, run the four interactive turns, and use Dashboard
Insights to answer:

> Which agent calls needed GLM, which calls used the code specialist, and how
> much relative compute did routing avoid while all tests still passed?
"""
    ),
]

for index, cell in enumerate(cells):
    cell["id"] = f"simple-vsr-{index:02d}"

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
            "interaction": "OpenClaw TUI human-in-the-loop",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

TARGET.write_text(json.dumps(notebook, indent=1) + "\n")
print(TARGET)

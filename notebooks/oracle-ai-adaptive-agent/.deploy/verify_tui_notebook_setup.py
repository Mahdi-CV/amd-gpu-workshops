#!/usr/bin/env python3
"""Qualify the simple TUI-first workshop against the live vLLM-SR endpoint."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "workshop.ipynb"
LIVE = ROOT / ".deploy" / "live"
ARTIFACTS = ROOT / ".deploy" / "artifacts"
STATE = Path("/tmp/openclaw-vsr-simple-e2e-state")
WORKSPACES = Path("/tmp/openclaw-vsr-simple-e2e-agents")
DEMO_ROOT = Path("/tmp/openclaw-vsr-simple-e2e-demo")
ROUTES = LIVE / "routes.jsonl"
OPENCLAW = os.getenv("OPENCLAW_BIN", shutil.which("openclaw") or "")


PROMPTS = {
    "bug_reviewer": (
        "Carefully review the Python accuracy implementation against the "
        "three failing examples. Give the root cause and smallest correct "
        "source fix in two bullets."
    ),
    "test_reviewer": (
        "Design a compact regression matrix for zero input, perfect accuracy, "
        "partial accuracy, rounding, and SessionResult propagation. Explain "
        "what each case catches in five bullets."
    ),
    "fixer": (
        "Use the reviewers' conclusions as guidance. Fix the prepared "
        "open_type_faster accuracy bug, run the complete pytest suite, and "
        "report the verified result."
    ),
    "main": (
        "In one sentence, summarize this verified result: the accuracy defect "
        "was fixed and all 107 tests passed."
    ),
}


def stop_pid_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        pid = int(path.read_text())
    except ValueError:
        path.unlink(missing_ok=True)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.2)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    path.unlink(missing_ok=True)


def read_routes() -> list[dict[str, Any]]:
    if not ROUTES.is_file():
        return []
    return [
        json.loads(line)
        for line in ROUTES.read_text().splitlines()
        if line.strip()
    ]


def run_agent(agent: str, session_id: str, message: str) -> dict[str, Any]:
    env = {
        **os.environ,
        "OPENCLAW_STATE_DIR": str(STATE),
        "PATH": f"/tmp/openclaw-test-bin:{os.environ.get('PATH', '')}",
    }
    result = subprocess.run(
        [
            OPENCLAW,
            "agent",
            "--agent",
            agent,
            "--session-id",
            session_id,
            "--json",
            "--timeout",
            "900",
            "--message",
            message,
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=1000,
        check=False,
    )
    (LIVE / f"{agent}.stdout").write_text(result.stdout)
    (LIVE / f"{agent}.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(
            f"{agent} failed with status {result.returncode}: "
            f"{result.stderr[-2000:]}"
        )
    body = json.loads(result.stdout)
    (LIVE / f"{agent}.json").write_text(json.dumps(body, indent=2) + "\n")
    return body


def route_view(row: dict[str, Any]) -> dict[str, Any]:
    headers = row.get("routing_headers") or {}
    usage = row.get("usage") or {}
    return {
        "request_id": row.get("request_id"),
        "decision": headers.get("x-vsr-selected-decision"),
        "model": headers.get("x-vsr-selected-model"),
        "reasoning": headers.get("x-vsr-selected-reasoning"),
        "algorithm": headers.get("x-vsr-selected-algorithm"),
        "tools": int(row.get("tool_count") or 0),
        "finish_reason": row.get("finish_reason"),
        "status": row.get("status"),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "reasoning_tokens": int(usage.get("reasoning_tokens") or 0),
        "latency_seconds": row.get("latency_seconds"),
        "cost_xxx": row.get("estimated_relative_cost_xxx"),
    }


def main() -> int:
    if not OPENCLAW:
        raise RuntimeError(
            "Set OPENCLAW_BIN or make openclaw available on PATH."
        )
    base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "Set OPENAI_BASE_URL and OPENAI_API_KEY before verification."
        )

    LIVE.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stop_pid_file(LIVE / "gateway.pid")
    stop_pid_file(LIVE / "proxy.pid")
    shutil.rmtree(STATE, ignore_errors=True)
    shutil.rmtree(WORKSPACES, ignore_errors=True)
    shutil.rmtree(DEMO_ROOT, ignore_errors=True)

    os.environ.update(
        {
            "OPENAI_BASE_URL": base_url,
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": "vllm-sr/auto",
            "OPENCLAW_WORKSHOP_STATE_DIR": str(STATE),
            "OPENCLAW_WORKSHOP_WORKSPACES": str(WORKSPACES),
            "OPENCLAW_WORKSHOP_DEMO_ROOT": str(DEMO_ROOT),
            "PATH": f"/tmp/openclaw-test-bin:{os.environ.get('PATH', '')}",
        }
    )

    notebook = json.loads(NOTEBOOK.read_text())
    namespace: dict[str, object] = {"__name__": "__workshop_verify__"}
    setup_cells = [
        2,
        4,
        6,
        8,
        10,
        13,
        15,
        17,
        19,
        21,
        23,
        25,
        27,
        30,
    ]

    previous_cwd = Path.cwd()
    os.chdir(ROOT)
    try:
        for index in setup_cells:
            print(f"EXECUTING_CELL={index}", flush=True)
            source = "".join(notebook["cells"][index]["source"])
            exec(compile(source, f"<cell-{index}>", "exec"), namespace)
    finally:
        os.chdir(previous_cwd)

    ROUTES.write_text("")
    route_spans: dict[str, list[dict[str, Any]]] = {}
    responses: dict[str, Any] = {}

    for agent in ("bug_reviewer", "test_reviewer", "fixer"):
        before = len(read_routes())
        body = run_agent(
            agent,
            f"simple-e2e-{agent}",
            PROMPTS[agent],
        )
        after_rows = read_routes()[before:]
        responses[agent] = body
        route_spans[agent] = [route_view(row) for row in after_rows]

    demo_repo = DEMO_ROOT / "open_type_faster"
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
        cwd=demo_repo,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    (LIVE / "pytest.stdout").write_text(tests.stdout)
    (LIVE / "pytest.stderr").write_text(tests.stderr)

    before = len(read_routes())
    responses["main"] = run_agent(
        "main",
        "simple-e2e-main",
        PROMPTS["main"],
    )
    route_spans["main"] = [
        route_view(row) for row in read_routes()[before:]
    ]

    all_rows = [
        item
        for agent_rows in route_spans.values()
        for item in agent_rows
    ]
    routed_cost = sum(float(row["cost_xxx"] or 0) for row in all_rows)
    all_glm_cost = sum(
        (
            row["prompt_tokens"] * 0.1
            + row["completion_tokens"]
        )
        * 4.35
        / 1_000_000
        for row in all_rows
    )

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "requested_model": "vllm-sr/auto",
        "recipe": "decision-balance",
        "recipe_version": "0.3.2",
        "routes": route_spans,
        "quality": {
            "pytest_returncode": tests.returncode,
            "pytest_passed": tests.returncode == 0,
            "contains_107_passed": "107 passed" in tests.stdout,
            "stdout_tail": tests.stdout[-1000:],
        },
        "cost": {
            "routed_measured_xxx": round(routed_cost, 8),
            "all_glm_same_tokens_xxx": round(all_glm_cost, 8),
            "estimated_reduction_percent": round(
                (1 - routed_cost / all_glm_cost) * 100,
                2,
            )
            if all_glm_cost
            else None,
        },
    }

    expected = {
        "bug_reviewer": ("code", "qwen/qwen3.8-flash-next"),
        "test_reviewer": ("code", "qwen/qwen3.8-flash-next"),
        "main": ("fast", "qwen/qwen3.8-27b"),
    }
    checks: dict[str, bool] = {}
    for agent, (decision, model) in expected.items():
        first = route_spans.get(agent, [{}])[0]
        checks[f"{agent}_decision"] = first.get("decision") == decision
        checks[f"{agent}_model"] = first.get("model") == model

    fixer_models = {
        row.get("model") for row in route_spans.get("fixer", [])
    }
    fixer_decisions = {
        row.get("decision") for row in route_spans.get("fixer", [])
    }
    checks["fixer_model"] = fixer_models == {"zai/glm-5.3-flash"}
    checks["fixer_decision"] = fixer_decisions <= {"agentic", "recovery"}
    checks["pytest"] = tests.returncode == 0 and "107 passed" in tests.stdout

    summary["checks"] = checks
    summary["passed"] = all(checks.values())

    output = ARTIFACTS / "simple-route-results.json"
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("Saved:", output)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

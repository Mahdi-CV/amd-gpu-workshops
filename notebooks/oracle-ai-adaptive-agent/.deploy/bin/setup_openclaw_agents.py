#!/usr/bin/env python3
"""Create an isolated, tool-free OpenClaw ReviewBench panel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


ROLES = {
    "rb_correctness": """# Correctness and Security Reviewer

Review only the supplied pull-request packet.
Find actionable correctness, security, reliability, and testing issues.
Use line numbers from the head files. Do not use tools or network access.
Return only the requested JSON.
""",
    "rb_reliability": """# Reliability and Performance Reviewer

Review only the supplied pull-request packet.
Find actionable reliability, performance, maintainability, and API issues.
Check whether the implementation actually matches the PR description.
Use line numbers from the head files. Do not use tools or network access.
Return only the requested JSON.
""",
    "rb_integration": """# Integration and Control-Flow Reviewer

Review only the supplied pull-request packet.
Trace call ordering, state transitions, cross-file interactions, pagination,
and side effects in callers. Check whether an earlier operation invalidates
state needed by a later operation. For every new gate or early return, inspect
the mutating calls that execute before it and verify the return does not leave
user-visible state partially changed. Use line numbers from the head files.
Return at most three high-confidence findings.
Do not use tools or network access. Return only the requested JSON.
""",
    "rb_merger": """# Review Finding Adjudicator

Merge supplied reviewer findings without inventing new issues.
Preserve distinct findings, remove exact duplicates, and keep precise file and
line anchors. Return only the requested JSON.
""",
}


def command(args: argparse.Namespace, *values: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["OPENCLAW_STATE_DIR"] = str(args.state_dir)
    return subprocess.run(
        [args.openclaw, *values],
        env=env,
        check=check,
        text=True,
        capture_output=True,
    )


def ensure_agent(
    args: argparse.Namespace,
    agent: str,
    workspace: Path,
    model_ref: str,
) -> None:
    listed = command(args, "agents", "list", "--json")
    body = json.loads(listed.stdout)
    agents = body.get("agents", body) if isinstance(body, dict) else body
    if not any(item.get("id") == agent for item in agents):
        command(
            args,
            "agents",
            "add",
            agent,
            "--non-interactive",
            "--workspace",
            str(workspace),
            "--model",
            model_ref,
        )
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text(ROLES[agent])
    (workspace / "SOUL.md").write_text("# Soul\n\nBe precise, concise, and evidence-driven.\n")
    (workspace / "IDENTITY.md").write_text(f"# Identity\n\nName: {agent}\n")
    (workspace / "USER.md").write_text("# User\n\nPrefer actionable review findings.\n")
    (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)
    command(
        args,
        "config",
        "set",
        f"agents.entries.{agent}.model",
        model_ref,
    )
    command(
        args,
        "config",
        "set",
        f"agents.entries.{agent}.skills",
        "[]",
        "--strict-json",
    )
    command(
        args,
        "config",
        "set",
        f"agents.entries.{agent}.tools.profile",
        "minimal",
    )
    command(
        args,
        "config",
        "set",
        f"agents.entries.{agent}.bootstrapMaxChars",
        "1600",
        "--strict-json",
    )
    command(
        args,
        "config",
        "set",
        f"agents.entries.{agent}.bootstrapTotalMaxChars",
        "4000",
        "--strict-json",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--proxy-base-url", default="http://127.0.0.1:19090/v1")
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "vllm-sr/auto"),
    )
    parser.add_argument(
        "--openclaw",
        default=os.getenv("OPENCLAW_BIN")
        or shutil.which("openclaw")
        or "openclaw",
    )
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    args.workspace_root.mkdir(parents=True, exist_ok=True)

    if not (args.state_dir / "openclaw.json").exists():
        command(
            args,
            "onboard",
            "--non-interactive",
            "--mode",
            "local",
            "--workspace",
            str(args.workspace_root / "main"),
            "--auth-choice",
            "custom-api-key",
            "--custom-base-url",
            args.proxy_base_url,
            "--custom-model-id",
            args.model,
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

    provider = {
        "baseUrl": args.proxy_base_url,
        "api": "openai-completions",
        "apiKey": "proxy-local",
        "models": [
            {
                "id": args.model,
                "name": f"{args.model} ReviewBench tool-free",
                "contextWindow": 128000,
                "maxTokens": 5000,
                "input": ["text"],
                "reasoning": False,
                "compat": {"supportsTools": False},
            }
        ],
    }
    command(
        args,
        "config",
        "set",
        "models.providers.vllm-sr-no-tools",
        json.dumps(provider, separators=(",", ":")),
        "--strict-json",
    )
    command(args, "config", "set", "memory.search.enabled", "false")

    model_ref = f"vllm-sr-no-tools/{args.model}"
    for agent in ROLES:
        ensure_agent(args, agent, args.workspace_root / agent, model_ref)

    print(
        json.dumps(
            {
                "state_dir": str(args.state_dir),
                "agents": list(ROLES),
                "model": model_ref,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

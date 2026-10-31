#!/usr/bin/env python3
"""Idempotently prepare OpenClaw for the AMD booth application."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


STATE = Path(os.getenv("OPENCLAW_STATE_DIR", "/data/openclaw"))
WORKSPACES = Path(os.getenv("OPENCLAW_WORKSPACES", "/data/agents"))
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "vllm-sr/auto")
TEMPLATES = Path("/opt/booth/templates")
CONFIG = STATE / "openclaw.json"
AGENTS = ("main", "researcher", "builder", "reviewer")


def environment() -> dict[str, str]:
    return {
        **os.environ,
        "OPENCLAW_STATE_DIR": str(STATE),
        "HOME": os.getenv("HOME", "/home/booth"),
    }


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["openclaw", *args],
        env=environment(),
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"openclaw {' '.join(args)} failed: "
            f"{(result.stderr or result.stdout)[-3000:]}"
        )
    return result


def onboard() -> None:
    if CONFIG.is_file():
        return
    run(
        "onboard",
        "--non-interactive",
        "--mode",
        "local",
        "--workspace",
        str(WORKSPACES / "main"),
        "--auth-choice",
        "custom-api-key",
        "--custom-base-url",
        "http://127.0.0.1:8088/proxy/main/v1",
        "--custom-model-id",
        ROUTER_MODEL,
        "--custom-provider-id",
        "booth-main",
        "--custom-compatibility",
        "openai",
        "--custom-api-key",
        "local-proxy",
        "--secret-input-mode",
        "plaintext",
        "--skip-bootstrap",
        "--skip-channels",
        "--skip-search",
        "--skip-hooks",
        "--skip-ui",
        "--skip-health",
        "--accept-risk",
    )


def configured_agents() -> set[str]:
    body = json.loads(run("agents", "list", "--json").stdout)
    rows = body.get("agents", body) if isinstance(body, dict) else body
    return {str(row.get("id")) for row in rows}


def ensure_agents() -> None:
    existing = configured_agents()
    for agent in AGENTS[1:]:
        if agent in existing:
            continue
        run(
            "agents",
            "add",
            agent,
            "--non-interactive",
            "--workspace",
            str(WORKSPACES / agent),
            "--model",
            f"booth-{agent}/{ROUTER_MODEL}",
        )


def model_entry() -> dict[str, Any]:
    return {
        "id": ROUTER_MODEL,
        "name": "AMD Booth Semantic Router",
        "contextWindow": 128000,
        "maxTokens": 8192,
        "input": ["text", "image"],
        "reasoning": False,
        "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
        },
    }


def provider(agent: str) -> dict[str, Any]:
    return {
        "baseUrl": f"http://127.0.0.1:8088/proxy/{agent}/v1",
        "api": "openai-completions",
        "apiKey": "local-proxy",
        "models": [model_entry()],
    }


def patch_config() -> None:
    body = json.loads(CONFIG.read_text(encoding="utf-8"))
    body.setdefault("models", {})["providers"] = {
        f"booth-{agent}": provider(agent) for agent in AGENTS
    }

    agents = body.setdefault("agents", {})
    agents.setdefault("defaults", {})["model"] = {
        "primary": f"booth-main/{ROUTER_MODEL}"
    }
    entries = agents.setdefault("entries", {})
    for agent in AGENTS:
        entry = entries.setdefault(agent, {"name": agent})
        entry["name"] = agent
        entry["workspace"] = str(WORKSPACES / agent)
        entry["model"] = f"booth-{agent}/{ROUTER_MODEL}"
        entry["bootstrapMaxChars"] = 24000
        entry["bootstrapTotalMaxChars"] = 64000
        entry["tools"] = {"profile": "coding"}

    entries["main"]["subagents"] = {
        "allowAgents": ["researcher", "builder", "reviewer"]
    }
    entries["main"]["tools"] = {
        "profile": "coding",
        "alsoAllow": [
            "sessions_spawn",
            "sessions_yield",
            "subagents",
            "browser",
            "web_fetch",
        ],
    }

    body.setdefault("tools", {})["profile"] = "coding"
    body.setdefault("memory", {}).setdefault("search", {})["enabled"] = False
    body["browser"] = {
        "enabled": True,
        "executablePath": os.getenv(
            "BROWSER_EXECUTABLE_PATH",
            "/usr/bin/chromium",
        ),
        "headless": True,
        "noSandbox": True,
    }

    CONFIG.write_text(
        json.dumps(body, indent=2) + "\n",
        encoding="utf-8",
    )


def install_role_files() -> None:
    for agent in AGENTS:
        workspace = WORKSPACES / agent
        workspace.mkdir(parents=True, exist_ok=True)
        source = TEMPLATES / f"{agent}-AGENTS.md"
        shutil.copyfile(source, workspace / "AGENTS.md")
        (workspace / "SOUL.md").write_text(
            "# Soul\n\nBe energetic, precise, visual, and evidence-driven.\n",
            encoding="utf-8",
        )
        (workspace / "IDENTITY.md").write_text(
            f"# Identity\n\n- Name: {agent}\n- Emoji: ⚡\n",
            encoding="utf-8",
        )
        (workspace / "USER.md").write_text(
            "# User\n\nPrefer useful booth-sized results with visible verification.\n",
            encoding="utf-8",
        )
        (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    WORKSPACES.mkdir(parents=True, exist_ok=True)
    onboard()
    ensure_agents()
    patch_config()
    install_role_files()
    print("OpenClaw booth state ready.")


if __name__ == "__main__":
    main()

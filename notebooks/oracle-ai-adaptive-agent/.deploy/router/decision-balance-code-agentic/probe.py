#!/usr/bin/env python3
"""Assert that code-agentic routes to Flash while GLM remains in use."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


FLASH = "qwen/qwen3.8-flash-next"
GLM = "zai/glm-5.3-flash"


def load_key(args: argparse.Namespace) -> str:
    if args.api_key_file:
        value = args.api_key_file.read_text(encoding="utf-8").strip()
    else:
        value = os.getenv(args.api_key_env, "").strip()
    if not value:
        raise SystemExit(
            f"Set {args.api_key_env} or pass --api-key-file."
        )
    return value


def completion_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/chat/completions"


def run_case(
    *,
    url: str,
    api_key: str,
    name: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    expected_decision: str,
    expected_model: str,
    timeout: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "vllm-sr/auto",
        "messages": messages,
        "max_tokens": 8,
    }
    if tools:
        body["tools"] = tools
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-vsr-debug": "true",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"{name} failed with HTTP {exc.code}: "
            f"{exc.read().decode(errors='replace')[:1000]}"
        ) from exc
    decision = headers.get("x-vsr-selected-decision")
    model = headers.get("x-vsr-selected-model")
    passed = decision == expected_decision and model == expected_model
    return {
        "case": name,
        "passed": passed,
        "decision": decision,
        "model": model,
        "reasoning": headers.get("x-vsr-selected-reasoning"),
        "ranking": headers.get("x-vsr-decision-ranking"),
        "expected_decision": expected_decision,
        "expected_model": expected_model,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()

    api_key = load_key(args)
    url = completion_url(args.base_url)
    read_tool = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read one source file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    cases = [
        {
            "name": "code_with_tools",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Review report.py for performance issues and give "
                        "file:line findings."
                    ),
                }
            ],
            "tools": read_tool,
            "expected_decision": "code_agentic",
            "expected_model": FLASH,
        },
        {
            "name": "generic_agentic",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Check the current weather in Paris using the "
                        "available tool."
                    ),
                }
            ],
            "tools": read_tool,
            "expected_decision": "agentic",
            "expected_model": GLM,
        },
        {
            "name": "code_without_tools",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Review this Python loop for performance: "
                        "for x in rows: rows.count(x)"
                    ),
                }
            ],
            "tools": None,
            "expected_decision": "code",
            "expected_model": FLASH,
        },
        {
            "name": "recovery",
            "messages": [
                {"role": "user", "content": "What is 17 * 24?"},
                {
                    "role": "assistant",
                    "content": "17 * 24 = 418.",
                },
                {
                    "role": "user",
                    "content": (
                        "That is wrong. Recalculate and correct it."
                    ),
                },
            ],
            "tools": None,
            "expected_decision": "recovery",
            "expected_model": GLM,
        },
    ]

    rows = [
        run_case(
            url=url,
            api_key=api_key,
            timeout=args.timeout,
            **case,
        )
        for case in cases
    ]
    text = json.dumps(rows, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

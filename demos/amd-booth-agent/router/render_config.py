#!/usr/bin/env python3
"""Render the booth Router config from the Decision Balance reference recipe."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import yaml


LOCAL_MODEL = "qwen/qwen3.8-27b"
GLM_MODEL = "zai/glm-5.3-flash"
KIMI_MODEL = "moonshot/kimi-k3"


def local_backend() -> dict[str, Any]:
    return {
        "name": LOCAL_MODEL,
        "catalog": LOCAL_MODEL,
        "provider_model_id": LOCAL_MODEL,
        "api_format": "openai",
        "backend_refs": [
            {
                "name": "mi300x-qwen27b",
                "endpoint": "local-model:8000",
                "protocol": "http",
                "provider": "vllm",
                "weight": 1,
            }
        ],
        "pricing": {
            "currency": "USD",
            "prompt_per_1m": 0.0,
            "completion_per_1m": 0.0,
        },
    }


def fireworks_backend(
    *,
    logical_name: str,
    catalog: str,
    provider_model_id: str,
    prompt_rate: float,
    completion_rate: float,
    cached_input_rate: float | None = None,
) -> dict[str, Any]:
    pricing: dict[str, Any] = {
        "currency": "USD",
        "prompt_per_1m": prompt_rate,
        "completion_per_1m": completion_rate,
    }
    if cached_input_rate is not None:
        pricing["cached_input_per_1m"] = cached_input_rate
    return {
        "name": logical_name,
        "catalog": catalog,
        "provider_model_id": provider_model_id,
        "api_format": "openai",
        "backend_refs": [
            {
                "name": logical_name.replace("/", "-"),
                "base_url": "https://api.fireworks.ai/inference/v1",
                "provider": "openai",
                "auth_header": "Authorization",
                "auth_prefix": "Bearer",
                "api_key_env": "FIREWORKS_API_KEY",
                "chat_path": "/chat/completions",
                "weight": 1,
            }
        ],
        "pricing": pricing,
    }


def rule(name: str, priority: int, conditions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "priority": priority,
        "rules": {
            "operator": "AND",
            "on_unknown": "no_match",
            "conditions": conditions,
        },
    }


def static_decision(
    *,
    name: str,
    priority: int,
    description: str,
    model: str,
    effort: str,
    conditions: list[dict[str, Any]],
    use_reasoning: bool = True,
) -> dict[str, Any]:
    value = rule(name, priority, conditions)
    value.update(
        {
            "description": description,
            "algorithm": {"type": "static"},
            "modelRefs": [
                {
                    "model": model,
                    "use_reasoning": use_reasoning,
                    "reasoning_effort": effort,
                }
            ],
        }
    )
    return value


def decision_by_name(base: dict[str, Any], name: str) -> dict[str, Any]:
    for item in base["routing"]["decisions"]:
        if item.get("name") == name:
            return copy.deepcopy(item)
    raise KeyError(name)


def build_decisions(base: dict[str, Any]) -> list[dict[str, Any]]:
    guard = decision_by_name(base, "guard")
    guard["description"] = (
        "Decline unsafe requests and obvious prompt attacks before any "
        "generation backend is called."
    )

    return [
        guard,
        static_decision(
            name="long_context",
            priority=900,
            description="Long requests use Fireworks Kimi K3.",
            model=KIMI_MODEL,
            effort="high",
            conditions=[{"type": "context", "name": "beyond_qwen_window"}],
        ),
        static_decision(
            name="vision",
            priority=850,
            description="Images and screenshots stay on the local MI300X model.",
            model=LOCAL_MODEL,
            effort="medium",
            conditions=[{"type": "conversation", "name": "has_image"}],
        ),
        static_decision(
            name="recovery",
            priority=800,
            description=(
                "Corrections and recovery use Fireworks Kimi K3 at "
                "maximum effort."
            ),
            model=KIMI_MODEL,
            effort="max",
            conditions=[
                {"type": "conversation", "name": "has_prior_answer"},
                {"type": "decision", "name": "correction"},
            ],
        ),
        static_decision(
            name="code_agentic",
            priority=760,
            description=(
                "Code requests with tools use Fireworks GLM-5.3-Flash."
            ),
            model=GLM_MODEL,
            effort="medium",
            conditions=[
                {"type": "decision", "name": "task", "label": "code"},
                {
                    "operator": "OR",
                    "conditions": [
                        {"type": "conversation", "name": "has_tools"},
                        {"type": "conversation", "name": "tool_loop"},
                    ],
                },
            ],
        ),
        static_decision(
            name="agentic",
            priority=700,
            description=(
                "Normal web, browser and tool orchestration uses "
                "Fireworks GLM-5.3-Flash."
            ),
            model=GLM_MODEL,
            effort="high",
            conditions=[
                {
                    "operator": "OR",
                    "conditions": [
                        {"type": "conversation", "name": "tool_loop"},
                        {
                            "operator": "AND",
                            "conditions": [
                                {"type": "conversation", "name": "has_tools"},
                                {
                                    "operator": "OR",
                                    "conditions": [
                                        {
                                            "type": "decision",
                                            "name": "task",
                                            "label": "agentic",
                                        },
                                        {
                                            "type": "decision",
                                            "name": "needs",
                                            "label": "tools",
                                            "predicate": {"gte": 0.5},
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        ),
        static_decision(
            name="facts",
            priority=600,
            description="Exact factual work uses Fireworks GLM-5.3-Flash.",
            model=GLM_MODEL,
            effort="medium",
            conditions=[
                {"type": "decision", "name": "precise_facts"},
                {
                    "operator": "OR",
                    "conditions": [
                        {"type": "decision", "name": "task", "label": "facts"},
                        {"type": "decision", "name": "task", "label": "analysis"},
                        {"type": "decision", "name": "task", "label": "writing"},
                    ],
                },
            ],
        ),
        static_decision(
            name="frontier",
            priority=500,
            description=(
                "Research-level requests use Fireworks Kimi K3 at "
                "maximum effort."
            ),
            model=KIMI_MODEL,
            effort="max",
            conditions=[{"type": "projection", "name": "effort_max"}],
        ),
        static_decision(
            name="code",
            priority=450,
            description="Code generation and debugging use GLM-5.3-Flash.",
            model=GLM_MODEL,
            effort="medium",
            conditions=[
                {"type": "decision", "name": "task", "label": "code"},
                {
                    "operator": "OR",
                    "conditions": [
                        {"type": "projection", "name": "effort_medium"},
                        {"type": "projection", "name": "effort_high"},
                    ],
                },
            ],
        ),
        static_decision(
            name="hard",
            priority=400,
            description="Hard non-agentic reasoning uses GLM-5.3-Flash.",
            model=GLM_MODEL,
            effort="high",
            conditions=[
                {
                    "operator": "OR",
                    "conditions": [
                        {"type": "projection", "name": "effort_high"},
                        {
                            "operator": "AND",
                            "conditions": [
                                {"type": "decision", "name": "task", "label": "stem"},
                                {"type": "decision", "name": "difficulty"},
                            ],
                        },
                    ],
                }
            ],
        ),
        static_decision(
            name="standard",
            priority=300,
            description="Everyday reasoning stays on local Qwen3.8-27B.",
            model=LOCAL_MODEL,
            effort="medium",
            conditions=[{"type": "projection", "name": "effort_medium"}],
        ),
        static_decision(
            name="fast",
            priority=100,
            description="Simple requests stay local with thinking disabled.",
            model=LOCAL_MODEL,
            effort="off",
            use_reasoning=False,
            conditions=[],
        ),
    ]


def render(args: argparse.Namespace) -> dict[str, Any]:
    config = yaml.safe_load(args.input.read_text(encoding="utf-8"))
    config.pop("evaluation", None)
    config["entrypoints"] = [{"model_names": ["vllm-sr/auto"], "recipe": "default"}]
    config["providers"] = {
        "defaults": {"model": LOCAL_MODEL},
        "models": [
            local_backend(),
            fireworks_backend(
                logical_name=GLM_MODEL,
                catalog=GLM_MODEL,
                provider_model_id="accounts/fireworks/models/glm-5p3-flash",
                prompt_rate=0.15,
                completion_rate=0.50,
                cached_input_rate=0.03,
            ),
            fireworks_backend(
                logical_name=KIMI_MODEL,
                catalog=KIMI_MODEL,
                provider_model_id=args.kimi_provider_model,
                prompt_rate=3.00,
                completion_rate=15.00,
                cached_input_rate=0.30,
            ),
        ],
    }
    config["routing"]["modelCards"] = [
        {
            "name": LOCAL_MODEL,
            "description": (
                "Local AMD MI300X model for fast, standard and vision work. "
                "No external API charge."
            ),
            "tags": ["location:local", "hardware:mi300x", "role:default"],
        },
        {
            "name": GLM_MODEL,
            "description": (
                "Fireworks GLM-5.3-Flash for code, tools, facts and "
                "cost-efficient agent turns."
            ),
            "tags": ["location:fireworks", "role:code", "role:agentic"],
        },
        {
            "name": KIMI_MODEL,
            "description": (
                "Fireworks Kimi K3 for premium frontier reasoning, recovery, "
                "vision and million-token context."
            ),
            "tags": ["location:fireworks", "role:frontier", "role:recovery"],
        },
    ]
    config["routing"]["decisions"] = build_decisions(config)
    config.setdefault("global", {}).setdefault("services", {}).setdefault(
        "router_replay", {}
    ).update(
        {
            "enabled": True,
            "capture_personal_data": False,
            "max_records": 5000,
            "store_backend": "memory",
        }
    )
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--kimi-provider-model",
        default="accounts/fireworks/models/kimi-k3",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = render(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(config, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "models": [
                    row["name"] for row in config["providers"]["models"]
                ],
                "decisions": [
                    row["name"] for row in config["routing"]["decisions"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

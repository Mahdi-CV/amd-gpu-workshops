#!/usr/bin/env python3
"""Acceptance test for the keyword-first D3 Lite workshop flow."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import time

import requests
import yaml


if os.getenv("WORKSHOP_E2E_CONFIRM_MUTATION") != "1":
    raise SystemExit(
        "Set WORKSHOP_E2E_CONFIRM_MUTATION=1 to acknowledge temporary "
        "Router configuration changes."
    )


MANAGEMENT_API = os.getenv(
    "ROUTER_MANAGEMENT_API",
    "http://127.0.0.1:8080",
).rstrip("/")
ROUTER_API = os.getenv(
    "ROUTER_API",
    "http://127.0.0.1:8898",
).rstrip("/")
DECISION_MODEL_ENDPOINT = os.getenv(
    "DECISION_MODEL_ENDPOINT",
    "http://127.0.0.1:8100",
).rstrip("/")
EVIDENCE_DIR = Path(
    os.getenv(
        "WORKSHOP_E2E_EVIDENCE_DIR",
        "/workspace/state/acceptance",
    )
)
ROUTED_MODEL = "vllm-sr/auto"
DECISION_THRESHOLD = float(
    os.getenv("WORKSHOP_D3_THRESHOLD", "0.50")
)
DECISION_QUESTION = (
    "Does answering this request well require multi-step reasoning, "
    "comparison of alternatives, diagnosis, or a justified plan?"
)


def active_config_with_etag() -> tuple[dict, str | None]:
    response = requests.get(
        f"{MANAGEMENT_API}/api/v1/config",
        timeout=30,
    )
    response.raise_for_status()
    return response.json(), response.headers.get("ETag")


def default_recipe(config: dict) -> dict:
    recipes = config.get("recipes", [])
    for recipe in recipes:
        if recipe.get("name") == "default":
            return recipe
    if len(recipes) == 1:
        return recipes[0]
    raise RuntimeError("The active configuration has no default recipe.")


def wait_ready(timeout_seconds: int = 300) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_body = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                f"{MANAGEMENT_API}/ready",
                timeout=10,
            )
            if response.ok:
                last_body = response.json()
                ready_models = last_body.get("ready_models")
                total_models = last_body.get("total_models")
                models_ready = (
                    total_models in (None, 0)
                    or ready_models == total_models
                )
                if last_body.get("ready") is True and models_ready:
                    return last_body
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError(
        f"The Router did not become ready: {last_body!r}"
    )


def apply_recipe(recipe: dict) -> dict:
    config, etag = active_config_with_etag()
    active_recipe = default_recipe(config)
    active_recipe["strategy"] = "priority"
    active_recipe["signals"] = copy.deepcopy(
        recipe.get("signals", {})
    )
    active_recipe["decisions"] = copy.deepcopy(
        recipe.get("decisions", [])
    )
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
    wait_ready()
    return default_recipe(active_config_with_etag()[0])


def preview(prompt: str) -> dict:
    response = requests.post(
        f"{MANAGEMENT_API}/api/v1/routing/preview?trace=true",
        json={"model": ROUTED_MODEL, "text": prompt},
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    decision_result = body.get("decision_result") or {}
    decision = (
        decision_result.get("decision_name")
        or decision_result.get("decision")
        or decision_result.get("name")
        or body.get("selected_decision")
        or body.get("decision")
    )
    model = (
        decision_result.get("model")
        or decision_result.get("selected_model")
        or body.get("selected_model")
        or body.get("model")
    )
    if isinstance(decision, dict):
        decision = decision.get("name")
    if isinstance(model, dict):
        model = model.get("name")
    return {
        "prompt": prompt,
        "decision": decision,
        "selected_model": model,
        "signal_values": body.get("signal_values", {}),
        "raw": body,
    }


def require_route(
    prompt: str,
    *,
    decision: str,
    model: str,
) -> dict:
    observed = preview(prompt)
    if (
        observed["decision"] != decision
        or observed["selected_model"] != model
    ):
        raise RuntimeError(
            "Unexpected route:\n"
            f"prompt={prompt!r}\n"
            f"expected={decision} -> {model}\n"
            f"observed={observed['decision']} -> "
            f"{observed['selected_model']}\n"
            f"signals={observed['signal_values']}"
        )
    print(f"PASS {decision} -> {model}: {prompt[:72]}")
    return observed


def fallback_decision() -> dict:
    return {
        "name": "routine-fallback",
        "description": "Everything else uses the routine route.",
        "priority": 100,
        "rules": {"operator": "AND", "conditions": []},
        "modelRefs": [{"model": "routine-model"}],
        "algorithm": {"type": "static"},
    }


def keyword_recipe() -> dict:
    return {
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
                "description": (
                    "Explicit security reviews use the reasoning route."
                ),
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
            fallback_decision(),
        ],
    }


def semantic_recipe(
    question: str = DECISION_QUESTION,
    threshold: float = DECISION_THRESHOLD,
) -> dict:
    return {
        "signals": {
            "systemone": [
                {
                    "name": "needs-deep-reasoning",
                    "description": (
                        "D3 Lite judges whether deeper reasoning is useful."
                    ),
                    "question": {
                        "type": "noul",
                        "instructions": question,
                    },
                    "predicate": {"gte": threshold},
                    "timeout_ms": 60000,
                }
            ]
        },
        "decisions": [
            {
                "name": "semantic-reasoning",
                "description": (
                    "Meaning indicates that the reasoning route is useful."
                ),
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
            fallback_decision(),
        ],
    }


def private_recipe() -> dict:
    recipe = semantic_recipe()
    recipe["signals"]["keywords"] = [
        {
            "name": "private-marker",
            "operator": "OR",
            "keywords": ["[PRIVATE]"],
            "case_sensitive": False,
        }
    ]
    recipe["decisions"].insert(
        0,
        {
            "name": "private-local",
            "description": (
                "Private requests must stay on the routine route."
            ),
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
    return recipe


def launch_recipe() -> dict:
    recipe = semantic_recipe()
    recipe["signals"]["keywords"] = [
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
    recipe["decisions"] = [
        {
            "name": "private-local",
            "priority": 400,
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
        {
            "name": "security-review",
            "priority": 300,
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
            **copy.deepcopy(
                semantic_recipe()["decisions"][0]
            ),
            "priority": 200,
        },
        fallback_decision(),
    ]
    return recipe


def main() -> None:
    services = {
        "routine": "http://127.0.0.1:8002/v1/models",
        "reasoning": "http://127.0.0.1:8001/v1/models",
        "d3-lite": f"{DECISION_MODEL_ENDPOINT}/health",
        "router": f"{ROUTER_API}/v1/models",
        "management": f"{MANAGEMENT_API}/health",
    }
    for name, url in services.items():
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"PASS service ready: {name}")

    baseline, _ = active_config_with_etag()
    evidence: dict[str, object] = {
        "started_at": time.time(),
        "threshold": DECISION_THRESHOLD,
    }

    try:
        apply_recipe(keyword_recipe())
        evidence["keyword"] = {
            "marked": require_route(
                (
                    "[SECURITY-REVIEW] Review this token-rotation "
                    "design and recommend two mitigations."
                ),
                decision="security-review",
                model="reasoning-model",
            ),
            "untagged": require_route(
                "Define a security review in one sentence.",
                decision="routine-fallback",
                model="routine-model",
            ),
        }

        apply_recipe(semantic_recipe())
        evidence["semantic"] = {
            "routine": require_route(
                "Define a software rollback in one sentence.",
                decision="routine-fallback",
                model="routine-model",
            ),
            "reasoning": require_route(
                (
                    "A checkout sometimes charges customers twice after "
                    "a timeout. Diagnose likely causes, compare three "
                    "fixes, and recommend a safe rollout."
                ),
                decision="semantic-reasoning",
                model="reasoning-model",
            ),
        }

        comparison_question = (
            "Does the user ask to compare competing technical approaches "
            "and recommend or justify one?"
        )
        apply_recipe(
            semantic_recipe(
                question=comparison_question,
                threshold=DECISION_THRESHOLD,
            )
        )
        evidence["comparison"] = {
            "positive": require_route(
                (
                    "Compare canary and blue-green deployment for a "
                    "small team and recommend one."
                ),
                decision="semantic-reasoning",
                model="reasoning-model",
            ),
            "negative": require_route(
                "Define blue-green deployment in one sentence.",
                decision="routine-fallback",
                model="routine-model",
            ),
        }

        apply_recipe(private_recipe())
        evidence["private"] = {
            "public": require_route(
                (
                    "Compare three strategies for reducing a service "
                    "outage, explain their tradeoffs, and recommend a "
                    "safe rollout."
                ),
                decision="semantic-reasoning",
                model="reasoning-model",
            ),
            "private": require_route(
                (
                    "[PRIVATE] Compare three strategies for reducing a "
                    "service outage, explain their tradeoffs, and "
                    "recommend a safe rollout."
                ),
                decision="private-local",
                model="routine-model",
            ),
        }

        apply_recipe(launch_recipe())
        cases = {
            "launch_update": {
                "prompt": (
                    "Rewrite this launch update clearly: rollout paused "
                    "at 40 percent while the team checks elevated retry "
                    "volume."
                ),
                "decision": "routine-fallback",
                "model": "routine-model",
            },
            "architecture": {
                "prompt": (
                    "Compare canary, blue-green, and rolling deployment "
                    "for this service. Recommend one and justify rollback "
                    "criteria."
                ),
                "decision": "semantic-reasoning",
                "model": "reasoning-model",
            },
            "security_review": {
                "prompt": (
                    "[SECURITY-REVIEW] Review the token-rotation design, "
                    "identify attack paths, and recommend mitigations."
                ),
                "decision": "security-review",
                "model": "reasoning-model",
            },
            "private_note": {
                "prompt": (
                    "[PRIVATE] ACCOUNT-ID 4821: summarize this payment "
                    "note in one sentence: the invoice is 12 days overdue."
                ),
                "decision": "private-local",
                "model": "routine-model",
            },
            "private_analysis": {
                "prompt": (
                    "[PRIVATE] Compare three customer-recovery options, "
                    "explain their tradeoffs, and recommend a rollout."
                ),
                "decision": "private-local",
                "model": "routine-model",
            },
            "three_way_collision": {
                "prompt": (
                    "[PRIVATE] [SECURITY-REVIEW] Investigate leaked "
                    "credentials, compare containment strategies, and "
                    "recommend a rollout."
                ),
                "decision": "private-local",
                "model": "routine-model",
            },
        }
        evidence["launch_control"] = {
            name: require_route(
                case["prompt"],
                decision=case["decision"],
                model=case["model"],
            )
            for name, case in cases.items()
        }
        print("PASS Launch Control -> ROUTE-CONTROL-GREEN")

        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output = EVIDENCE_DIR / "route-one-d3-lite-e2e.json"
        output.write_text(
            json.dumps(evidence, indent=2, default=repr),
            encoding="utf-8",
        )
        print(f"PASS evidence saved to {output}")
    finally:
        _, etag = active_config_with_etag()
        headers = {"If-Match": etag} if etag else {}
        restore = requests.put(
            f"{MANAGEMENT_API}/api/v1/config",
            headers=headers,
            json={
                "yaml": yaml.safe_dump(
                    baseline,
                    sort_keys=False,
                )
            },
            timeout=180,
        )
        restore.raise_for_status()
        wait_ready()
        print("PASS baseline restored")


if __name__ == "__main__":
    main()

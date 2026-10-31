from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import yaml


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "render_config",
    ROOT / "router/render_config.py",
)
assert spec and spec.loader
render_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_config)


def test_router_pool_and_priority_order(tmp_path):
    args = SimpleNamespace(
        input=ROOT / "router/decision-balance-base.yaml",
        output=tmp_path / "config.yaml",
        kimi_provider_model="accounts/fireworks/models/kimi-k3",
    )
    body = render_config.render(args)
    assert [row["name"] for row in body["providers"]["models"]] == [
        "qwen/qwen3.8-27b",
        "zai/glm-5.3-flash",
        "moonshot/kimi-k3",
    ]
    decisions = body["routing"]["decisions"]
    priorities = [int(row["priority"]) for row in decisions]
    assert priorities == sorted(priorities, reverse=True)
    routes = {row["name"]: row["modelRefs"][0]["model"] for row in decisions if row.get("modelRefs")}
    assert routes["fast"] == "qwen/qwen3.8-27b"
    assert routes["code_agentic"] == "zai/glm-5.3-flash"
    assert routes["frontier"] == "moonshot/kimi-k3"
    assert routes["recovery"] == "moonshot/kimi-k3"
    recovery = next(
        row for row in decisions if row["name"] == "recovery"
    )
    assert {
        "operator": "NOT",
        "conditions": [
            {
                "type": "conversation",
                "name": "tool_loop",
            }
        ],
    } in recovery["rules"]["conditions"]
    context = {
        row["name"]: row for row in body["routing"]["signals"]["context"]
    }
    assert context["beyond_qwen_window"]["min_tokens"] == "56K"
    jailbreak = {
        row["name"]: row for row in body["routing"]["signals"]["jailbreak"]
    }
    assert jailbreak["prompt_attack"]["threshold"] == 0.999
    cards = {
        row["name"]: row for row in body["routing"]["modelCards"]
    }
    assert cards["qwen/qwen3.8-27b"]["context_window_size"] == 65536
    for model in body["providers"]["models"][1:]:
        assert "chat_path" not in model["backend_refs"][0]
        assert model["backend_refs"][0]["base_url"] == (
            "http://fireworks-shim:8090/v1"
        )
    assert body["global"]["services"]["response_api"]["enabled"] is False
    assert (
        body["global"]["services"]["observability"]["tracing"]["enabled"]
        is False
    )


def test_rendered_config_serializes(tmp_path):
    output = tmp_path / "config.yaml"
    args = SimpleNamespace(
        input=ROOT / "router/decision-balance-base.yaml",
        output=output,
        kimi_provider_model="accounts/fireworks/models/kimi-k3",
    )
    body = render_config.render(args)
    output.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    assert yaml.safe_load(output.read_text())["entrypoints"][0]["model_names"] == [
        "vllm-sr/auto"
    ]

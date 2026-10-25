from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "router/decision-balance-code-agentic/patch_config.py"
)
SPEC = importlib.util.spec_from_file_location("code_agentic_patch", SCRIPT)
patcher = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(patcher)


def base_config() -> dict:
    return {
        "version": "v0.3",
        "global": {"services": {"router_replay": {"enabled": True}}},
        "providers": {
            "models": [
                {
                    "name": "zai/glm-5.3-flash",
                    "backend_refs": [{"endpoint": "glm.internal:8000"}],
                },
                {
                    "name": "qwen/qwen3.8-flash-next",
                    "backend_refs": [{"endpoint": "flash.internal:8000"}],
                },
                {
                    "name": "qwen/qwen3.8-27b",
                    "backend_refs": [{"endpoint": "qwen.internal:8000"}],
                },
            ]
        },
        "routing": {
            "decisions": [
                {"name": "recovery", "priority": 800},
                {"name": "agentic", "priority": 700},
                {"name": "code", "priority": 450},
                {"name": "fast", "priority": 100},
            ]
        },
    }


def test_patch_inserts_between_recovery_and_agentic():
    source = base_config()
    patched, changed = patcher.patch_document(source)
    assert changed
    assert source["routing"]["decisions"][1]["name"] == "agentic"
    rows = patched["routing"]["decisions"]
    assert [row["name"] for row in rows] == [
        "recovery",
        "code_agentic",
        "agentic",
        "code",
        "fast",
    ]
    route = rows[1]
    assert route == patcher.CODE_AGENTIC_DECISION
    assert route["modelRefs"][0]["model"] == "qwen/qwen3.8-flash-next"
    assert patched["global"] == source["global"]
    assert patched["providers"] == source["providers"]


def test_patch_is_idempotent_for_exact_route():
    patched, changed = patcher.patch_document(base_config())
    assert changed
    repeated, repeated_changed = patcher.patch_document(patched)
    assert not repeated_changed
    assert repeated == patched


def test_patch_refuses_priority_collision():
    source = base_config()
    source["routing"]["decisions"].insert(
        1,
        {"name": "some_other_route", "priority": 750},
    )
    with pytest.raises(patcher.ConfigError, match="already used"):
        patcher.patch_document(source)


def test_patch_refuses_incompatible_existing_route():
    source = base_config()
    source["routing"]["decisions"].insert(
        1,
        {
            "name": "code_agentic",
            "priority": 750,
            "modelRefs": [{"model": "zai/glm-5.3-flash"}],
        },
    )
    with pytest.raises(patcher.ConfigError, match="different"):
        patcher.patch_document(source)


def test_patch_refuses_missing_flash_provider():
    source = base_config()
    source["providers"]["models"] = [
        model
        for model in source["providers"]["models"]
        if model["name"] != "qwen/qwen3.8-flash-next"
    ]
    with pytest.raises(patcher.ConfigError, match="does not define"):
        patcher.patch_document(source)


def test_rendered_yaml_round_trips():
    patched, _ = patcher.patch_document(base_config())
    rendered = patcher.render_yaml(patched)
    assert yaml.safe_load(rendered) == patched

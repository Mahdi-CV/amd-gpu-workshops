from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
pytest.importorskip("aiohttp")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proxy = load("logging_proxy", ROOT / "bin/logging_proxy.py")
endpoint = load("endpoint_access", ROOT / "bin/endpoint_access.py")


def test_endpoint_access_reads_file_secret(tmp_path):
    secret = tmp_path / "key"
    secret.write_text("secret-value\n")
    base, key = endpoint.endpoint_and_key(
        base_url="https://example.test/api",
        api_key_file=str(secret),
    )
    assert base == "https://example.test/api/v1"
    assert key == "secret-value"


def test_content_shape_keeps_hashes_not_text():
    rows = proxy.content_shape(
        [{"role": "user", "content": "private prompt"}]
    )
    assert rows[0]["content_chars"] == len("private prompt")
    assert rows[0]["content_sha256"]
    assert "private prompt" not in json.dumps(rows)


def test_exact_recipe_costs():
    rates = {
        "zai/glm-5.3-flash": {
            "aliases": ["glm-5.3-flash"],
            "prompt_per_1m": 0.44,
            "completion_per_1m": 4.35,
        }
    }
    model, cost = proxy.relative_cost(
        "s3/workshop-glm-5.3-flash-import",
        {"prompt_tokens": 1000, "completion_tokens": 100},
        rates,
    )
    assert model == "zai/glm-5.3-flash"
    assert cost == 0.000875


def test_phase_file_is_explicit(tmp_path):
    phase = tmp_path / "phase.json"
    phase.write_text('{"phase":"bug_reviewer"}')
    state = proxy.ProxyState(
        upstream="https://example.test/v1",
        api_key="secret",
        log_path=tmp_path / "routes.jsonl",
        phase_path=phase,
        rates={},
        timeout_seconds=30,
    )
    assert state.phase() == "bug_reviewer"

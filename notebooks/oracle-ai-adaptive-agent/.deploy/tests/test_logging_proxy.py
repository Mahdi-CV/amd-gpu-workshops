from __future__ import annotations

import argparse
import asyncio
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


def test_route_is_logged_when_client_closes_stream_early(tmp_path):
    from aiohttp import web

    async def scenario() -> list[dict]:
        async def upstream_chat(request: web.Request) -> web.StreamResponse:
            response = web.StreamResponse(
                headers={
                    "Content-Type": "text/event-stream",
                    "x-vsr-selected-decision": "code",
                    "x-vsr-selected-model": "qwen/qwen3.8-flash-next",
                }
            )
            await response.prepare(request)
            await response.write(
                b'data: {"model":"qwen/qwen3.8-flash-next","choices":'
                b'[{"finish_reason":"stop"}]}\n\n'
            )
            await asyncio.sleep(0.3)
            await response.write(
                b'data: {"choices":[],"usage":{"prompt_tokens":10,'
                b'"completion_tokens":5}}\n\ndata: [DONE]\n\n'
            )
            await response.write_eof()
            return response

        upstream_app = web.Application()
        upstream_app.router.add_post("/v1/chat/completions", upstream_chat)
        upstream_runner = web.AppRunner(upstream_app)
        await upstream_runner.setup()
        upstream_site = web.TCPSite(upstream_runner, "127.0.0.1", 0)
        await upstream_site.start()
        upstream_port = upstream_site._server.sockets[0].getsockname()[1]

        key = tmp_path / "key"
        key.write_text("secret")
        log = tmp_path / "routes.jsonl"
        args = argparse.Namespace(
            base_url=f"http://127.0.0.1:{upstream_port}/v1",
            api_key_file=str(key),
            log_jsonl=log,
            phase_file=tmp_path / "phase.json",
            cost_factors=None,
            timeout_seconds=30,
        )
        proxy_runner = web.AppRunner(await proxy.create_app(args))
        await proxy_runner.setup()
        proxy_site = web.TCPSite(proxy_runner, "127.0.0.1", 0)
        await proxy_site.start()
        proxy_port = proxy_site._server.sockets[0].getsockname()[1]

        body = b'{"model":"vllm-sr/auto","stream":true,"messages":[]}'
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(
            b"POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        await reader.readuntil(b"finish_reason")
        writer.close()
        await asyncio.sleep(1.0)

        await proxy_runner.cleanup()
        await upstream_runner.cleanup()
        return [json.loads(line) for line in log.read_text().splitlines()]

    rows = asyncio.run(scenario())
    assert len(rows) == 1
    assert rows[0]["routing_headers"]["x-vsr-selected-decision"] == "code"
    assert rows[0]["usage"]["completion_tokens"] == 5

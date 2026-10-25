#!/usr/bin/env python3
"""Streaming, secret-safe OpenAI proxy with vLLM-SR route telemetry."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import (
    ClientConnectionResetError,
    ClientError,
    ClientSession,
    ClientTimeout,
    web,
)

from endpoint_access import endpoint_and_key


EXCLUDED_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=19090)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key-file", default="")
    parser.add_argument("--log-jsonl", type=Path, required=True)
    parser.add_argument("--phase-file", type=Path, required=True)
    parser.add_argument("--cost-factors", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def content_shape(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    shaped: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            chars = len(content)
            digest = hashlib.sha256(content.encode()).hexdigest()
        else:
            chars = len(json.dumps(content, ensure_ascii=False)) if content else 0
            digest = canonical_hash(content) if content else ""
        shaped.append(
            {
                "role": message.get("role"),
                "content_chars": chars,
                "content_sha256": digest,
                "tool_calls": len(message.get("tool_calls") or []),
            }
        )
    return shaped


def usage_from(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "cached_tokens": int(prompt_details.get("cached_tokens") or 0),
        "created_cache_tokens": int(
            prompt_details.get("created_cache_tokens") or 0
        ),
        "reasoning_tokens": int(
            completion_details.get("reasoning_tokens")
            or usage.get("reasoning_tokens")
            or 0
        ),
    }


def parse_response(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" not in content_type:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    result: dict[str, Any] = {"choices": [], "usage": {}}
    finish_reason = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        value = line[5:].strip()
        if not value or value == "[DONE]":
            continue
        try:
            chunk = json.loads(value)
        except json.JSONDecodeError:
            continue
        if chunk.get("model"):
            result["model"] = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            result["usage"] = chunk["usage"]
        choices = chunk.get("choices") or []
        if choices and choices[0].get("finish_reason"):
            finish_reason = choices[0]["finish_reason"]
    if finish_reason:
        result["choices"] = [{"finish_reason": finish_reason}]
    return result


def load_rates(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.is_file():
        return {}
    body = json.loads(path.read_text(encoding="utf-8"))
    return body.get("models") or {}


def normalized_model(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value)


def canonical_model(value: str, rates: dict[str, dict[str, Any]]) -> str | None:
    target = normalized_model(value)
    matches = []
    for model_id, details in rates.items():
        aliases = [model_id, *(details.get("aliases") or [])]
        if any(normalized_model(str(alias)) in target for alias in aliases):
            matches.append(model_id)
    return matches[0] if len(matches) == 1 else None


def relative_cost(
    model: str,
    usage: dict[str, int],
    rates: dict[str, dict[str, Any]],
) -> tuple[str | None, float | None]:
    model_id = canonical_model(model, rates)
    if not model_id:
        return None, None
    pricing = rates[model_id]
    cost = (
        usage["prompt_tokens"] * float(pricing["prompt_per_1m"])
        + usage["completion_tokens"] * float(pricing["completion_per_1m"])
    ) / 1_000_000
    return model_id, round(cost, 8)


class ProxyState:
    def __init__(
        self,
        *,
        upstream: str,
        api_key: str,
        log_path: Path,
        phase_path: Path,
        rates: dict[str, dict[str, Any]],
        timeout_seconds: float,
    ) -> None:
        self.upstream = upstream.rstrip("/")
        self.api_key = api_key
        self.log_path = log_path
        self.phase_path = phase_path
        self.rates = rates
        self.timeout = ClientTimeout(total=timeout_seconds)
        self.counter = 0
        self.counter_lock = asyncio.Lock()
        self.log_lock = asyncio.Lock()
        self.session: ClientSession | None = None
        self.is_ready = False
        log_path.parent.mkdir(parents=True, exist_ok=True)
        phase_path.parent.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        self.session = ClientSession(timeout=self.timeout)

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()

    async def request_id(self) -> int:
        async with self.counter_lock:
            self.counter += 1
            return self.counter

    def phase(self) -> str:
        try:
            body = json.loads(self.phase_path.read_text(encoding="utf-8"))
            return str(body.get("phase") or "unmarked")
        except (OSError, json.JSONDecodeError):
            return "unmarked"

    async def log(self, row: dict[str, Any]) -> None:
        async with self.log_lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def ready(request: web.Request) -> web.Response:
    state: ProxyState = request.app["state"]
    if state.is_ready:
        return web.json_response({"status": "ready"})
    assert state.session is not None
    try:
        async with state.session.get(
            state.upstream + "/models",
            headers={
                "Authorization": f"Bearer {state.api_key}",
                "Accept": "application/json",
            },
        ) as response:
            if response.status >= 400:
                return web.json_response(
                    {"status": "not_ready", "upstream_status": response.status},
                    status=503,
                )
    except (ClientError, asyncio.TimeoutError):
        return web.json_response({"status": "not_ready"}, status=503)
    state.is_ready = True
    return web.json_response({"status": "ready"})


async def forward(request: web.Request) -> web.StreamResponse:
    state: ProxyState = request.app["state"]
    assert state.session is not None
    request_id = await state.request_id()
    raw = await request.read()
    request_body: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                request_body = parsed
        except json.JSONDecodeError:
            pass

    path = request.path_qs
    if state.upstream.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    upstream_url = state.upstream + path
    headers = {
        "Authorization": f"Bearer {state.api_key}",
        "Accept": request.headers.get("Accept", "application/json"),
        "User-Agent": "openclaw-vllm-sr-workshop-proxy",
        "x-vsr-debug": "true",
    }
    if request.method in {"POST", "PUT", "PATCH"}:
        headers["Content-Type"] = request.headers.get(
            "Content-Type", "application/json"
        )

    started = time.perf_counter()
    first_byte: float | None = None
    response_buffer = bytearray()
    client_gone = False

    async def send(outgoing: web.StreamResponse, chunk: bytes | None) -> None:
        # OpenClaw can close a stream right after the last event. Keep reading
        # upstream so the route row (usage, routing headers) is still logged.
        nonlocal client_gone
        if client_gone:
            return
        try:
            if chunk is None:
                await outgoing.write_eof()
            else:
                await outgoing.write(chunk)
        except (ConnectionResetError, ClientConnectionResetError):
            client_gone = True

    try:
        async with state.session.request(
            request.method,
            upstream_url,
            data=raw if raw else None,
            headers=headers,
        ) as upstream:
            response_headers = {
                key: value
                for key, value in upstream.headers.items()
                if key.lower() not in EXCLUDED_RESPONSE_HEADERS
            }
            outgoing = web.StreamResponse(
                status=upstream.status,
                headers=response_headers,
            )
            try:
                await outgoing.prepare(request)
            except (ConnectionResetError, ClientConnectionResetError):
                client_gone = True
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                if first_byte is None:
                    first_byte = time.perf_counter() - started
                response_buffer.extend(chunk)
                await send(outgoing, chunk)
            await send(outgoing, None)
            status = upstream.status
            content_type = upstream.headers.get("Content-Type", "")
            routing_headers = {
                key.lower(): value
                for key, value in upstream.headers.items()
                if key.lower().startswith("x-vsr-")
            }
    except asyncio.TimeoutError:
        status = 504
        content_type = "application/json"
        routing_headers = {}
        payload = b'{"error":{"message":"upstream timeout","type":"proxy_error"}}'
        outgoing = web.StreamResponse(
            status=status,
            headers={"Content-Type": "application/json"},
        )
        await outgoing.prepare(request)
        await outgoing.write(payload)
        await outgoing.write_eof()
        response_buffer.extend(payload)
    except ClientError:
        status = 502
        content_type = "application/json"
        routing_headers = {}
        payload = b'{"error":{"message":"upstream unavailable","type":"proxy_error"}}'
        outgoing = web.StreamResponse(
            status=status,
            headers={"Content-Type": "application/json"},
        )
        await outgoing.prepare(request)
        await outgoing.write(payload)
        await outgoing.write_eof()
        response_buffer.extend(payload)

    elapsed = time.perf_counter() - started
    response_body = parse_response(bytes(response_buffer), content_type)
    choices = response_body.get("choices") or []
    usage = usage_from(response_body)
    selected_model = (
        routing_headers.get("x-vsr-selected-model")
        or str(response_body.get("model") or "")
    )
    cost_model, cost = relative_cost(selected_model, usage, state.rates)
    await state.log(
        {
            "timestamp": utc_now(),
            "request_id": request_id,
            "phase": state.phase(),
            "method": request.method,
            "path": request.path,
            "status": status,
            "latency_seconds": round(elapsed, 4),
            "first_byte_seconds": (
                round(first_byte, 4) if first_byte is not None else None
            ),
            "request_sha256": canonical_hash(request_body),
            "requested_model": request_body.get("model"),
            "response_model": response_body.get("model"),
            "selected_cost_model": cost_model,
            "finish_reason": (
                choices[0].get("finish_reason") if choices else None
            ),
            "message_shape": content_shape(request_body.get("messages")),
            "tool_count": len(request_body.get("tools") or []),
            "tool_schema_sha256": canonical_hash(request_body.get("tools") or []),
            "stream": request_body.get("stream"),
            "max_tokens": (
                request_body.get("max_tokens")
                or request_body.get("max_completion_tokens")
            ),
            "usage": usage,
            "estimated_relative_cost_xxx": cost,
            "routing_headers": routing_headers,
        }
    )
    return outgoing


async def create_app(args: argparse.Namespace) -> web.Application:
    upstream, key = endpoint_and_key(
        base_url=args.base_url,
        api_key_file=args.api_key_file,
    )
    state = ProxyState(
        upstream=upstream,
        api_key=key,
        log_path=args.log_jsonl,
        phase_path=args.phase_file,
        rates=load_rates(args.cost_factors),
        timeout_seconds=args.timeout_seconds,
    )
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app["state"] = state
    app.router.add_get("/healthz", health)
    app.router.add_get("/readyz", ready)
    app.router.add_route("*", "/{tail:.*}", forward)
    app.on_startup.append(lambda _app: state.start())
    app.on_cleanup.append(lambda _app: state.close())
    return app


def main() -> None:
    args = parse_args()
    web.run_app(
        create_app(args),
        host=args.listen_host,
        port=args.listen_port,
        print=None,
        access_log=None,
    )


if __name__ == "__main__":
    main()

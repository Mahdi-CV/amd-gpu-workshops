"""Normalize Fireworks OpenAI responses for vLLM-SR's strict codec."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


FIREWORKS_BASE_URL = os.getenv(
    "FIREWORKS_BASE_URL",
    "https://api.fireworks.ai/inference/v1",
).rstrip("/")
FIREWORKS_KEY_FILE = Path(
    os.getenv(
        "FIREWORKS_KEY_FILE",
        "/run/secrets/fireworks_api_key",
    )
)
UPSTREAM_TIMEOUT_SECONDS = 1200

HOP_BY_HOP_HEADERS = {
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

app = FastAPI(title="Fireworks OpenAI compatibility adapter")


@lru_cache(maxsize=1)
def fireworks_key() -> str:
    key = FIREWORKS_KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError("Fireworks API key secret is empty.")
    return key


def normalize_usage(usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    # Fireworks currently duplicates reasoning accounting here. The canonical
    # Chat Completions location is completion_tokens_details.
    usage.pop("output_tokens_details", None)


def normalize_tool_calls(tool_calls: Any, *, streaming: bool) -> None:
    if not isinstance(tool_calls, list):
        return
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        call.pop("name", None)
        if not streaming:
            # `index` belongs to streamed deltas, not final messages.
            call.pop("index", None)


def normalize_fireworks_payload(
    payload: dict[str, Any],
    *,
    streaming: bool,
) -> dict[str, Any]:
    normalize_usage(payload.get("usage"))
    for choice in payload.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        # Fireworks exposes private generation metadata that is not part of
        # the OpenAI Chat Completions response contract.
        choice.pop("raw_output", None)
        message_key = "delta" if streaming else "message"
        message = choice.get(message_key)
        if not isinstance(message, dict):
            continue
        message.pop("tools", None)
        normalize_tool_calls(
            message.get("tool_calls"),
            streaming=streaming,
        )
    return payload


def canonical_error(payload: Any, status_code: int) -> dict[str, Any]:
    value = payload.get("error", payload) if isinstance(payload, dict) else {}
    if not isinstance(value, dict):
        value = {}
    message = str(value.get("message") or f"Fireworks returned HTTP {status_code}")
    error_type = str(value.get("type") or "upstream_error")
    code = value.get("code")
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": value.get("param"),
            "code": str(code) if code is not None else str(status_code),
        }
    }


def response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() != "content-type"
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    fireworks_key()
    return {"status": "ok"}


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(path: str, request: Request) -> Response:
    raw = await request.body()
    request_payload: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                request_payload = parsed
        except json.JSONDecodeError:
            pass

    upstream_headers = {
        "Authorization": f"Bearer {fireworks_key()}",
        "Content-Type": request.headers.get(
            "content-type",
            "application/json",
        ),
        "Accept": request.headers.get("accept", "application/json"),
        "User-Agent": "amd-openclaw-fireworks-adapter",
    }
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            UPSTREAM_TIMEOUT_SECONDS,
            connect=30,
        )
    )
    context = client.stream(
        request.method,
        f"{FIREWORKS_BASE_URL}/{path}",
        content=raw or None,
        headers=upstream_headers,
    )
    upstream = await context.__aenter__()

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await context.__aexit__(None, None, None)
        await client.aclose()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        return JSONResponse(
            canonical_error(payload, upstream.status_code),
            status_code=upstream.status_code,
            headers=response_headers(upstream.headers),
        )

    is_stream = bool(request_payload.get("stream")) or (
        "text/event-stream"
        in upstream.headers.get("content-type", "")
    )
    if not is_stream:
        body = await upstream.aread()
        await context.__aexit__(None, None, None)
        await client.aclose()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return Response(
                body,
                status_code=upstream.status_code,
                headers=response_headers(upstream.headers),
                media_type=upstream.headers.get(
                    "content-type",
                    "application/octet-stream",
                ),
            )
        if isinstance(payload, dict):
            payload = normalize_fireworks_payload(
                payload,
                streaming=False,
            )
        return JSONResponse(
            payload,
            status_code=upstream.status_code,
            headers=response_headers(upstream.headers),
        )

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for line in upstream.aiter_lines():
                if line.startswith("data:"):
                    value = line[5:].strip()
                    if value and value != "[DONE]":
                        try:
                            payload = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                        else:
                            if isinstance(payload, dict):
                                payload = normalize_fireworks_payload(
                                    payload,
                                    streaming=True,
                                )
                                line = (
                                    "data: "
                                    + json.dumps(
                                        payload,
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    )
                                )
                yield (line + "\n").encode()
        finally:
            await context.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        headers=response_headers(upstream.headers),
        media_type="text/event-stream",
    )

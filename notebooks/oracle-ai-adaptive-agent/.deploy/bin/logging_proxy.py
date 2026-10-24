#!/usr/bin/env python3
"""Sanitizing OpenAI proxy that records vLLM-SR routing evidence."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from endpoint_access import endpoint_and_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=19090)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--log-jsonl", type=Path, required=True)
    return parser.parse_args()


def content_shape(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    shaped = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        shaped.append(
            {
                "role": message.get("role"),
                "content_chars": len(text),
                "content_sha256": hashlib.sha256(text.encode()).hexdigest()
                if text
                else "",
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
        "reasoning_tokens": int(completion_details.get("reasoning_tokens") or 0),
    }


def parse_payload(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" not in content_type:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    synthesized: dict[str, Any] = {"choices": [], "usage": {}}
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
        if not isinstance(chunk, dict):
            continue
        if chunk.get("model"):
            synthesized["model"] = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            synthesized["usage"] = chunk["usage"]
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            reason = choices[0].get("finish_reason")
            if reason:
                finish_reason = reason
    if finish_reason:
        synthesized["choices"] = [{"finish_reason": finish_reason}]
    return synthesized


def relative_cost_xxx(
    selected_model: str,
    usage: dict[str, int],
) -> float | None:
    factors = {
        "qwen/qwen3.8-27b": 1.0,
        "qwen/qwen3.8-flash-next": 1.99,
        "zai/glm-5.3-flash": 4.35,
    }
    factor = factors.get(selected_model)
    if factor is None:
        return None
    token_units = usage["prompt_tokens"] * 0.1 + usage["completion_tokens"]
    return round(token_units * factor / 1_000_000, 8)


class ProxyState:
    def __init__(self, upstream: str, api_key: str, log_path: Path) -> None:
        self.upstream = upstream.rstrip("/")
        self.api_key = api_key
        self.log_path = log_path
        self.lock = threading.Lock()
        self.request_id = 0
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: dict[str, Any]) -> None:
        with self.lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "OpenClawVSRProbe/1.0"

    @property
    def state(self) -> ProxyState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def do_GET(self) -> None:
        self.forward(None)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        self.forward(raw)

    def forward(self, raw: bytes | None) -> None:
        self.state.request_id += 1
        request_id = self.state.request_id
        started = time.perf_counter()
        request_payload: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                request_payload = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
        path = self.path
        if self.state.upstream.endswith("/v1") and path.startswith("/v1/"):
            path = path[3:]
        upstream_url = self.state.upstream + path
        headers = {
            "Authorization": f"Bearer {self.state.api_key}",
            "Accept": self.headers.get("Accept", "application/json"),
            "User-Agent": "openclaw-vllm-sr-sanitizing-proxy",
            "x-vsr-debug": "true",
        }
        if raw is not None:
            headers["Content-Type"] = self.headers.get(
                "Content-Type", "application/json"
            )
        request = urllib.request.Request(
            upstream_url,
            data=raw,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                response_raw = response.read()
                status = response.status
                response_headers = dict(response.headers)
        except urllib.error.HTTPError as exc:
            response_raw = exc.read()
            status = exc.code
            response_headers = dict(exc.headers)
        elapsed = time.perf_counter() - started
        content_type = next(
            (
                value
                for key, value in response_headers.items()
                if key.lower() == "content-type"
            ),
            "",
        )
        response_payload = parse_payload(response_raw, content_type)

        routing_headers = {
            key.lower(): value
            for key, value in response_headers.items()
            if key.lower().startswith("x-vsr-")
        }
        parsed_usage = usage_from(response_payload)
        selected_model = routing_headers.get("x-vsr-selected-model", "")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": self.command,
            "path": self.path,
            "status": status,
            "latency_seconds": round(elapsed, 4),
            "requested_model": request_payload.get("model"),
            "request_keys": sorted(request_payload),
            "stream": request_payload.get("stream"),
            "message_shape": content_shape(request_payload.get("messages")),
            "tool_count": len(request_payload.get("tools") or []),
            "tool_choice": request_payload.get("tool_choice"),
            "max_tokens": request_payload.get("max_tokens"),
            "response_model": response_payload.get("model"),
            "finish_reason": (
                response_payload.get("choices", [{}])[0].get("finish_reason")
                if response_payload.get("choices")
                else None
            ),
            "usage": parsed_usage,
            "estimated_relative_cost_xxx": relative_cost_xxx(
                selected_model,
                parsed_usage,
            ),
            "routing_headers": routing_headers,
        }
        self.state.log(record)

        self.send_response(status)
        excluded = {
            "content-length",
            "connection",
            "transfer-encoding",
            "content-encoding",
        }
        for name, value in response_headers.items():
            if name.lower() not in excluded:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_raw)))
        self.end_headers()
        self.wfile.write(response_raw)


def main() -> None:
    args = parse_args()
    base_url, api_key = endpoint_and_key(
        base_url=args.base_url,
        api_key=args.api_key,
    )
    server = http.server.ThreadingHTTPServer(
        (args.listen_host, args.listen_port),
        Handler,
    )
    server.state = ProxyState(base_url, api_key, args.log_jsonl)  # type: ignore[attr-defined]
    print(
        json.dumps(
            {
                "listen": f"http://{args.listen_host}:{args.listen_port}/v1",
                "upstream_host": base_url.split("://", 1)[-1].split("/", 1)[0],
                "credential": "loaded; not displayed",
                "log": str(args.log_jsonl),
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()

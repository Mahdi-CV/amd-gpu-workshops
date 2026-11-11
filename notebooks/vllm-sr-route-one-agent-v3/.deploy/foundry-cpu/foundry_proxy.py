"""Stand-in for the two local model servers the vLLM-SR workshop expects.

Listens on 127.0.0.1:8002 (routine) and 127.0.0.1:8001 (reasoning) and forwards
OpenAI-style requests to Azure Foundry with the API key attached, so the router
and notebook run unchanged on a CPU-only lab VM. Standard library only.

Env:
  FOUNDRY_ENDPOINT     e.g. https://<resource>.services.ai.azure.com  (required)
  FOUNDRY_API_KEY      the key from the lab instructions panel         (required)
  FOUNDRY_PATH         chat path appended to the endpoint
                       (default /openai/v1/chat/completions)
  ROUTINE_DEPLOYMENT   Foundry deployment for port 8002 (default FW-Qwen3.8-27B)
  REASONING_DEPLOYMENT Foundry deployment for port 8001 (default FW-GLM-5.3-Flash)
  ROUTINE_PROVIDER_MODEL / REASONING_PROVIDER_MODEL
                       model ids reported on /v1/models, so the platform's
                       readiness check sees the names it was configured with
                       (default: the deployment names)
  HARDWARE_NOTE        system instruction added to every request (empty = off)
  USAGE_LOG            JSON-lines file with Foundry's full usage per request, cached
                       tokens included (default /workspace/logs/foundry_usage.jsonl)
"""

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT", "").strip().rstrip("/")
API_KEY = os.environ.get("FOUNDRY_API_KEY", "").strip()
CHAT_PATH = os.environ.get("FOUNDRY_PATH", "/openai/v1/chat/completions")
# The lab panel gives the full chat URL; accept that as well as a bare resource URL.
if ENDPOINT.endswith("/chat/completions"):
    CHAT_PATH = ""

# vLLM-only request fields. The notebook and the router send some of these to the local
# servers (e.g. chat_template_kwargs to switch thinking off); Azure may reject unknown fields.
VLLM_ONLY_FIELDS = {
    "chat_template_kwargs", "skip_special_tokens", "spaces_between_special_tokens",
    "separate_reasoning", "include_stop_str_in_output", "top_k", "min_p",
    "repetition_penalty", "guided_json", "guided_regex", "guided_choice", "guided_grammar",
}

_ROUTINE = os.environ.get("ROUTINE_DEPLOYMENT", "FW-Qwen3.8-27B")
_REASONING = os.environ.get("REASONING_DEPLOYMENT", "FW-GLM-5.3-Flash")
ROUTES = {
    8002: (_ROUTINE, os.environ.get("ROUTINE_PROVIDER_MODEL", _ROUTINE)),
    8001: (_REASONING, os.environ.get("REASONING_PROVIDER_MODEL", _REASONING)),
}


# Phi-4-multimodal on Foundry has no tool calling: any request carrying `tools` is refused
# ("auto tool choice requires --enable-auto-tool-choice"). The Dashboard Playground and
# Hermes always send tools, so with Phi-4 on the routine lane those requests go to a
# deployment that supports them. Other routine deployments keep their own tool calls.
TOOLS_DEPLOYMENT = {
    8002: os.environ.get(
        "ROUTINE_TOOLS_DEPLOYMENT",
        "FW-GLM-5.3-Flash" if _ROUTINE.startswith("Phi-4") else ""),
}


# The router refuses any response field outside the OpenAI chat-completions schema
# ("upstream response JSON contains a non-canonical field"); Fireworks adds raw_output
# and service_tier, Phi-4 adds audio_prompt_tokens. Responses are rebuilt from these keys.
_TOP_KEYS = ("id", "object", "created", "model", "choices", "usage", "system_fingerprint")
_CHOICE_KEYS = ("index", "message", "delta", "finish_reason", "logprobs")
_MESSAGE_KEYS = ("role", "content", "tool_calls")
_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _pick(obj, keys):
    return {k: obj[k] for k in keys if isinstance(obj, dict) and k in obj}


def _canonical_tool_call(call):
    out = _pick(call, ("index", "id", "type"))
    if isinstance(call.get("function"), dict):
        out["function"] = _pick(call["function"], ("name", "arguments"))
    return out


def canonical_completion(body, chunk):
    out = _pick(body, _TOP_KEYS)
    out.setdefault("object", "chat.completion.chunk" if chunk else "chat.completion")
    choices = []
    for choice in body.get("choices") or []:
        c = _pick(choice, _CHOICE_KEYS)
        for key in ("message", "delta"):
            if key in c:
                m = _pick(c[key], _MESSAGE_KEYS)
                if m.get("tool_calls"):
                    m["tool_calls"] = [_canonical_tool_call(t) for t in m["tool_calls"]]
                else:
                    m.pop("tool_calls", None)
                    if key == "message" and not m.get("content"):
                        # Thinking used the whole token budget; the router rejects an empty answer.
                        m["content"] = EMPTY_ANSWER_TEXT
                c[key] = m
        choices.append(c)
    out["choices"] = choices
    if isinstance(body.get("usage"), dict):
        out["usage"] = _pick(body["usage"], _USAGE_KEYS)
    elif "usage" in out:
        del out["usage"]
    return out


def canonical_error(status, raw):
    message = raw.decode("utf-8", "replace")
    try:
        err = json.loads(raw).get("error")
        if isinstance(err, dict) and err.get("message"):
            message = str(err["message"])
        elif isinstance(err, str):
            message = err
    except (ValueError, AttributeError):
        pass
    kind = "invalid_request_error" if 400 <= status < 500 else "server_error"
    return {"error": {"message": message, "type": kind, "param": None, "code": None}}


# Phi-4 has been seen to go silent on requests forwarded by the router while answering the
# same prompt directly in seconds; a request it leaves unanswered is retried on GLM so a
# workshop cell never hangs on it.
# Only for Phi: a thinking model such as Qwen can take longer than the cutoff on a normal answer.
FALLBACK_DEPLOYMENT = {8002: os.environ.get(
    "ROUTINE_FALLBACK_DEPLOYMENT",
    "FW-GLM-5.3-Flash" if _ROUTINE.startswith("Phi-4") else "")}
FALLBACK_AFTER_SECONDS = float(os.environ.get("FALLBACK_AFTER_SECONDS", "12"))

# GLM-5.3 is thinking-only: reasoning_effort "none" (and every other way of switching thinking
# off) is a 400. At its default effort it spends a small max_tokens entirely on thinking and
# returns no answer, which the router rejects; "low" answers with a few thinking tokens.
THINKING_ONLY_DEPLOYMENTS = {"FW-GLM-5.3-Flash"}
DEFAULT_REASONING_EFFORT = os.environ.get("DEFAULT_REASONING_EFFORT", "low")
EMPTY_ANSWER_TEXT = "[No answer text within the response token limit.]"


# Asked what they run on, the models answer "I don't know", but their visible thinking muses
# about vendors ("some might assume NVIDIA H100s"). This line goes on every request so they
# decline without speculating. HARDWARE_NOTE="" turns it off.
HARDWARE_NOTE = os.environ.get(
    "HARDWARE_NOTE",
    "Do not discuss, guess or speculate about the hardware, chips, accelerators, cloud "
    "or infrastructure you run on, and do not name any hardware vendor in that context. "
    "If asked, say only that you don't have that information.")


def add_hardware_note(payload):
    messages = payload.get("messages")
    if not HARDWARE_NOTE or not isinstance(messages, list):
        return payload
    first = messages[0] if messages and isinstance(messages[0], dict) else {}
    if first.get("role") == "system":
        content = first.get("content")
        if isinstance(content, str):
            merged = HARDWARE_NOTE + "\n\n" + content
        elif isinstance(content, list):
            merged = [{"type": "text", "text": HARDWARE_NOTE}] + content
        else:
            merged = HARDWARE_NOTE
        # One system message, kept first: some chat templates reject a second or a late one.
        messages = [dict(first, content=merged)] + messages[1:]
    else:
        messages = [{"role": "system", "content": HARDWARE_NOTE}] + messages
    return dict(payload, messages=messages)


# Foundry's usage, untrimmed (the router only gets the three canonical counts), one line per
# request. prompt_tokens_details.cached_tokens is what the PTU sizing's cache rate comes from.
USAGE_LOG = os.environ.get("USAGE_LOG", "/workspace/logs/foundry_usage.jsonl")
STREAM_USAGE = os.environ.get("STREAM_USAGE", "1") != "0"   # 0 = never add stream_options
_usage_lock = threading.Lock()


def log_usage(port, model, stream, usage):
    if not USAGE_LOG or not isinstance(usage, dict):
        return
    row = json.dumps({"ts": round(time.time(), 3), "port": port, "model": model,
                      "stream": bool(stream), "usage": usage})
    try:
        with _usage_lock, open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except OSError as e:
        sys.stderr.write(f"[{port}] usage log not written ({e})\n")


def prepare_for(deployment, payload):
    payload = dict(payload, model=deployment)
    if deployment in THINKING_ONLY_DEPLOYMENTS:
        if payload.get("reasoning_effort") in (None, "", "none", "minimal"):
            payload["reasoning_effort"] = DEFAULT_REASONING_EFFORT
    else:
        payload.pop("reasoning_effort", None)
    return payload


def make_handler(port):
    deployment, served_name = ROUTES[port]
    tools_deployment = TOOLS_DEPLOYMENT.get(port) or deployment

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 120  # a stalled client read fails instead of hanging the request forever

        def log_message(self, fmt, *args):
            sys.stderr.write(f"[{port}] {fmt % args}\n")

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") in ("/v1/models", "/models"):
                ids = list(dict.fromkeys([served_name, deployment]))
                self._json(200, {"object": "list", "data": [
                    {"id": i, "object": "model", "owned_by": "foundry"} for i in ids]})
            elif self.path.rstrip("/") in ("/health", "/healthz", ""):
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": f"not served here: {self.path}"})

        def _read_body(self):
            # A proxy may forward a rewritten body chunked, without Content-Length.
            if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                parts = []
                while True:
                    size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                    if size == 0:
                        self.rfile.readline()
                        break
                    parts.append(self.rfile.read(size))
                    self.rfile.readline()
                return b"".join(parts)
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def do_POST(self):
            sys.stderr.write(
                f"[{port}] <- {self.path} length={self.headers.get('Content-Length')} "
                f"te={self.headers.get('Transfer-Encoding')} expect={self.headers.get('Expect')}\n")
            raw = self._read_body() or b"{}"
            sys.stderr.write(f"[{port}]    body {len(raw)} bytes\n")
            try:
                payload = json.loads(raw)
            except ValueError:
                return self._json(400, {"error": "body is not JSON"})
            if not self.path.rstrip("/").endswith("chat/completions"):
                return self._json(404, {"error": f"only chat/completions is forwarded, got {self.path}"})
            for field in VLLM_ONLY_FIELDS & payload.keys():
                del payload[field]
            payload = add_hardware_note(payload)
            payload = prepare_for(tools_deployment if payload.get("tools") else deployment, payload)
            # A stream carries usage only when asked for, in a final chunk with no choices. That
            # chunk is logged, and passed on only if the caller asked for it itself.
            caller_wants_usage = bool((payload.get("stream_options") or {}).get("include_usage"))
            if payload.get("stream") and STREAM_USAGE and not caller_wants_usage:
                payload["stream_options"] = dict(payload.get("stream_options") or {}, include_usage=True)

            def request_for(body):
                sys.stderr.write(f"[{port}]    -> {body['model']} stream={body.get('stream')} "
                                 f"body={json.dumps(body)[:600]}\n")
                return urllib.request.Request(
                    ENDPOINT + CHAT_PATH,
                    data=json.dumps(body).encode(),
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "api-key": API_KEY,
                        "Authorization": f"Bearer {API_KEY}",
                    },
                )

            fallback = FALLBACK_DEPLOYMENT.get(port)
            if fallback == payload["model"]:
                fallback = None
            try:
                try:
                    upstream = urllib.request.urlopen(
                        request_for(payload), timeout=FALLBACK_AFTER_SECONDS if fallback else 600)
                except (TimeoutError, socket.timeout) if fallback else () as slow:
                    sys.stderr.write(f"[{port}]    {payload['model']} silent for {FALLBACK_AFTER_SECONDS}s "
                                     f"({slow!r}); retrying on {fallback}\n")
                    payload = prepare_for(fallback, payload)
                    upstream = urllib.request.urlopen(request_for(payload), timeout=600)
                sys.stderr.write(f"[{port}]    Foundry answered {upstream.status}\n")
                try:  # the short fallback timeout was only for the first byte; don't cut a slow stream
                    upstream.fp.raw._sock.settimeout(600)
                except AttributeError:
                    pass
            except urllib.error.HTTPError as e:
                body = e.read()
                sys.stderr.write(
                    f"[{port}] Foundry {e.code} for fields {sorted(payload)} "
                    f"stream={payload.get('stream')}: {body[:800]!r}\n")
                return self._json(e.code, canonical_error(e.code, body))
            except (urllib.error.URLError, TimeoutError) as e:
                return self._json(502, canonical_error(502, f"Foundry unreachable: {e}".encode()))

            with upstream:
                if "text/event-stream" not in upstream.headers.get("Content-Type", ""):
                    raw_body = upstream.read()
                    try:
                        parsed = json.loads(raw_body)
                        log_usage(port, payload["model"], False, parsed.get("usage"))
                        return self._json(upstream.status, canonical_completion(parsed, chunk=False))
                    except ValueError:
                        return self._json(502, canonical_error(502, raw_body[:500]))

                self.send_response(upstream.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    line = upstream.readline()
                    if not line:
                        break
                    text = line.strip()
                    if text.startswith(b"data:") and text[5:].strip() != b"[DONE]":
                        try:
                            parsed = json.loads(text[5:])
                            if parsed.get("usage"):
                                log_usage(port, payload["model"], True, parsed["usage"])
                                if not parsed.get("choices") and not caller_wants_usage:
                                    continue
                            event = canonical_completion(parsed, chunk=True)
                            line = b"data: " + json.dumps(event).encode() + b"\n"
                        except ValueError:
                            pass
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")

    return Handler


def main():
    if not ENDPOINT or not API_KEY:
        sys.exit("Set FOUNDRY_ENDPOINT and FOUNDRY_API_KEY (both are in the lab instructions panel).")
    servers = [ThreadingHTTPServer(("127.0.0.1", p), make_handler(p)) for p in ROUTES]
    for p, (dep, name) in ROUTES.items():
        tools_dep = TOOLS_DEPLOYMENT.get(p) or dep
        extra = f", requests with tools -> {tools_dep}" if tools_dep != dep else ""
        print(f"127.0.0.1:{p} -> {dep} (reported as {name}){extra}", flush=True)
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()

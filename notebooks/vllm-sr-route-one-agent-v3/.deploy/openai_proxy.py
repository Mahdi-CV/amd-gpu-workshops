#!/usr/bin/env python3
"""
OpenAI-compatible proxy for the workshop model backends.

Each frontend port presents a local OpenAI-compatible endpoint to the
router.  The backend can be either a local llama-server or a remote
cloud API (e.g. AMD Radeon Cloud).

Port mapping (defaults):
    8001 -> local 18001  OR  remote REASONING_BACKEND_URL  (reasoning)
    8002 -> local 18002  OR  remote ROUTINE_BACKEND_URL    (routine)

Remote mode is activated per-model by setting the *_BACKEND_URL env var
to a full URL (e.g. https://developer.amd.com.cn/radeon/api/v1).
An API key is read from RADEON_API_KEY (or the model-specific override).
"""

import json
import os
import ssl
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen

CANONICAL_TOP = {"id", "object", "created", "model", "choices", "usage", "system_fingerprint"}
CANONICAL_USAGE = {"prompt_tokens", "completion_tokens", "total_tokens"}

REASONING_FRONTEND = int(os.environ.get("OPENAI_PROXY_REASONING_PORT", "8001"))
REASONING_BACKEND = int(os.environ.get("OPENAI_PROXY_REASONING_BACKEND", "18001"))
ROUTINE_FRONTEND = int(os.environ.get("OPENAI_PROXY_ROUTINE_PORT", "8002"))
ROUTINE_BACKEND = int(os.environ.get("OPENAI_PROXY_ROUTINE_BACKEND", "18002"))

# Remote backend URLs (empty = use local llama-server)
REASONING_BACKEND_URL = os.environ.get("REASONING_BACKEND_URL", "")
ROUTINE_BACKEND_URL = os.environ.get("ROUTINE_BACKEND_URL", "")

# API keys for remote backends
REASONING_API_KEY = os.environ.get("REASONING_API_KEY", os.environ.get("RADEON_API_KEY", ""))
ROUTINE_API_KEY = os.environ.get("ROUTINE_API_KEY", os.environ.get("RADEON_API_KEY", ""))

# Model name remapping: local_name -> remote_name
# The router uses lowercase names (e.g. qwen3.8-27b) but cloud APIs may
# expect different casing (e.g. Qwen3.8-27B).  Set via env vars:
#   REASONING_REMOTE_MODEL=Qwen3.8-27B   (what the cloud API expects)
#   REASONING_LOCAL_MODEL=qwen3.8-27b     (what the router sends)
REASONING_REMOTE_MODEL = os.environ.get("REASONING_REMOTE_MODEL", "")
REASONING_LOCAL_MODEL = os.environ.get("REASONING_LOCAL_MODEL", os.environ.get("REASONING_PROVIDER_MODEL", ""))
ROUTINE_REMOTE_MODEL = os.environ.get("ROUTINE_REMOTE_MODEL", "")
ROUTINE_LOCAL_MODEL = os.environ.get("ROUTINE_LOCAL_MODEL", os.environ.get("ROUTINE_PROVIDER_MODEL", ""))

# Permissive SSL context for proxied HTTPS connections
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _clean_response(data):
    """Strip non-canonical fields from an OpenAI response dict."""
    data = {k: v for k, v in data.items() if k in CANONICAL_TOP}
    if "usage" in data:
        data["usage"] = {k: v for k, v in data["usage"].items() if k in CANONICAL_USAGE}
    return data


class Proxy(BaseHTTPRequestHandler):
    backend = None       # local port (int)
    backend_url = ""     # remote URL (str), empty = local mode
    api_key = ""         # Bearer token for remote mode
    local_model = ""     # model name the router uses
    remote_model = ""    # model name the cloud API expects

    def _build_url(self):
        if self.backend_url:
            base = self.backend_url.rstrip("/")
            path = self.path
            # Avoid doubling /v1 when the base URL already ends with it
            if base.endswith("/v1") and path.startswith("/v1/"):
                path = path[3:]  # strip leading "/v1"
            return f"{base}{path}"
        return f"http://127.0.0.1:{self.backend}{self.path}"

    def _build_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.backend_url and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _remap_request_model(self, body):
        """Rewrite model name in request body for remote backends."""
        if not (self.backend_url and self.local_model and self.remote_model):
            return body
        try:
            data = json.loads(body)
            if data.get("model") == self.local_model:
                data["model"] = self.remote_model
                return json.dumps(data).encode()
        except (json.JSONDecodeError, ValueError):
            pass
        return body

    def _remap_response_model(self, data):
        """Rewrite model name in response dict back to local name."""
        if self.backend_url and self.local_model and self.remote_model:
            m = data.get("model", "")
            # Match exact name or provider-prefixed name (e.g. "self-dploy/Qwen3.8-27B")
            if m == self.remote_model or m.endswith("/" + self.remote_model):
                data["model"] = self.local_model
        return data

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        is_stream = False
        try:
            is_stream = json.loads(body).get("stream", False) if body else False
        except (json.JSONDecodeError, ValueError):
            pass

        body = self._remap_request_model(body)

        url = self._build_url()
        req = Request(url, data=body, method="POST", headers=self._build_headers())
        ctx = _ssl_ctx if url.startswith("https") else None
        try:
            resp = urlopen(req, timeout=600, context=ctx)

            if is_stream:
                ct = resp.headers.get("Content-Type", "text/event-stream")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    if text.startswith("data: ") and not text.startswith("data: [DONE]"):
                        try:
                            chunk = json.loads(text[6:])
                            chunk = _clean_response(chunk)
                            chunk = self._remap_response_model(chunk)
                            self.wfile.write(f"data: {json.dumps(chunk)}\n".encode())
                        except (json.JSONDecodeError, ValueError):
                            self.wfile.write(line)
                    else:
                        self.wfile.write(line)
                    self.wfile.flush()
            else:
                data = json.loads(resp.read())
                data = _clean_response(data)
                data = self._remap_response_model(data)
                out = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)

    def do_GET(self):
        # For /v1/models on a remote backend, return a synthetic response
        # with the local model name so the router sees what it expects.
        if self.backend_url and self.local_model and self.path.rstrip("/") == "/v1/models":
            data = {
                "object": "list",
                "data": [{"id": self.local_model, "object": "model", "owned_by": "remote"}],
            }
            out = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return

        url = self._build_url()
        req = Request(url, headers=self._build_headers())
        ctx = _ssl_ctx if url.startswith("https") else None
        try:
            resp = urlopen(req, timeout=10, context=ctx)
            out = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
            self.end_headers()
            self.wfile.write(out)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, fmt, *args):
        pass


def serve(port, backend, backend_url="", api_key="", local_model="", remote_model=""):
    handler = type("H", (Proxy,), {
        "backend": backend,
        "backend_url": backend_url,
        "api_key": api_key,
        "local_model": local_model,
        "remote_model": remote_model,
    })
    HTTPServer(("127.0.0.1", port), handler).serve_forever()


def main():
    r_label = REASONING_BACKEND_URL or f"127.0.0.1:{REASONING_BACKEND}"
    threading.Thread(
        target=serve,
        args=(REASONING_FRONTEND, REASONING_BACKEND, REASONING_BACKEND_URL, REASONING_API_KEY),
        kwargs={"local_model": REASONING_LOCAL_MODEL, "remote_model": REASONING_REMOTE_MODEL},
        daemon=True,
    ).start()
    if REASONING_BACKEND_URL and REASONING_REMOTE_MODEL:
        print(f"Proxy :{REASONING_FRONTEND} -> {r_label} (reasoning) "
              f"model remap: {REASONING_LOCAL_MODEL} <-> {REASONING_REMOTE_MODEL}")
    else:
        print(f"Proxy :{REASONING_FRONTEND} -> {r_label} (reasoning) started")

    s_label = ROUTINE_BACKEND_URL or f"127.0.0.1:{ROUTINE_BACKEND}"
    if ROUTINE_BACKEND_URL and ROUTINE_REMOTE_MODEL:
        print(f"Proxy :{ROUTINE_FRONTEND} -> {s_label} (routine) "
              f"model remap: {ROUTINE_LOCAL_MODEL} <-> {ROUTINE_REMOTE_MODEL}")
    else:
        print(f"Proxy :{ROUTINE_FRONTEND} -> {s_label} (routine) starting...")
    serve(ROUTINE_FRONTEND, ROUTINE_BACKEND, ROUTINE_BACKEND_URL, ROUTINE_API_KEY,
          local_model=ROUTINE_LOCAL_MODEL, remote_model=ROUTINE_REMOTE_MODEL)


if __name__ == "__main__":
    main()

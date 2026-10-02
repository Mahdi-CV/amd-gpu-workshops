#!/usr/bin/env python3
"""
OpenAI-compatible proxy for llama-server.

llama-server (llama.cpp) returns extra fields in its OpenAI-compatible
responses that the vLLM-SR router does not expect. This proxy strips
non-canonical fields so the router can process the responses cleanly.

Port mapping:
    8001 -> 18001  (reasoning model, e.g. qwen3)
    8002 -> 18002  (routine model, e.g. gemma4)
"""

import json
import os
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


class Proxy(BaseHTTPRequestHandler):
    backend = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # Detect streaming requests so we can handle SSE responses
        is_stream = False
        try:
            is_stream = json.loads(body).get("stream", False) if body else False
        except (json.JSONDecodeError, ValueError):
            pass

        req = Request(
            f"http://127.0.0.1:{self.backend}{self.path}",
            data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urlopen(req, timeout=120)

            if is_stream:
                # Forward SSE stream, cleaning each JSON chunk
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
                            chunk = {k: v for k, v in chunk.items() if k in CANONICAL_TOP}
                            if "usage" in chunk:
                                chunk["usage"] = {k: v for k, v in chunk["usage"].items() if k in CANONICAL_USAGE}
                            self.wfile.write(f"data: {json.dumps(chunk)}\n".encode())
                        except (json.JSONDecodeError, ValueError):
                            self.wfile.write(line)
                    else:
                        self.wfile.write(line)
                    self.wfile.flush()
            else:
                data = json.loads(resp.read())
                data = {k: v for k, v in data.items() if k in CANONICAL_TOP}
                if "usage" in data:
                    data["usage"] = {k: v for k, v in data["usage"].items() if k in CANONICAL_USAGE}
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
        req = Request(f"http://127.0.0.1:{self.backend}{self.path}")
        try:
            resp = urlopen(req, timeout=10)
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


def serve(port, backend):
    handler = type("H", (Proxy,), {"backend": backend})
    HTTPServer(("127.0.0.1", port), handler).serve_forever()


def main():
    threading.Thread(target=serve, args=(REASONING_FRONTEND, REASONING_BACKEND), daemon=True).start()
    print(f"Proxy {REASONING_FRONTEND}->{REASONING_BACKEND} (reasoning) started")
    print(f"Proxy {ROUTINE_FRONTEND}->{ROUTINE_BACKEND} (routine) starting...")
    serve(ROUTINE_FRONTEND, ROUTINE_BACKEND)


if __name__ == "__main__":
    main()

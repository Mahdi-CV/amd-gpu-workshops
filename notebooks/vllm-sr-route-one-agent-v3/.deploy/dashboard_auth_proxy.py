#!/usr/bin/env python3
"""
Auth-injecting reverse proxy for the vLLM-SR dashboard behind jupyter-server-proxy.

Problem: jupyter-server-proxy (via JupyterHub) replaces the browser's Authorization
header with Jupyter's own token, so the dashboard backend always sees an invalid
token and returns 401.

Solution: This proxy sits between jupyter-server-proxy and the dashboard backend.
It acquires a dashboard JWT on startup and injects it into every forwarded request.

  Browser -> jupyter-server-proxy(:9001) -> this proxy(:9001) -> dashboard(:9000)

Usage:
    python3 dashboard_auth_proxy.py &

Then access the dashboard via /proxy/9001/ instead of /proxy/9000/.
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request

BACKEND = os.environ.get("DASHBOARD_AUTH_PROXY_BACKEND", "http://127.0.0.1:9000")
LISTEN_PORT = int(os.environ.get("DASHBOARD_AUTH_PROXY_PORT", "9001"))
LOGIN_EMAIL = os.environ.get("DASHBOARD_ADMIN_EMAIL", "admin@workshop.local")
LOGIN_PASSWORD = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "workshop2026")

# Mutable token state
_token_lock = threading.Lock()
_token = {"value": None, "expires": 0}

HOP_BY_HOP = frozenset([
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
])


def _acquire_token() -> str:
    """POST to /api/auth/login and return a fresh JWT."""
    payload = json.dumps({"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
    token = body.get("token") or body.get("access_token") or body.get("jwt")
    if not token:
        raise RuntimeError(f"Login response has no token field: {list(body.keys())}")
    # Decode expiry from JWT payload (base64 middle segment)
    import base64
    parts = token.split(".")
    if len(parts) == 3:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        exp = claims.get("exp", 0)
    else:
        exp = time.time() + 3600  # fallback: 1 hour
    return token, exp


def get_token() -> str:
    """Return a valid token, refreshing if expired or close to expiry."""
    with _token_lock:
        # Refresh if within 5 minutes of expiry
        if _token["value"] and time.time() < _token["expires"] - 300:
            return _token["value"]
        try:
            tok, exp = _acquire_token()
            _token["value"] = tok
            _token["expires"] = exp
            print(f"[auth-proxy] Token acquired, expires in {int(exp - time.time())}s")
            return tok
        except Exception as exc:
            if _token["value"]:
                print(f"[auth-proxy] Token refresh failed ({exc}), using existing token")
                return _token["value"]
            raise


class AuthProxyHandler(http.server.BaseHTTPRequestHandler):
    """Reverse proxy that injects Authorization header."""

    def _proxy(self):
        url = f"{BACKEND}{self.path}"

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        # Build headers: copy all, replace Authorization
        headers = {}
        for key in self.headers:
            if key.lower() not in ("host", "authorization") and key.lower() not in HOP_BY_HOP:
                headers[key] = self.headers[key]
        headers["Authorization"] = f"Bearer {get_token()}"
        headers["Host"] = "127.0.0.1:9000"

        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in HOP_BY_HOP and key.lower() != "content-length":
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            self.send_response(e.code)
            for key, value in e.headers.items():
                if key.lower() not in HOP_BY_HOP and key.lower() != "content-length":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as exc:
            msg = f"Proxy error: {exc}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_PATCH = _proxy
    do_OPTIONS = _proxy
    do_HEAD = _proxy

    def log_message(self, format, *args):
        # Only log errors, not every request
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write(f"[auth-proxy] {self.address_string()} {format % args}\n")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    # Verify backend is reachable
    try:
        urllib.request.urlopen(f"{BACKEND}/api/setup/state", timeout=5)
    except Exception as exc:
        print(f"[auth-proxy] WARNING: Backend {BACKEND} not reachable: {exc}", file=sys.stderr)

    # Acquire initial token
    get_token()

    server = ThreadedHTTPServer(("127.0.0.1", LISTEN_PORT), AuthProxyHandler)
    print(f"[auth-proxy] Listening on 127.0.0.1:{LISTEN_PORT} -> {BACKEND}")
    print(f"[auth-proxy] Access dashboard via /proxy/{LISTEN_PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[auth-proxy] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()

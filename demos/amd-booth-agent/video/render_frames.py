#!/usr/bin/env python3
"""Capture deterministic teaser frames from Chrome via the DevTools Protocol."""

from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect


CHROME_CANDIDATES = (
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--quality", type=int, default=94)
    parser.add_argument("--chrome")
    return parser.parse_args()


def find_chrome(explicit: str | None) -> str:
    if explicit:
        path = shutil.which(explicit) or explicit
        if Path(path).is_file():
            return str(path)
        raise SystemExit(f"Chrome executable not found: {explicit}")
    for candidate in CHROME_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    raise SystemExit(
        "No Chrome/Chromium executable found. Set --chrome or install one of: "
        + ", ".join(CHROME_CANDIDATES)
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def page_websocket(port: int, deadline: float) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                targets = json.load(response)
            for target in targets:
                if target.get("type") == "page":
                    return str(target["webSocketDebuggerUrl"])
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(0.1)
    raise RuntimeError(f"Chrome DevTools endpoint did not become ready: {last_error}")


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.websocket = connect(
            websocket_url,
            max_size=None,
            open_timeout=10,
            close_timeout=2,
            proxy=None,
        )
        self.message_id = 0

    def close(self) -> None:
        self.websocket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.message_id += 1
        message_id = self.message_id
        self.websocket.send(
            json.dumps(
                {
                    "id": message_id,
                    "method": method,
                    "params": params or {},
                },
                separators=(",", ":"),
            )
        )
        while True:
            try:
                raw_message = self.websocket.recv(timeout=20)
            except TimeoutError as error:
                raise RuntimeError(f"Timed out waiting for {method}") from error
            message = json.loads(raw_message)
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method} failed: {message['error']}")
            return dict(message.get("result") or {})


def wait_for_teaser(cdp: CDP, deadline: float) -> None:
    expression = (
        "document.readyState === 'complete' && "
        "window.__TEASER_READY === true && "
        "[...document.images].every((image) => image.complete)"
    )
    while time.monotonic() < deadline:
        result = cdp.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        if result.get("result", {}).get("value") is True:
            cdp.call(
                "Runtime.evaluate",
                {
                    "expression": (
                        "Promise.all([...document.images].map((image) => "
                        "image.decode ? image.decode().catch(() => {}) : null))"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            return
        time.sleep(0.05)
    raise RuntimeError("Teaser page did not report ready state")


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_source_server(html: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    serve_root = html.parent.parent
    relative_html = html.relative_to(serve_root).as_posix()
    handler = functools.partial(QuietHandler, directory=str(serve_root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    return server, f"http://127.0.0.1:{port}/{relative_html}?capture=1"


def main() -> int:
    args = parse_args()
    html = args.html.resolve()
    output_dir = args.output_dir.resolve()
    if not html.is_file():
        raise SystemExit(f"HTML source does not exist: {html}")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        raise SystemExit("Width, height, and fps must be positive")
    if args.duration <= 0:
        raise SystemExit("Duration must be positive")
    if not 0 <= args.quality <= 100:
        raise SystemExit("JPEG quality must be between 0 and 100")

    output_dir.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome(args.chrome)
    port = free_port()
    profile = output_dir.parent / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)

    command = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-domain-reliability",
        "--disable-extensions",
        "--disable-features=Translate,MediaRouter",
        "--disable-renderer-backgrounding",
        "--force-color-profile=srgb",
        "--hide-scrollbars",
        "--mute-audio",
        "--no-first-run",
        "--run-all-compositor-stages-before-draw",
        "--allow-file-access-from-files",
        "--remote-allow-origins=*",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        f"--window-size={args.width},{args.height}",
        "about:blank",
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Launching {Path(chrome).name} on local DevTools port {port}...", flush=True)
    cdp: CDP | None = None
    source_server, capture_url = start_source_server(html)
    try:
        websocket_url = page_websocket(port, time.monotonic() + 15)
        print("Connecting to Chrome DevTools...", flush=True)
        cdp = CDP(websocket_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.width,
                "height": args.height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "screenWidth": args.width,
                "screenHeight": args.height,
            },
        )
        print("Loading teaser source and AMD assets...", flush=True)
        cdp.call("Page.navigate", {"url": capture_url})
        wait_for_teaser(cdp, time.monotonic() + 15)
        print("Teaser ready; capturing deterministic frames.", flush=True)

        frame_count = round(args.duration * args.fps)
        started = time.monotonic()
        for frame in range(frame_count):
            teaser_time = frame / args.fps
            cdp.call(
                "Runtime.evaluate",
                {
                    "expression": f"window.setTeaserTime({teaser_time:.9f})",
                    "returnByValue": True,
                },
            )
            screenshot = cdp.call(
                "Page.captureScreenshot",
                {
                    "format": "jpeg",
                    "quality": args.quality,
                    "fromSurface": True,
                    "captureBeyondViewport": False,
                },
            )
            payload = screenshot.get("data")
            if not payload:
                raise RuntimeError(f"Chrome returned no image data for frame {frame}")
            target = output_dir / f"frame_{frame:06d}.jpg"
            target.write_bytes(base64.b64decode(payload))

            completed = frame + 1
            if completed == 1 or completed % (args.fps * 5) == 0:
                elapsed = max(time.monotonic() - started, 0.001)
                rate = completed / elapsed
                print(
                    f"  {completed:4d}/{frame_count} frames "
                    f"({completed / args.fps:5.1f}s teaser, {rate:4.1f} fps capture)",
                    flush=True,
                )
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        terminate(process)
        source_server.shutdown()
        source_server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

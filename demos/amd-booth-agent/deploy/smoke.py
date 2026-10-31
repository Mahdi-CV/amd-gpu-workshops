#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request


origin = os.getenv(
    "BOOTH_ORIGIN",
    "https://agent.165.245.129.230.sslip.io",
).rstrip("/")
context = ssl.create_default_context()


def get(path: str):
    with urllib.request.urlopen(origin + path, context=context, timeout=30) as r:
        return r.status, json.load(r)


status, health = get("/healthz")
assert status == 200 and health["status"] == "ok", health
status, config = get("/api/config")
assert status == 200
assert len(config["suggested_tasks"]) >= 4
assert set(config["models"]) == {
    "qwen/qwen3.8-27b",
    "zai/glm-5.3-flash",
    "moonshot/kimi-k3",
}
status, system = get("/api/system")
assert status == 200 and system["router"] == "ready", system
print(json.dumps({"health": health, "system": system}, indent=2))

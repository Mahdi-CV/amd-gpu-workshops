#!/usr/bin/env python3
"""Run three matched OpenClaw auto-vs-direct-GLM workflow pairs.

The harness is intentionally self-contained and secret-safe:

* endpoints and credential-file paths come only from environment variables;
* credentials are used for preflight and proxy forwarding but never persisted;
* every arm receives fresh OpenClaw state, workspaces, and fixture files;
* reviewer text is handed verbatim to the Fixer;
* the independent pytest result is handed verbatim to Main; and
* summary.json is the sole source used to render comparison.csv and report.md.
"""

from __future__ import annotations

import argparse
import ast
import csv
import difflib
import hashlib
import http.server
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEPLOY = Path(__file__).resolve().parents[1]
FIXTURE = DEPLOY / "fixture" / "open_type_faster"
COST_FACTORS = DEPLOY / "config" / "cost-factors.json"
SCHEMA = DEPLOY / "artifacts" / "comparison-schema.json"
SCHEMA_VERSION = "openclaw-policy-comparison/v1"
PAIR_COUNT = 3
ARMS = ("auto", "direct_glm")
PHASES = ("bug_reviewer", "test_reviewer", "fixer", "main")
GLM_CANONICAL = "zai/glm-5.3-flash"

BUG_PROMPT = (
    "Carefully review the Python accuracy implementation against the three "
    "failing examples. Give the root cause and smallest correct source fix "
    "in two bullets."
)
TEST_PROMPT = (
    "Design a compact regression matrix for zero input, perfect accuracy, "
    "partial accuracy, rounding, and SessionResult propagation. Explain what "
    "each case catches in five bullets."
)
OLD_ACCURACY_LINE = (
    "    return round((correct // (total_typed + 1)) * 100, 1)"
)
NEW_ACCURACY_LINE = "    return round((correct / total_typed) * 100, 1)"
EQUIVALENT_ACCURACY_LINE = (
    "    return round(correct / total_typed * 100, 1)"
)
ACCEPTED_ACCURACY_LINES = (
    NEW_ACCURACY_LINE,
    EQUIVALENT_ACCURACY_LINE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_cost_factors(path: Path = COST_FACTORS) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    recipe = body.get("recipe") or {}
    if recipe.get("id") != "decision-balance":
        raise ValueError("Cost factors are not for decision-balance.")
    if recipe.get("version") != "0.3.2":
        raise ValueError("Cost factors are not recipe version 0.3.2.")
    return body


def normalized_model(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def canonical_model_id(
    value: str,
    factors: dict[str, Any],
) -> str | None:
    normalized = normalized_model(value)
    matches: list[str] = []
    for model_id, details in (factors.get("models") or {}).items():
        names = [model_id, *(details.get("aliases") or [])]
        normalized_names = [normalized_model(str(item)) for item in names]
        if any(
            normalized == name
            or name in normalized
            or normalized in name
            for name in normalized_names
        ):
            matches.append(model_id)
    return matches[0] if len(matches) == 1 else None


def usage_cost_xxx(
    usage: dict[str, Any],
    model_id: str,
    factors: dict[str, Any],
) -> float:
    rates = (factors.get("models") or {}).get(model_id)
    if not rates:
        raise ValueError(f"No Decision Balance 0.3.2 rate for {model_id!r}.")
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    cost = (
        prompt * float(rates["prompt_per_1m"])
        + completion * float(rates["completion_per_1m"])
    ) / 1_000_000
    return round(cost, 8)


def normalize_base_url(value: str) -> str:
    raw = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Endpoint must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Endpoint URLs must not contain credentials, query strings, or fragments."
        )
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")
    )


def env_choice(*names: str, default: str = "") -> tuple[str, str]:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value, name
    return default, ""


def read_credential_file(path_value: str, env_name: str) -> tuple[Path, str]:
    if not path_value:
        raise RuntimeError(f"Set {env_name} to a credential file.")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{env_name} does not name a readable file.")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{env_name} names an empty credential file.")
    return path, value


def endpoint_from_env(arm: str) -> dict[str, Any]:
    if arm == "auto":
        base_value, base_env = env_choice(
            "AUTO_BASE_URL",
            "AUTO_OPENAI_BASE_URL",
        )
        key_value, key_env = env_choice(
            "AUTO_API_KEY_FILE",
            "AUTO_OPENAI_API_KEY_FILE",
        )
        model, model_env = env_choice(
            "AUTO_MODEL",
            "AUTO_OPENAI_MODEL",
            default="vllm-sr/auto",
        )
        expected_key_env = "AUTO_API_KEY_FILE"
    else:
        base_value, base_env = env_choice(
            "DIRECT_GLM_BASE_URL",
            "DIRECT_GLM_OPENAI_BASE_URL",
            "GLM_BASE_URL",
        )
        key_value, key_env = env_choice(
            "DIRECT_GLM_API_KEY_FILE",
            "DIRECT_GLM_OPENAI_API_KEY_FILE",
            "GLM_API_KEY_FILE",
        )
        model, model_env = env_choice(
            "DIRECT_GLM_MODEL",
            "GLM_MODEL",
        )
        expected_key_env = "DIRECT_GLM_API_KEY_FILE"
    if not base_value:
        raise RuntimeError(
            f"Set {'AUTO_BASE_URL' if arm == 'auto' else 'DIRECT_GLM_BASE_URL'}."
        )
    key_path, key = read_credential_file(key_value, expected_key_env)
    return {
        "arm": arm,
        "base_url": normalize_base_url(base_value),
        "base_url_env": base_env,
        "credential_file": key_path,
        "credential_env": key_env,
        "api_key": key,
        "model": model,
        "model_env": model_env,
    }


def get_models(
    base_url: str,
    api_key: str,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "openclaw-policy-comparison-preflight",
        },
        method="GET",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GET /models failed with HTTP {exc.code}."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("GET /models could not reach the endpoint.") from exc
    elapsed = time.perf_counter() - started
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("GET /models did not return JSON.") from exc
    model_ids = [
        str(item.get("id"))
        for item in body.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    if status != 200 or not model_ids:
        raise RuntimeError("GET /models returned no model IDs.")
    return {
        "status": status,
        "latency_seconds": round(elapsed, 4),
        "models": model_ids,
    }


def discover_glm_model(
    model_ids: list[str],
    override: str = "",
) -> str:
    if override:
        if override not in model_ids:
            raise RuntimeError(
                "DIRECT_GLM_MODEL is not present in the direct endpoint's /models response."
            )
        return override

    def score(model_id: str) -> tuple[int, int]:
        value = normalized_model(model_id)
        if value == "zai-glm-5-3-flash":
            return (4, -len(model_id))
        if "glm-5-3-flash" in value:
            return (3, -len(model_id))
        if "glm" in value and "flash" in value:
            return (2, -len(model_id))
        if "glm" in value:
            return (1, -len(model_id))
        return (0, -len(model_id))

    candidates = [(score(model_id), model_id) for model_id in model_ids]
    candidates = [item for item in candidates if item[0][0] > 0]
    if not candidates:
        raise RuntimeError(
            "No GLM model was discoverable; set DIRECT_GLM_MODEL."
        )
    best_score = max(item[0] for item in candidates)
    winners = [model_id for value, model_id in candidates if value == best_score]
    if len(winners) != 1:
        raise RuntimeError(
            "GLM discovery was ambiguous; set DIRECT_GLM_MODEL."
        )
    return winners[0]


def build_execution_plan(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    pair_ids = list(range(1, PAIR_COUNT + 1))
    rng.shuffle(pair_ids)
    plan: list[dict[str, Any]] = []
    position = 0
    for pair_execution_index, pair_id in enumerate(pair_ids, start=1):
        arm_order = list(ARMS)
        rng.shuffle(arm_order)
        for arm_position, arm in enumerate(arm_order, start=1):
            position += 1
            plan.append(
                {
                    "position": position,
                    "pair_id": pair_id,
                    "pair_execution_index": pair_execution_index,
                    "arm_position": arm_position,
                    "arm": arm,
                }
            )
    return plan


def parse_response_payload(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" not in content_type:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return body if isinstance(body, dict) else {}
    body: dict[str, Any] = {"choices": [], "usage": {}}
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
            body["model"] = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            body["usage"] = chunk["usage"]
        choices = chunk.get("choices") or []
        if choices and choices[0].get("finish_reason"):
            finish_reason = choices[0]["finish_reason"]
    if finish_reason:
        body["choices"] = [{"finish_reason": finish_reason}]
    return body


def normalized_usage(body: dict[str, Any]) -> dict[str, int]:
    usage = body.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "cached_tokens": int(prompt_details.get("cached_tokens") or 0),
        "reasoning_tokens": int(
            completion_details.get("reasoning_tokens")
            or usage.get("reasoning_tokens")
            or 0
        ),
    }


class ProxyState:
    def __init__(
        self,
        *,
        upstream: str,
        api_key: str,
        log_path: Path,
        pair_id: int,
        arm: str,
    ) -> None:
        self.upstream = upstream.rstrip("/")
        self.api_key = api_key
        self.log_path = log_path
        self.pair_id = pair_id
        self.arm = arm
        self.phase = "setup"
        self.request_id = 0
        self.records: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def set_phase(self, phase: str) -> None:
        with self.lock:
            self.phase = phase

    def allocate(self) -> tuple[int, str]:
        with self.lock:
            self.request_id += 1
            return self.request_id, self.phase

    def log(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.records.append(row)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    server_version = "OpenClawPolicyComparison/1.0"

    @property
    def state(self) -> ProxyState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def do_GET(self) -> None:
        self.forward(None)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.forward(self.rfile.read(length) if length else b"")

    def forward(self, raw: bytes | None) -> None:
        request_id, phase = self.state.allocate()
        request_body: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    request_body = parsed
            except json.JSONDecodeError:
                pass
        path = self.path
        if self.state.upstream.endswith("/v1") and path.startswith("/v1/"):
            path = path[3:]
        upstream_url = self.state.upstream + path
        headers = {
            "Authorization": f"Bearer {self.state.api_key}",
            "Accept": self.headers.get("Accept", "application/json"),
            "User-Agent": "openclaw-policy-comparison-proxy",
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
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                response_raw = response.read()
                status = response.status
                response_headers = dict(response.headers)
        except urllib.error.HTTPError as exc:
            response_raw = exc.read()
            status = exc.code
            response_headers = dict(exc.headers)
        except urllib.error.URLError:
            response_raw = b'{"error":"upstream unavailable"}'
            status = 502
            response_headers = {"Content-Type": "application/json"}
        elapsed = time.perf_counter() - started
        content_type = next(
            (
                value
                for key, value in response_headers.items()
                if key.lower() == "content-type"
            ),
            "",
        )
        response_body = parse_response_payload(response_raw, content_type)
        choices = response_body.get("choices") or []
        routing_headers = {
            key.lower(): value
            for key, value in response_headers.items()
            if key.lower().startswith("x-vsr-")
        }
        self.state.log(
            {
                "timestamp": utc_now(),
                "pair_id": self.state.pair_id,
                "arm": self.state.arm,
                "phase": phase,
                "request_id": request_id,
                "method": self.command,
                "path": self.path,
                "status": status,
                "latency_seconds": round(elapsed, 4),
                "requested_model": request_body.get("model"),
                "response_model": response_body.get("model"),
                "finish_reason": (
                    choices[0].get("finish_reason") if choices else None
                ),
                "tool_count": len(request_body.get("tools") or []),
                "stream": request_body.get("stream"),
                "usage": normalized_usage(response_body),
                "routing_headers": routing_headers,
            }
        )
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


class TaggedProxy:
    def __init__(
        self,
        endpoint: dict[str, Any],
        log_path: Path,
        pair_id: int,
        arm: str,
    ) -> None:
        self.state = ProxyState(
            upstream=endpoint["base_url"],
            api_key=endpoint["api_key"],
            log_path=log_path,
            pair_id=pair_id,
            arm=arm,
        )
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            ProxyHandler,
        )
        self.server.state = self.state  # type: ignore[attr-defined]
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}/v1"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def run_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def openclaw_env(state_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["OPENCLAW_STATE_DIR"] = str(state_dir)
    for name in (
        "OPENAI_API_KEY",
        "ADAPTIVE_AI_API_KEY",
        "AUTO_API_KEY",
        "DIRECT_GLM_API_KEY",
        "GLM_API_KEY",
    ):
        env.pop(name, None)
    return env


def run_openclaw(
    openclaw: str,
    state_dir: Path,
    *args: str,
    timeout: int = 240,
) -> subprocess.CompletedProcess[str]:
    return run_process(
        [openclaw, *args],
        env=openclaw_env(state_dir),
        timeout=timeout,
    )


def require_success(
    result: subprocess.CompletedProcess[str],
    label: str,
) -> None:
    if result.returncode:
        detail = (result.stderr or result.stdout)[-2000:]
        raise RuntimeError(f"{label} failed ({result.returncode}): {detail}")


def role_files(
    fixture_repo: Path,
    accuracy_source: str,
    accuracy_tests: str,
) -> dict[str, str]:
    return {
        "main": """# Team Reporter

Report only the independent pytest result supplied in the user message.
Keep the answer to one sentence. No additional tool use is needed.
""",
        "bug_reviewer": f"""# Bug Reviewer

Review only the supplied implementation and failures. All evidence is below.
Identify the root cause and smallest source-only fix.

```python
{accuracy_source}
```

Observed failures:
- perfect: expected 100.0, got 0
- half correct: expected 50.0, got 0
- two of three: expected 66.7, got 0
""",
        "test_reviewer": f"""# Test Reviewer

Define the behavioral contract and regression tests for this calculation.
All evidence is below.

Implementation:
```python
{accuracy_source}
```

Existing contract:
```python
{accuracy_tests}
```
""",
        "fixer": f"""# Fixer

Work only in:

{fixture_repo}

Use filesystem and execution tools. Preserve every test file. Make the
smallest source-only correction, run the complete pytest suite, and report
the result.
""",
    }


def extract_fixture_evidence(repo: Path) -> tuple[str, str]:
    stats = (repo / "stats.py").read_text(encoding="utf-8")
    start = stats.index("def _accuracy")
    end = stats.index("\ndef _count_correct", start)
    tests = (repo / "tests" / "test_stats.py").read_text(encoding="utf-8")
    test_start = tests.index("class TestAccuracy")
    test_end = tests.index("# ── _count_correct", test_start)
    return stats[start:end].strip(), tests[test_start:test_end].strip()


def configure_openclaw(
    *,
    openclaw: str,
    state_dir: Path,
    workspaces: Path,
    proxy_url: str,
    model_id: str,
    fixture_repo: Path,
) -> str:
    state_dir.mkdir(parents=True, exist_ok=True)
    workspaces.mkdir(parents=True, exist_ok=True)
    provider = "comparison"
    model_ref = f"{provider}/{model_id}"
    onboard = run_openclaw(
        openclaw,
        state_dir,
        "onboard",
        "--non-interactive",
        "--mode",
        "local",
        "--workspace",
        str(workspaces / "main"),
        "--auth-choice",
        "custom-api-key",
        "--custom-base-url",
        proxy_url,
        "--custom-model-id",
        model_id,
        "--custom-provider-id",
        provider,
        "--custom-compatibility",
        "openai",
        "--custom-api-key",
        "proxy-local",
        "--secret-input-mode",
        "plaintext",
        "--skip-bootstrap",
        "--skip-channels",
        "--skip-search",
        "--skip-hooks",
        "--skip-ui",
        "--skip-health",
        "--accept-risk",
        timeout=300,
    )
    require_success(onboard, "OpenClaw onboarding")
    for agent in ("bug_reviewer", "test_reviewer", "fixer"):
        added = run_openclaw(
            openclaw,
            state_dir,
            "agents",
            "add",
            agent,
            "--non-interactive",
            "--workspace",
            str(workspaces / agent),
            "--model",
            model_ref,
        )
        require_success(added, f"adding {agent}")

    config_path = state_dir / "openclaw.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.setdefault("memory", {}).setdefault("search", {})["enabled"] = False
    config.setdefault("tools", {})["profile"] = "coding"
    entries = config.setdefault("agents", {}).setdefault("entries", {})
    for agent in ("main", "bug_reviewer", "test_reviewer", "fixer"):
        entry = entries.setdefault(agent, {"name": agent})
        entry["workspace"] = str(workspaces / agent)
        entry["model"] = model_ref
        entry["skills"] = []
        entry["tools"] = {
            "profile": "coding" if agent == "fixer" else "minimal"
        }
        entry["bootstrapMaxChars"] = 20000
        entry["bootstrapTotalMaxChars"] = 60000
    provider_config = (
        config.setdefault("models", {})
        .setdefault("providers", {})
        .get(provider, {})
    )
    for model in provider_config.get("models", []):
        if model.get("id") == model_id:
            model["contextWindow"] = 128000
            model["maxTokens"] = 8192
            model["reasoning"] = False
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    accuracy_source, accuracy_tests = extract_fixture_evidence(fixture_repo)
    roles = role_files(
        fixture_repo,
        accuracy_source,
        accuracy_tests,
    )
    for agent, instructions in roles.items():
        workspace = workspaces / agent
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(instructions, encoding="utf-8")
        (workspace / "SOUL.md").write_text(
            "# Soul\n\nBe precise, calm, and evidence-driven.\n",
            encoding="utf-8",
        )
        (workspace / "IDENTITY.md").write_text(
            f"# Identity\n\nName: {agent}\n",
            encoding="utf-8",
        )
        (workspace / "USER.md").write_text(
            "# User\n\nPrefer minimal changes and verified results.\n",
            encoding="utf-8",
        )
        (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)
    return model_ref


def extract_result_body(body: dict[str, Any]) -> dict[str, Any]:
    result = body.get("result")
    return result if isinstance(result, dict) else body


def extract_assistant_text(body: dict[str, Any]) -> str:
    result = extract_result_body(body)
    visible = result.get("finalAssistantVisibleText")
    if isinstance(visible, str):
        return visible
    payloads = result.get("payloads") or body.get("payloads") or []
    return "\n".join(
        str(item.get("text") or "")
        for item in payloads
        if isinstance(item, dict)
    )


def extract_agent_meta(body: dict[str, Any]) -> dict[str, Any]:
    result = extract_result_body(body)
    meta = result.get("meta") or body.get("meta") or {}
    agent_meta = meta.get("agentMeta") or {}
    return agent_meta if isinstance(agent_meta, dict) else {}


def run_agent_phase(
    *,
    openclaw: str,
    state_dir: Path,
    proxy: TaggedProxy,
    arm_dir: Path,
    pair_id: int,
    arm: str,
    phase: str,
    prompt: str,
) -> dict[str, Any]:
    proxy.state.set_phase(phase)
    before = len(proxy.state.records)
    started = time.perf_counter()
    result = run_openclaw(
        openclaw,
        state_dir,
        "agent",
        "--agent",
        phase,
        "--session-id",
        f"comparison-p{pair_id}-{arm}-{phase}",
        "--local",
        "--json",
        "--timeout",
        "900",
        "--message",
        prompt,
        timeout=1000,
    )
    wall = time.perf_counter() - started
    phase_dir = arm_dir / "phases" / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (phase_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    require_success(result, phase)
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{phase} returned non-JSON stdout.") from exc
    (phase_dir / "openclaw.json").write_text(
        json.dumps(body, indent=2) + "\n",
        encoding="utf-8",
    )
    calls = proxy.state.records[before:]
    tokens = {
        key: sum(int((row.get("usage") or {}).get(key) or 0) for row in calls)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
        )
    }
    meta = extract_agent_meta(body)
    return {
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "output": extract_assistant_text(body),
        "output_sha256": sha256_text(extract_assistant_text(body)),
        "assistant_turns": int(meta.get("assistantTurns") or 0),
        "wall_time_seconds": round(wall, 3),
        "tokens": tokens,
        "request_count": len(calls),
    }


def build_fixer_prompt(bug_output: str, test_output: str) -> str:
    return (
        "Use the reviewers' exact outputs below as guidance. Work in the "
        "prepared open_type_faster path from AGENTS.md, preserve every test "
        "file, make the smallest source-only correction, run the complete "
        "pytest suite, and report the verified result.\n\n"
        "----- BUG REVIEWER OUTPUT (VERBATIM) -----\n"
        f"{bug_output}\n"
        "----- END BUG REVIEWER OUTPUT -----\n\n"
        "----- TEST REVIEWER OUTPUT (VERBATIM) -----\n"
        f"{test_output}\n"
        "----- END TEST REVIEWER OUTPUT -----"
    )


def build_main_prompt(pytest_result: dict[str, Any]) -> str:
    return (
        "In one sentence, summarize only this independent pytest result. "
        "The stdout and stderr blocks are verbatim.\n\n"
        f"returncode: {pytest_result['returncode']}\n"
        "----- PYTEST STDOUT (VERBATIM) -----\n"
        f"{pytest_result['stdout']}"
        "----- END PYTEST STDOUT -----\n"
        "----- PYTEST STDERR (VERBATIM) -----\n"
        f"{pytest_result['stderr']}"
        "----- END PYTEST STDERR -----"
    )


def parse_pytest_counts(stdout: str) -> dict[str, Any]:
    aliases = {
        "passed": "passed",
        "failed": "failed",
        "error": "errors",
        "errors": "errors",
        "skipped": "skipped",
        "xfailed": "xfailed",
        "xpassed": "xpassed",
        "deselected": "deselected",
        "warning": "warnings",
        "warnings": "warnings",
    }
    summary_line = ""
    counts: Counter[str] = Counter()
    for line in reversed(stdout.splitlines()):
        found = re.findall(
            r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|"
            r"deselected|warnings?)\b",
            line,
        )
        if found:
            summary_line = line.strip()
            for number, label in found:
                counts[aliases[label]] += int(number)
            break
    return {
        "summary_line": summary_line,
        "counts": dict(counts),
    }


def run_pytest(repo: Path, output_dir: Path, label: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = run_process(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
        cwd=repo,
        timeout=240,
    )
    wall = time.perf_counter() - started
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{label}.stdout.txt").write_text(
        result.stdout,
        encoding="utf-8",
    )
    (output_dir / f"{label}.stderr.txt").write_text(
        result.stderr,
        encoding="utf-8",
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "wall_time_seconds": round(wall, 3),
        **parse_pytest_counts(result.stdout),
    }


def source_files(root: Path) -> dict[str, bytes]:
    rows: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {"__pycache__", ".pytest_cache"} for part in relative.parts):
            continue
        if path.suffix == ".pyc":
            continue
        rows[relative.as_posix()] = path.read_bytes()
    return rows


def tree_sha256(files: dict[str, bytes], prefix: str = "") -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        if prefix and not name.startswith(prefix):
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def same_program(left: str, right: str) -> bool:
    """True when both sources parse to the same AST.

    Formatting and redundant parentheses do not change the AST, so
    ``round(correct / total_typed * 100, 1)`` matches the expected fix.
    """
    try:
        return ast.dump(ast.parse(left)) == ast.dump(ast.parse(right))
    except SyntaxError:
        return False


def minimal_ast_equivalent_fix(
    before: str,
    after: str,
    expected: str,
) -> bool:
    """Accept semantic formatting variants only on the intended source line."""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    if len(before_lines) != len(after_lines):
        return False
    changed = [
        index
        for index, (old, new) in enumerate(
            zip(before_lines, after_lines, strict=True)
        )
        if old != new
    ]
    targets = [
        index
        for index, line in enumerate(before_lines)
        if line == OLD_ACCURACY_LINE
    ]
    return changed == targets and len(targets) == 1 and same_program(
        after,
        expected,
    )


def source_integrity(
    pristine: dict[str, bytes],
    current: dict[str, bytes],
) -> dict[str, Any]:
    changed = sorted(
        name
        for name in set(pristine) | set(current)
        if pristine.get(name) != current.get(name)
    )
    tests_before = tree_sha256(pristine, "tests/")
    tests_after = tree_sha256(current, "tests/")
    stats_before = pristine.get("stats.py", b"").decode("utf-8")
    stats_after = current.get("stats.py", b"").decode("utf-8")
    replacement = next(
        (
            line
            for line in ACCEPTED_ACCURACY_LINES
            if stats_after
            == stats_before.replace(OLD_ACCURACY_LINE, line, 1)
        ),
        None,
    )
    expected_stats = stats_before.replace(
        OLD_ACCURACY_LINE,
        NEW_ACCURACY_LINE,
        1,
    )
    ast_equivalent = minimal_ast_equivalent_fix(
        stats_before,
        stats_after,
        expected_stats,
    )
    source_fix_valid = (
        stats_before.count(OLD_ACCURACY_LINE) == 1
        and (replacement is not None or ast_equivalent)
        and changed == ["stats.py"]
    )
    exact_patch = source_fix_valid and replacement == NEW_ACCURACY_LINE
    patch = "".join(
        difflib.unified_diff(
            stats_before.splitlines(keepends=True),
            stats_after.splitlines(keepends=True),
            fromfile="a/stats.py",
            tofile="b/stats.py",
        )
    )
    return {
        "changed_files": changed,
        "tests_sha256_before": tests_before,
        "tests_sha256_after": tests_after,
        "tests_unchanged": tests_before == tests_after,
        "source_fix_valid": source_fix_valid,
        "source_fix_variant": (
            "canonical"
            if replacement == NEW_ACCURACY_LINE
            else "equivalent"
            if replacement == EQUIVALENT_ACCURACY_LINE or ast_equivalent
            else None
        ),
        "exact_source_patch": exact_patch,
        "patch": patch,
    }


def summarize_calls(
    records: list[dict[str, Any]],
    arm: str,
    direct_model: str,
    factors: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    actual_total = 0.0
    auto_glm_total = 0.0
    for row in records:
        headers = row.get("routing_headers") or {}
        selected = (
            headers.get("x-vsr-selected-model")
            or row.get("response_model")
            or row.get("requested_model")
            or direct_model
        )
        canonical = (
            GLM_CANONICAL
            if arm == "direct_glm"
            else canonical_model_id(str(selected), factors)
        )
        if not canonical:
            raise RuntimeError(
                f"Could not map selected model {selected!r} to recipe rates."
            )
        usage = row.get("usage") or {}
        actual = usage_cost_xxx(usage, canonical, factors)
        glm_reprice = usage_cost_xxx(usage, GLM_CANONICAL, factors)
        actual_total += actual
        if arm == "auto":
            auto_glm_total += glm_reprice
        calls.append(
            {
                "request_id": row.get("request_id"),
                "phase": row.get("phase"),
                "status": row.get("status"),
                "requested_model": row.get("requested_model"),
                "response_model": row.get("response_model"),
                "selected_model": selected,
                "cost_model": canonical,
                "decision": headers.get("x-vsr-selected-decision"),
                "reasoning": headers.get("x-vsr-selected-reasoning"),
                "finish_reason": row.get("finish_reason"),
                "tool_count": row.get("tool_count"),
                "latency_seconds": row.get("latency_seconds"),
                "usage": usage,
                "actual_cost_xxx": actual,
                "auto_tokens_glm_reprice_xxx": (
                    glm_reprice if arm == "auto" else None
                ),
            }
        )
    totals = {
        key: sum(
            int((row.get("usage") or {}).get(key) or 0)
            for row in records
        )
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
        )
    }
    return calls, {
        "actual_cost_xxx": round(actual_total, 8),
        "auto_tokens_glm_reprice_xxx": (
            round(auto_glm_total, 8) if arm == "auto" else None
        ),
        "tokens": totals,
        "requests": len(records),
    }


def relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def run_arm(
    *,
    pair_id: int,
    arm: str,
    execution_position: int,
    output_root: Path,
    endpoint: dict[str, Any],
    direct_model: str,
    openclaw: str,
    factors: dict[str, Any],
) -> dict[str, Any]:
    arm_dir = output_root / f"pair-{pair_id:02d}" / arm.replace("_", "-")
    if arm_dir.exists():
        raise RuntimeError(f"Arm directory already exists: {arm_dir}")
    state_dir = arm_dir / "state"
    workspaces = arm_dir / "workspaces"
    fixture_root = arm_dir / "fixture"
    fixture_repo = fixture_root / "open_type_faster"
    arm_dir.mkdir(parents=True)
    shutil.copytree(
        FIXTURE,
        fixture_repo,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    pristine = source_files(fixture_repo)
    total_started = time.perf_counter()
    baseline = run_pytest(fixture_repo, arm_dir / "pytest", "baseline")
    proxy = TaggedProxy(
        endpoint,
        arm_dir / "routes.jsonl",
        pair_id,
        arm,
    )
    proxy.start()
    phases: dict[str, Any] = {}
    posttest: dict[str, Any] | None = None
    workflow_error: Exception | None = None
    workflow_started = time.perf_counter()
    try:
        model_id = endpoint["model"]
        configure_openclaw(
            openclaw=openclaw,
            state_dir=state_dir,
            workspaces=workspaces,
            proxy_url=proxy.base_url,
            model_id=model_id,
            fixture_repo=fixture_repo,
        )
        phases["bug_reviewer"] = run_agent_phase(
            openclaw=openclaw,
            state_dir=state_dir,
            proxy=proxy,
            arm_dir=arm_dir,
            pair_id=pair_id,
            arm=arm,
            phase="bug_reviewer",
            prompt=BUG_PROMPT,
        )
        phases["test_reviewer"] = run_agent_phase(
            openclaw=openclaw,
            state_dir=state_dir,
            proxy=proxy,
            arm_dir=arm_dir,
            pair_id=pair_id,
            arm=arm,
            phase="test_reviewer",
            prompt=TEST_PROMPT,
        )
        fixer_prompt = build_fixer_prompt(
            phases["bug_reviewer"]["output"],
            phases["test_reviewer"]["output"],
        )
        phases["fixer"] = run_agent_phase(
            openclaw=openclaw,
            state_dir=state_dir,
            proxy=proxy,
            arm_dir=arm_dir,
            pair_id=pair_id,
            arm=arm,
            phase="fixer",
            prompt=fixer_prompt,
        )
        posttest = run_pytest(fixture_repo, arm_dir / "pytest", "posttest")
        main_prompt = build_main_prompt(posttest)
        phases["main"] = run_agent_phase(
            openclaw=openclaw,
            state_dir=state_dir,
            proxy=proxy,
            arm_dir=arm_dir,
            pair_id=pair_id,
            arm=arm,
            phase="main",
            prompt=main_prompt,
        )
    except Exception as exc:
        workflow_error = exc
    finally:
        proxy.close()
    workflow_wall = time.perf_counter() - workflow_started
    integrity = source_integrity(pristine, source_files(fixture_repo))
    (arm_dir / "patch.diff").write_text(
        integrity["patch"],
        encoding="utf-8",
    )
    try:
        calls, call_totals = summarize_calls(
            proxy.state.records,
            arm,
            direct_model,
            factors,
        )
        metrics_error = None
    except Exception as exc:
        calls = []
        call_totals = {
            "actual_cost_xxx": 0.0,
            "auto_tokens_glm_reprice_xxx": (
                0.0 if arm == "auto" else None
            ),
            "tokens": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "reasoning_tokens": 0,
                "cached_tokens": 0,
            },
            "requests": len(proxy.state.records),
        }
        metrics_error = f"{type(exc).__name__}: {exc}"
    turns = sum(
        int(phase.get("assistant_turns") or 0)
        for phase in phases.values()
    )
    metrics = {
        **call_totals,
        "assistant_turns": turns,
        "agent_wall_time_seconds": round(
            sum(
                float(phase.get("wall_time_seconds") or 0)
                for phase in phases.values()
            ),
            3,
        ),
        "workflow_wall_time_seconds": round(workflow_wall, 3),
        "total_arm_wall_time_seconds": round(
            time.perf_counter() - total_started,
            3,
        ),
        "complete": workflow_error is None,
        "cost_coverage_complete": metrics_error is None,
    }
    paths = {
        "arm_root": relative_path(arm_dir, output_root),
        "state": relative_path(state_dir, output_root),
        "workspaces": relative_path(workspaces, output_root),
        "fixture": relative_path(fixture_repo, output_root),
        "routes": relative_path(arm_dir / "routes.jsonl", output_root),
    }
    if workflow_error is not None:
        return {
            "status": "error",
            "execution_position": execution_position,
            "requested_model": endpoint["model"],
            "paths": paths,
            "phases": phases,
            "quality": {
                "baseline": baseline,
                "posttest": posttest,
                "baseline_exact": None,
                "posttest_exact": None,
                "integrity": integrity,
                "passed": False,
            },
            "calls": calls,
            "metrics": metrics,
            "error": {
                "type": type(workflow_error).__name__,
                "message": str(workflow_error),
                "metrics_error": metrics_error,
            },
            "passed": False,
        }

    assert posttest is not None
    baseline_counts = baseline["counts"]
    post_counts = posttest["counts"]
    baseline_exact = (
        baseline["returncode"] != 0
        and baseline_counts.get("failed") == 5
        and baseline_counts.get("passed") == 102
        and sum(
            value
            for key, value in baseline_counts.items()
            if key not in {"failed", "passed", "warnings"}
        )
        == 0
    )
    post_exact = (
        posttest["returncode"] == 0
        and post_counts.get("passed") == 107
        and sum(
            value
            for key, value in post_counts.items()
            if key not in {"passed", "warnings"}
        )
        == 0
    )
    quality_passed = (
        baseline_exact
        and post_exact
        and integrity["tests_unchanged"]
        and integrity["source_fix_valid"]
    )
    return {
        "status": "completed",
        "execution_position": execution_position,
        "requested_model": endpoint["model"],
        "paths": paths,
        "phases": phases,
        "handoffs": {
            "fixer": {
                "bug_reviewer_output": phases["bug_reviewer"]["output"],
                "test_reviewer_output": phases["test_reviewer"]["output"],
                "prompt_sha256": phases["fixer"]["prompt_sha256"],
            },
            "main": {
                "pytest_result": {
                    key: posttest[key]
                    for key in ("returncode", "stdout", "stderr")
                },
                "prompt_sha256": phases["main"]["prompt_sha256"],
            },
        },
        "quality": {
            "baseline": baseline,
            "posttest": posttest,
            "baseline_exact": baseline_exact,
            "posttest_exact": post_exact,
            "integrity": integrity,
            "passed": quality_passed,
        },
        "calls": calls,
        "metrics": metrics,
        "passed": quality_passed,
    }


def aggregate_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {"arms": {}}
    for arm in ARMS:
        attempted = [pair["arms"].get(arm, {}) for pair in pairs]
        completed = [
            run
            for run in attempted
            if run.get("status") == "completed"
        ]
        measured = [
            run
            for run in attempted
            if isinstance(run.get("metrics"), dict)
        ]
        costed = [
            run
            for run in measured
            if run["metrics"].get("cost_coverage_complete", True)
        ]
        repriced = [
            run
            for run in costed
            if run["metrics"].get("auto_tokens_glm_reprice_xxx") is not None
        ]
        aggregate["arms"][arm] = {
            "attempts": len(attempted),
            "runs": len(completed),
            "completed": len(completed),
            "passed": sum(bool(run.get("passed")) for run in attempted),
            "failed_or_incomplete": sum(
                run.get("status") != "completed" or not run.get("passed")
                for run in attempted
            ),
            "cost_observed_attempts": len(costed),
            "cost_missing_attempts": len(attempted) - len(costed),
            "requests": sum(
                int(run["metrics"]["requests"]) for run in measured
            ),
            "assistant_turns": sum(
                int(run["metrics"]["assistant_turns"]) for run in measured
            ),
            "tokens": {
                key: sum(
                    int(run["metrics"]["tokens"][key])
                    for run in measured
                )
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "reasoning_tokens",
                    "cached_tokens",
                )
            },
            "workflow_wall_time_seconds": round(
                sum(
                    float(run["metrics"]["workflow_wall_time_seconds"])
                    for run in measured
                ),
                3,
            ),
            "actual_cost_xxx": round(
                sum(
                    float(run["metrics"]["actual_cost_xxx"])
                    for run in costed
                ),
                8,
            ),
            "auto_tokens_glm_reprice_xxx": (
                round(
                    sum(
                        float(
                            run["metrics"]["auto_tokens_glm_reprice_xxx"]
                        )
                        for run in repriced
                    ),
                    8,
                )
                if arm == "auto"
                else None
            ),
            "auto_reprice_observed_attempts": (
                len(repriced) if arm == "auto" else None
            ),
        }
    matched_completed = [
        pair
        for pair in pairs
        if all(
            pair["arms"].get(arm, {}).get("status") == "completed"
            for arm in ARMS
        )
    ]
    matched = [
        pair
        for pair in matched_completed
        if all(
            pair["arms"].get(arm, {}).get("passed") is True
            for arm in ARMS
        )
    ]
    auto_cost = sum(
        float(pair["arms"]["auto"]["metrics"]["actual_cost_xxx"])
        for pair in matched
    )
    direct_cost = sum(
        float(pair["arms"]["direct_glm"]["metrics"]["actual_cost_xxx"])
        for pair in matched
    )
    repriced = sum(
        float(
            pair["arms"]["auto"]["metrics"][
                "auto_tokens_glm_reprice_xxx"
            ]
            or 0
        )
        for pair in matched
    )
    aggregate["paired_cost"] = {
        "primary_actual_execution": {
            "completed_matched_pairs": len(matched),
            "all_completed_matched_pairs": len(matched_completed),
            "successful_matched_pairs": len(matched),
            "auto_actual_cost_xxx": round(auto_cost, 8),
            "direct_glm_actual_cost_xxx": round(direct_cost, 8),
            "direct_minus_auto_xxx": round(direct_cost - auto_cost, 8),
            "auto_savings_percent_vs_direct": (
                round((1 - auto_cost / direct_cost) * 100, 2)
                if direct_cost
                else None
            ),
        },
        "secondary_auto_token_glm_repricing": {
            "completed_matched_pairs": len(matched),
            "successful_matched_pairs": len(matched),
            "auto_actual_cost_xxx": round(auto_cost, 8),
            "auto_tokens_repriced_as_glm_xxx": round(repriced, 8),
            "repriced_minus_auto_xxx": round(repriced - auto_cost, 8),
            "routing_savings_percent": (
                round((1 - auto_cost / repriced) * 100, 2)
                if repriced
                else None
            ),
        },
    }
    return aggregate


def csv_text(summary: dict[str, Any]) -> str:
    output = io.StringIO()
    fields = [
        "pair_id",
        "pair_execution_index",
        "arm",
        "execution_position",
        "requested_model",
        "passed",
        "baseline_failed",
        "baseline_passed",
        "post_passed",
        "tests_unchanged",
        "source_fix_valid",
        "source_fix_variant",
        "exact_source_patch",
        "requests",
        "assistant_turns",
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "workflow_wall_time_seconds",
        "actual_cost_xxx",
        "auto_tokens_glm_reprice_xxx",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for pair in sorted(summary["pairs"], key=lambda item: item["pair_id"]):
        for arm in ARMS:
            run = pair["arms"].get(arm, {})
            quality = run.get("quality") or {}
            metrics = run.get("metrics") or {}
            tokens = metrics.get("tokens") or {}
            writer.writerow(
                {
                    "pair_id": pair["pair_id"],
                    "pair_execution_index": pair["execution_index"],
                    "arm": arm,
                    "execution_position": run.get("execution_position"),
                    "requested_model": run.get("requested_model"),
                    "passed": run.get("passed"),
                    "baseline_failed": (
                        (quality.get("baseline") or {})
                        .get("counts", {})
                        .get("failed")
                    ),
                    "baseline_passed": (
                        (quality.get("baseline") or {})
                        .get("counts", {})
                        .get("passed")
                    ),
                    "post_passed": (
                        (quality.get("posttest") or {})
                        .get("counts", {})
                        .get("passed")
                    ),
                    "tests_unchanged": (
                        (quality.get("integrity") or {}).get("tests_unchanged")
                    ),
                    "source_fix_valid": (
                        (quality.get("integrity") or {}).get(
                            "source_fix_valid"
                        )
                    ),
                    "source_fix_variant": (
                        (quality.get("integrity") or {}).get(
                            "source_fix_variant"
                        )
                    ),
                    "exact_source_patch": (
                        (quality.get("integrity") or {}).get(
                            "exact_source_patch"
                        )
                    ),
                    "requests": metrics.get("requests"),
                    "assistant_turns": metrics.get("assistant_turns"),
                    "prompt_tokens": tokens.get("prompt_tokens"),
                    "completion_tokens": tokens.get("completion_tokens"),
                    "reasoning_tokens": tokens.get("reasoning_tokens"),
                    "workflow_wall_time_seconds": metrics.get(
                        "workflow_wall_time_seconds"
                    ),
                    "actual_cost_xxx": metrics.get("actual_cost_xxx"),
                    "auto_tokens_glm_reprice_xxx": metrics.get(
                        "auto_tokens_glm_reprice_xxx"
                    ),
                }
            )
    return output.getvalue()


def report_text(summary: dict[str, Any]) -> str:
    lines = [
        "# Auto vs Direct GLM Comparison",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        f"Seed: `{summary['seed']}`",
        "",
        "Execution remained sequential and each matched pair completed both "
        "arms before the next pair began.",
        "",
        "| Pair | Pair order | Arm order | Auto pass | Direct GLM pass |",
        "| ---: | ---: | --- | --- | --- |",
    ]
    for pair in sorted(summary["pairs"], key=lambda item: item["pair_id"]):
        lines.append(
            f"| {pair['pair_id']} | {pair['execution_index']} | "
            f"`{' → '.join(pair['arm_order'])}` | "
            f"{pair['arms'].get('auto', {}).get('passed')} | "
            f"{pair['arms'].get('direct_glm', {}).get('passed')} |"
        )
    primary = summary["aggregate"]["paired_cost"]["primary_actual_execution"]
    secondary = summary["aggregate"]["paired_cost"][
        "secondary_auto_token_glm_repricing"
    ]
    fallback_matched = min(
        int(summary["aggregate"]["arms"]["auto"].get("runs") or 0),
        int(summary["aggregate"]["arms"]["direct_glm"].get("runs") or 0),
    )
    lines.extend(
        [
            "",
            "## Reliability",
            "",
            f"- Auto: `{summary['aggregate']['arms']['auto']['passed']}/"
            f"{summary['aggregate']['arms']['auto'].get('attempts', summary['aggregate']['arms']['auto'].get('runs'))}` passed",
            f"- Direct GLM: "
            f"`{summary['aggregate']['arms']['direct_glm']['passed']}/"
            f"{summary['aggregate']['arms']['direct_glm'].get('attempts', summary['aggregate']['arms']['direct_glm'].get('runs'))}` passed",
            "",
            "## Primary: actual executions",
            "",
            f"- Successful matched pairs: "
            f"`{primary.get('successful_matched_pairs', primary.get('completed_matched_pairs', fallback_matched))}`",
            f"- Auto actual cost: `{primary['auto_actual_cost_xxx']:.8f} XXX`",
            f"- Direct GLM actual cost: "
            f"`{primary['direct_glm_actual_cost_xxx']:.8f} XXX`",
            f"- Auto savings vs direct: "
            f"`{primary['auto_savings_percent_vs_direct']}%`",
            "",
            "## Secondary: auto tokens repriced as GLM",
            "",
            f"- Auto actual cost: `{secondary['auto_actual_cost_xxx']:.8f} XXX`",
            f"- Auto-token GLM repricing: "
            f"`{secondary['auto_tokens_repriced_as_glm_xxx']:.8f} XXX`",
            f"- Routing-only savings estimate: "
            f"`{secondary['routing_savings_percent']}%`",
            "",
            "Costs use Decision Balance 0.3.2 rates. `XXX` is a relative "
            "compute unit, not money. The primary comparison uses each arm's "
            "actual tokens; the secondary comparison holds the auto arm's "
            "tokens fixed and reprices them at GLM rates.",
            "",
        ]
    )
    return "\n".join(lines)


def render_derived(summary_path: Path) -> tuple[Path, Path]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    csv_path = summary_path.with_name("comparison.csv")
    report_path = summary_path.with_name("report.md")
    csv_path.write_text(csv_text(summary), encoding="utf-8")
    report_path.write_text(report_text(summary), encoding="utf-8")
    return csv_path, report_path


def verify_summary(
    summary: dict[str, Any],
    factors: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if summary.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version is incorrect")
    if summary.get("recipe", {}).get("version") != "0.3.2":
        errors.append("recipe version is not 0.3.2")
    pairs = summary.get("pairs") or []
    expected_pair_count = int(
        (summary.get("design") or {}).get("matched_pairs")
        or len(pairs)
    )
    plan = summary.get("execution_plan") or []
    if len(plan) != expected_pair_count * len(ARMS):
        errors.append(
            "execution plan does not contain two arms per matched pair"
        )
    for pair_id in range(1, expected_pair_count + 1):
        rows = [item for item in plan if item.get("pair_id") == pair_id]
        if len(rows) != 2 or {item.get("arm") for item in rows} != set(ARMS):
            errors.append(f"pair {pair_id} is not matched")
        positions = sorted(int(item.get("position") or 0) for item in rows)
        if len(positions) == 2 and positions[1] != positions[0] + 1:
            errors.append(f"pair {pair_id} arms are not sequential")
    if len(pairs) != expected_pair_count:
        errors.append(
            "summary pair count does not match design.matched_pairs"
        )
    seen_paths: set[str] = set()
    for pair in pairs:
        for arm in ARMS:
            run = (pair.get("arms") or {}).get(arm) or {}
            if run.get("status") != "completed":
                errors.append(f"pair {pair.get('pair_id')} {arm} did not complete")
                continue
            for key in ("state", "workspaces", "fixture"):
                value = (run.get("paths") or {}).get(key)
                if not value or value in seen_paths:
                    errors.append(
                        f"pair {pair.get('pair_id')} {arm} lacks a unique {key}"
                    )
                seen_paths.add(str(value))
            quality = run.get("quality") or {}
            if not quality.get("baseline_exact"):
                errors.append(f"pair {pair.get('pair_id')} {arm} baseline mismatch")
            if not quality.get("posttest_exact"):
                errors.append(f"pair {pair.get('pair_id')} {arm} posttest mismatch")
            integrity = quality.get("integrity") or {}
            if not integrity.get("tests_unchanged"):
                errors.append(f"pair {pair.get('pair_id')} {arm} changed tests")
            if not integrity.get(
                "source_fix_valid",
                integrity.get("exact_source_patch"),
            ):
                errors.append(
                    f"pair {pair.get('pair_id')} {arm} source fix was not minimal"
                )
            phases = run.get("phases") or {}
            if set(phases) != set(PHASES):
                errors.append(f"pair {pair.get('pair_id')} {arm} phases mismatch")
                continue
            expected_fixer = build_fixer_prompt(
                phases["bug_reviewer"]["output"],
                phases["test_reviewer"]["output"],
            )
            if phases["fixer"].get("prompt") != expected_fixer:
                errors.append(
                    f"pair {pair.get('pair_id')} {arm} reviewer handoff changed"
                )
            pytest_result = {
                key: quality["posttest"][key]
                for key in ("returncode", "stdout", "stderr")
            }
            if phases["main"].get("prompt") != build_main_prompt(pytest_result):
                errors.append(
                    f"pair {pair.get('pair_id')} {arm} pytest handoff changed"
                )
            for call in run.get("calls") or []:
                if call.get("phase") not in PHASES:
                    errors.append(
                        f"pair {pair.get('pair_id')} {arm} has untagged call"
                    )
                expected_cost = usage_cost_xxx(
                    call.get("usage") or {},
                    call.get("cost_model"),
                    factors,
                )
                if abs(expected_cost - float(call.get("actual_cost_xxx") or 0)) > 1e-8:
                    errors.append(
                        f"pair {pair.get('pair_id')} {arm} call cost mismatch"
                    )
    serialized = canonical_json(summary).lower()
    if '"authorization"' in serialized or "bearer " in serialized:
        errors.append("summary appears to contain a credential")
    return errors


def verify_summary_file(summary_path: Path) -> list[str]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    errors = verify_summary(summary, load_cost_factors())
    csv_path = summary_path.with_name("comparison.csv")
    report_path = summary_path.with_name("report.md")
    if not csv_path.is_file() or csv_path.read_text(encoding="utf-8") != csv_text(summary):
        errors.append("comparison.csv is missing or not generated from summary.json")
    if (
        not report_path.is_file()
        or report_path.read_text(encoding="utf-8") != report_text(summary)
    ):
        errors.append("report.md is missing or not generated from summary.json")
    return errors


def default_output_dir(seed: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(
        os.getenv("WORKSHOP_RESULTS_DIR", "/workspace/results")
    )
    return root / f"policy-comparison-{stamp}-{seed}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=PAIR_COUNT,
        help="Number of matched auto/direct-GLM pairs.",
    )
    parser.add_argument(
        "--openclaw",
        default=os.getenv("OPENCLAW_BIN") or shutil.which("openclaw") or "",
    )
    parser.add_argument(
        "--render-only",
        type=Path,
        help="Regenerate CSV/report from an existing summary JSON.",
    )
    return parser.parse_args()


def main() -> int:
    global PAIR_COUNT
    args = parse_args()
    if args.render_only:
        render_derived(args.render_only)
        return 0
    if args.repetitions < 1:
        raise RuntimeError("--repetitions must be at least 1.")
    PAIR_COUNT = args.repetitions
    if not args.openclaw:
        raise RuntimeError("Set OPENCLAW_BIN or put openclaw on PATH.")
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(
        1, 2**63
    )
    output_root = (args.output_dir or default_output_dir(seed)).resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("Output directory already exists and is not empty.")
    output_root.mkdir(parents=True, exist_ok=True)

    factors = load_cost_factors()
    auto_endpoint = endpoint_from_env("auto")
    direct_endpoint = endpoint_from_env("direct_glm")
    auto_preflight = get_models(
        auto_endpoint["base_url"],
        auto_endpoint["api_key"],
    )
    if auto_endpoint["model"] not in auto_preflight["models"]:
        raise RuntimeError("AUTO_MODEL is not present in the auto /models response.")
    direct_preflight = get_models(
        direct_endpoint["base_url"],
        direct_endpoint["api_key"],
    )
    direct_model = discover_glm_model(
        direct_preflight["models"],
        direct_endpoint["model"],
    )
    direct_endpoint["model"] = direct_model
    endpoints = {"auto": auto_endpoint, "direct_glm": direct_endpoint}
    preflights = {"auto": auto_preflight, "direct_glm": direct_preflight}

    plan = build_execution_plan(seed)
    pair_rows: dict[int, dict[str, Any]] = {}
    for item in plan:
        pair_id = int(item["pair_id"])
        pair = pair_rows.setdefault(
            pair_id,
            {
                "pair_id": pair_id,
                "execution_index": item["pair_execution_index"],
                "arm_order": [],
                "arms": {},
            },
        )
        pair["arm_order"].append(item["arm"])
        try:
            run = run_arm(
                pair_id=pair_id,
                arm=item["arm"],
                execution_position=item["position"],
                output_root=output_root,
                endpoint=endpoints[item["arm"]],
                direct_model=direct_model,
                openclaw=args.openclaw,
                factors=factors,
            )
        except Exception as exc:  # checkpoint the other arm/pairs too
            run = {
                "status": "error",
                "execution_position": item["position"],
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "passed": False,
            }
        pair["arms"][item["arm"]] = run

    pairs = sorted(pair_rows.values(), key=lambda item: item["pair_id"])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "recipe": {
            **factors["recipe"],
            "cost_factors_sha256": hashlib.sha256(
                COST_FACTORS.read_bytes()
            ).hexdigest(),
        },
        "seed": seed,
        "design": {
            "matched_pairs": PAIR_COUNT,
            "sequential": True,
            "pair_order_randomized": True,
            "within_pair_arm_order_randomized": True,
        },
        "endpoints": {
            arm: {
                "base_url": endpoint["base_url"],
                "base_url_env": endpoint["base_url_env"],
                "credential_file": str(endpoint["credential_file"]),
                "credential_env": endpoint["credential_env"],
                "model": endpoint["model"],
                "model_env": endpoint["model_env"],
                "preflight": preflights[arm],
            }
            for arm, endpoint in endpoints.items()
        },
        "execution_plan": plan,
        "pairs": pairs,
        "aggregate": aggregate_summary(pairs),
        "artifact_contract": {
            "authoritative": "summary.json",
            "derived": ["comparison.csv", "report.md"],
            "schema": str(SCHEMA.relative_to(DEPLOY)),
        },
    }
    summary["passed"] = all(
        pair["arms"].get(arm, {}).get("passed")
        for pair in pairs
        for arm in ARMS
    )
    summary_path = output_root / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    render_derived(summary_path)
    errors = verify_summary_file(summary_path)
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "seed": seed,
                "passed": summary["passed"] and not errors,
                "verification_errors": errors,
            },
            indent=2,
        )
    )
    return 0 if summary["passed"] and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

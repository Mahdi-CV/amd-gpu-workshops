#!/usr/bin/env python3
"""Run a reproducible, crash-tolerant soak test against the AMD booth API.

The booth accepts one task at a time, so this harness cycles a deterministic
workload matrix sequentially for the requested duration.  It uses SSE when
available, falls back to polling, retries transient HTTP failures, and writes
every state transition incrementally.

Typical four-hour run:

    python3 deploy/soak.py \
      --duration 4h \
      --origin https://agent.example.test \
      --output soak-results/booth-4h \
      --interval 5s

Resume an interrupted invocation without changing the original deadline:

    python3 deploy/soak.py --output soak-results/booth-4h --resume

``--workloads`` accepts either a JSON list or ``{"workloads": [...]}``.  Each
entry requires ``id``, ``title``, and ``prompt``; an optional ``repeat`` weights
the matrix.  Optional quality expectations are preserved for analyze-soak.py:

    {
      "id": "example",
      "title": "Build and verify an example",
      "prompt": "Create example.html and verify it.",
      "quality": {
        "min_result_chars": 80,
        "min_model_calls": 1,
        "min_tool_calls": 1,
        "min_agents": 2,
        "min_artifacts": 1,
        "artifact_globs": ["example.html"]
      }
    }

The output directory contains a manifest, an append-only journal, API probes,
and one attempt directory per submitted workload.  Attempt directories contain
the request, atomic state snapshots, deduplicated events.jsonl, final run JSON,
artifact metadata, and downloaded artifact bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import signal
import socket
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable


SCHEMA_VERSION = 1
HARNESS_VERSION = "1.0"
DEFAULT_ORIGIN = "https://agent.165.245.129.230.sslip.io"
TRANSIENT_HTTP_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
REMOTE_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
LOCAL_FINAL_STATES = {"finished", "submission_failed", "lost"}
STOP_EVENT = threading.Event()


DEFAULT_WORKLOADS: list[dict[str, Any]] = [
    {
        "id": "fast-local-control",
        "title": "Run a brief local-route control",
        "prompt": (
            "Answer briefly in one sentence: what practical benefit does a "
            "semantic model router provide at a live AI demo? Do not browse, "
            "call tools, create files, or spawn subagents; return only the "
            "one-sentence answer."
        ),
        "quality": {
            "min_result_chars": 30,
            "min_model_calls": 1,
            "min_agents": 1,
        },
    },
    {
        "id": "debug-benchmark",
        "title": "Repair and verify the prepared latency benchmark",
        "prompt": (
            "Inspect the prepared benchmark-demo project in the shared run "
            "directory. Reproduce the test failure, make the smallest "
            "source-only fix without changing tests, run the complete test "
            "suite, and ask the reviewer to verify the result. Write a concise "
            "verification.md at the run-directory root with the failing and "
            "passing commands, observed results, and changed file."
        ),
        "quality": {
            "min_result_chars": 80,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 4,
            "artifact_globs": [
                "benchmark-demo/latency_report.py",
                "verification.md",
            ],
        },
    },
    {
        "id": "routing-visual",
        "title": "Build and review a semantic-routing visual",
        "prompt": (
            "Create a polished, self-contained routing-visual.html in the "
            "shared run directory. It must visually explain how OpenClaw sends "
            "fast/default work to local AMD-hosted Qwen, agentic and exact-fact "
            "work to GLM, and frontier/recovery work to Kimi. Include an "
            "accessible text explanation, responsive styling, and no external "
            "assets. Use the builder and reviewer, then perform a deterministic "
            "file-level smoke check."
        ),
        "quality": {
            "min_result_chars": 80,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 1,
            "artifact_globs": ["routing-visual.html"],
        },
    },
    {
        "id": "amd-primary-source-brief",
        "title": "Research and verify a current AMD AI brief",
        "prompt": (
            "Research three current AMD Instinct, ROCm, or open-model platform "
            "facts that are useful to an AI infrastructure engineer. Use only "
            "public primary AMD sources, verify exact publication dates and "
            "figures, distinguish facts from inference, and ask the reviewer "
            "to check every citation. Write amd-primary-source-brief.md in the "
            "shared run directory with source titles, dates, and full URLs."
        ),
        "quality": {
            "min_result_chars": 100,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 1,
            "artifact_globs": ["amd-primary-source-brief.md"],
        },
    },
    {
        "id": "telemetry-rollup",
        "title": "Implement a stdlib telemetry rollup utility",
        "prompt": (
            "Use the builder to create telemetry_rollup.py and "
            "test_telemetry_rollup.py in the shared run directory. The utility "
            "must read newline-delimited JSON request records from stdin and "
            "emit deterministic JSON containing request count, failures, token "
            "totals, mean latency, nearest-rank p50, and nearest-rank p95. Use "
            "only the Python standard library, handle malformed lines with a "
            "clear nonzero exit, run the tests, and have the reviewer verify "
            "edge cases. Record commands and results in verification.md."
        ),
        "quality": {
            "min_result_chars": 100,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 3,
            "artifact_globs": [
                "telemetry_rollup.py",
                "test_telemetry_rollup.py",
                "verification.md",
            ],
        },
    },
    {
        "id": "queue-policy",
        "title": "Design and simulate a booth queue policy",
        "prompt": (
            "Develop a defensible queue policy for a four-hour live AI booth "
            "with one active agent run, a 15-minute hard task timeout, bursty "
            "visitors, and a goal of maximizing completed demos while keeping "
            "p95 wait time bounded. State assumptions, compare at least three "
            "policies, and use a small deterministic Python simulation to test "
            "normal and burst scenarios. Put the runnable simulation in "
            "queue_sim.py and the recommendation plus scenario results in "
            "queue-policy.md. Use the builder and reviewer."
        ),
        "quality": {
            "min_result_chars": 100,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 2,
            "artifact_globs": ["queue_sim.py", "queue-policy.md"],
        },
    },
    {
        "id": "incident-runbook",
        "title": "Create and validate a routed-agent incident runbook",
        "prompt": (
            "Create incident-runbook.md for an operator responding when an "
            "OpenClaw task stalls or vLLM Semantic Router starts returning "
            "errors during a live booth. Cover triage order, evidence to "
            "capture, safe recovery, rollback criteria, and post-recovery "
            "verification. Add a small stdlib-only runbook_check.py that "
            "verifies the document contains every required section and exits "
            "nonzero when one is absent. Run the checker and ask the reviewer "
            "to challenge unsafe or ambiguous steps."
        ),
        "quality": {
            "min_result_chars": 100,
            "min_model_calls": 2,
            "min_tool_calls": 1,
            "min_agents": 2,
            "min_artifacts": 2,
            "artifact_globs": ["incident-runbook.md", "runbook_check.py"],
        },
    },
    {
        "id": "frontier-routing-control",
        "title": "Run a tool-free frontier reasoning control",
        "prompt": (
            "Without browsing, tools, files, or subagents, design a rigorous "
            "routing policy for a pool with one zero-API-cost local model, one "
            "economy cloud model, and one premium cloud model. The policy must "
            "optimize expected answer utility under correlated model failures, "
            "a hard p95 latency budget, uncertain token demand, and a monthly "
            "cloud-spend constraint. Derive the decision variables and "
            "objective, explain how to estimate the needed quantities online, "
            "analyze sensitivity to calibration error, and identify a safe "
            "fallback when telemetry is sparse. Return a self-contained, "
            "carefully checked technical answer."
        ),
        "quality": {
            "min_result_chars": 300,
            "min_model_calls": 1,
            "min_agents": 1,
        },
    },
]


class HarnessError(RuntimeError):
    """Base class for actionable harness failures."""


class ApiError(HarnessError):
    """An HTTP or transport error with retry metadata."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: Any = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.transient = transient


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""

    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO timestamp written by this harness."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)?", re.IGNORECASE)


def parse_duration(value: str) -> float:
    """Parse seconds or a compact duration such as 500ms, 30s, 5m, or 4h."""

    text = str(value).strip().lower().replace(" ", "")
    if not text:
        raise argparse.ArgumentTypeError("duration cannot be empty")
    total = 0.0
    position = 0
    scales = {
        None: 1.0,
        "ms": 0.001,
        "s": 1.0,
        "m": 60.0,
        "h": 3600.0,
        "d": 86400.0,
    }
    for match in _DURATION_PART.finditer(text):
        if match.start() != position:
            raise argparse.ArgumentTypeError(f"invalid duration: {value!r}")
        total += float(match.group(1)) * scales[match.group(2)]
        position = match.end()
    if position != len(text):
        raise argparse.ArgumentTypeError(f"invalid duration: {value!r}")
    return total


def positive_duration(value: str) -> float:
    """Argparse duration type requiring a positive result."""

    parsed = parse_duration(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("duration must be greater than zero")
    return parsed


def nonnegative_duration(value: str) -> float:
    """Argparse duration type allowing zero."""

    parsed = parse_duration(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("duration cannot be negative")
    return parsed


def log(message: str) -> None:
    """Write a timestamped progress line."""

    print(f"[{iso_now()}] {message}", flush=True)


def compact_error(value: Any, limit: int = 500) -> str:
    """Turn an exception or response body into one bounded line."""

    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        try:
            text = " ".join(json.dumps(value, ensure_ascii=False).split())
        except (TypeError, ValueError):
            text = " ".join(str(value).split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def safe_slug(value: str, limit: int = 48) -> str:
    """Create a stable filesystem-safe identifier."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "workload")[:limit].rstrip("-")


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically replace a JSON file and fsync its contents."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    """Append one durable JSON record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path) -> Any:
    """Read a JSON file."""

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def responsive_wait(seconds: float) -> bool:
    """Wait until timeout or a stop signal; return true if stopped."""

    if seconds <= 0:
        return STOP_EVENT.is_set()
    return STOP_EVENT.wait(seconds)


def retry_delay(attempt: int, base: float) -> float:
    """Return a bounded deterministic exponential backoff."""

    return min(60.0, max(0.5, base) * (2 ** max(0, attempt)))


def decode_body(raw: bytes) -> Any:
    """Decode a JSON response when possible, otherwise return bounded text."""

    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return compact_error(text, 4000)


class BoothClient:
    """Small stdlib HTTP client for the booth API."""

    def __init__(
        self,
        origin: str,
        *,
        timeout: float,
        retries: int,
        retry_interval: float,
        insecure: bool,
    ) -> None:
        self.origin = origin.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.retry_interval = retry_interval
        self.context = ssl.create_default_context()
        if insecure:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE

    def url(self, path: str) -> str:
        """Resolve an API path relative to the configured origin."""

        if path.startswith(("http://", "https://")):
            return path
        return self.origin + "/" + path.lstrip("/")

    def _open(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        accept: str = "application/json",
        timeout: float | None = None,
    ) -> BinaryIO:
        headers = {
            "Accept": accept,
            "User-Agent": f"amd-booth-soak/{HARNESS_VERSION}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.url(path),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            return urllib.request.urlopen(
                request,
                context=self.context,
                timeout=timeout or self.timeout,
            )
        except urllib.error.HTTPError as exc:
            raw = exc.read(64 * 1024)
            body_value = decode_body(raw)
            raise ApiError(
                f"{method} {path} returned HTTP {exc.code}: "
                f"{compact_error(body_value)}",
                status=exc.code,
                body=body_value,
                transient=exc.code in TRANSIENT_HTTP_STATUSES,
            ) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            ConnectionError,
            OSError,
        ) as exc:
            raise ApiError(
                f"{method} {path} failed: {compact_error(exc)}",
                transient=True,
            ) from exc

    def json_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        retry_safe: bool = True,
    ) -> dict[str, Any]:
        """Issue a JSON request, retrying only when explicitly safe."""

        encoded = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        attempts = self.retries + 1 if retry_safe else 1
        last_error: ApiError | None = None
        for attempt in range(attempts):
            try:
                with self._open(method, path, body=encoded) as response:
                    value = decode_body(response.read())
                if not isinstance(value, dict):
                    raise ApiError(
                        f"{method} {path} returned non-object JSON",
                        body=value,
                    )
                return value
            except ApiError as exc:
                last_error = exc
                if (
                    not retry_safe
                    or not exc.transient
                    or attempt + 1 >= attempts
                    or STOP_EVENT.is_set()
                ):
                    raise
                if responsive_wait(retry_delay(attempt, self.retry_interval)):
                    raise
            except (
                http.client.HTTPException,
                TimeoutError,
                socket.timeout,
                ssl.SSLError,
                ConnectionError,
                OSError,
            ) as exc:
                last_error = ApiError(
                    f"{method} {path} response failed: "
                    f"{compact_error(exc)}",
                    transient=True,
                )
                if (
                    not retry_safe
                    or attempt + 1 >= attempts
                    or STOP_EVENT.is_set()
                ):
                    raise last_error from exc
                if responsive_wait(retry_delay(attempt, self.retry_interval)):
                    raise last_error from exc
        assert last_error is not None
        raise last_error

    def get_json(self, path: str) -> dict[str, Any]:
        """GET an object response with safe retries."""

        return self.json_request("GET", path, retry_safe=True)

    def post_json_once(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST once; callers recover ambiguity before retrying."""

        return self.json_request(
            "POST",
            path,
            payload=payload or {},
            retry_safe=False,
        )

    def open_sse(self, path: str, timeout: float) -> BinaryIO:
        """Open one SSE response."""

        return self._open(
            "GET",
            path,
            accept="text/event-stream",
            timeout=timeout,
        )

    def open_artifact(self, url: str) -> BinaryIO:
        """Open a same-origin artifact URL."""

        target = urllib.parse.urljoin(self.origin + "/", url)
        origin_parts = urllib.parse.urlsplit(self.origin)
        target_parts = urllib.parse.urlsplit(target)
        if (
            origin_parts.scheme.lower(),
            origin_parts.netloc.lower(),
        ) != (
            target_parts.scheme.lower(),
            target_parts.netloc.lower(),
        ):
            raise HarnessError(f"refusing cross-origin artifact URL: {url}")
        target = urllib.parse.urlunsplit(
            target_parts._replace(
                path=urllib.parse.quote(
                    target_parts.path,
                    safe="/%:@",
                )
            )
        )
        return self._open("GET", target, accept="*/*")


class ResultStore:
    """Crash-safe filesystem layout for one soak invocation."""

    def __init__(self, output: Path, resume: bool) -> None:
        self.output = output.resolve()
        self.manifest_path = self.output / "manifest.json"
        self.journal_path = self.output / "journal.jsonl"
        existed = self.output.exists()
        if existed and any(self.output.iterdir()) and not resume:
            raise HarnessError(
                f"output directory is not empty: {self.output}; "
                "use --resume or choose another --output"
            )
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "attempts").mkdir(exist_ok=True)
        if resume and not self.manifest_path.is_file():
            raise HarnessError(
                f"--resume requires {self.manifest_path} to exist"
            )

    def load_manifest(self) -> dict[str, Any]:
        """Load the existing manifest."""

        value = read_json(self.manifest_path)
        if not isinstance(value, dict):
            raise HarnessError("manifest.json must contain an object")
        return value

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        """Atomically persist the manifest."""

        manifest["updated_at"] = iso_now()
        atomic_write_json(self.manifest_path, manifest)

    def journal(self, event_type: str, **fields: Any) -> None:
        """Append a journal record."""

        append_jsonl(
            self.journal_path,
            {"timestamp": iso_now(), "type": event_type, **fields},
        )

    def attempt_directories(self) -> list[Path]:
        """Return attempt directories in sequence order."""

        return sorted(
            path
            for path in (self.output / "attempts").iterdir()
            if path.is_dir() and (path / "attempt.json").is_file()
        )

    def create_attempt(
        self,
        sequence: int,
        matrix_index: int,
        workload: dict[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        """Create and persist a prepared attempt."""

        directory = self.output / "attempts" / (
            f"{sequence:05d}-{safe_slug(str(workload['id']))}"
        )
        directory.mkdir(parents=False, exist_ok=False)
        suffix = f" [soak-{sequence:05d}]"
        title = str(workload["title"])
        title = title[: max(1, 100 - len(suffix))].rstrip() + suffix
        request = {"task": workload["prompt"], "title": title}
        attempt = {
            "schema_version": SCHEMA_VERSION,
            "sequence": sequence,
            "matrix_index": matrix_index,
            "workload": workload,
            "title": title,
            "request": request,
            "state": "prepared",
            "status": "not_submitted",
            "created_at": iso_now(),
            "errors": [],
            "event_count": 0,
        }
        atomic_write_json(directory / "workload.json", workload)
        atomic_write_json(directory / "request.json", request)
        self.write_attempt(directory, attempt)
        self.journal(
            "attempt.prepared",
            sequence=sequence,
            workload_id=workload["id"],
            attempt_path=str(directory.relative_to(self.output)),
        )
        return directory, attempt

    def write_attempt(
        self,
        directory: Path,
        attempt: dict[str, Any],
    ) -> None:
        """Atomically persist attempt state."""

        attempt["updated_at"] = iso_now()
        atomic_write_json(directory / "attempt.json", attempt)


class EventSink:
    """Append deduplicated SSE events while preserving partial progress."""

    def __init__(
        self,
        path: Path,
        on_event: Callable[[dict[str, Any]], None],
    ) -> None:
        self.path = path
        self.on_event = on_event
        self.keys: set[str] = set()
        self.count = 0
        if path.is_file():
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        self.keys.add(self._key(value))
                        self.count += 1

    @staticmethod
    def _key(event: dict[str, Any]) -> str:
        if event.get("seq") is not None:
            return f"seq:{event['seq']}"
        canonical = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

    def append(self, event: dict[str, Any]) -> bool:
        """Append an event if it has not already been observed."""

        key = self._key(event)
        if key in self.keys:
            return False
        append_jsonl(self.path, event)
        self.keys.add(key)
        self.count += 1
        self.on_event(event)
        return True


def load_workloads(path: Path | None) -> list[dict[str, Any]]:
    """Load, validate, and expand a workload matrix."""

    raw: Any = DEFAULT_WORKLOADS if path is None else read_json(path)
    if isinstance(raw, dict):
        raw = raw.get("workloads")
    if not isinstance(raw, list) or not raw:
        raise HarnessError("workload matrix must be a non-empty JSON list")

    expanded: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HarnessError(f"workload {index} must be a JSON object")
        missing = [
            field
            for field in ("id", "title", "prompt")
            if not isinstance(item.get(field), str) or not item[field].strip()
        ]
        if missing:
            raise HarnessError(
                f"workload {index} has missing/invalid fields: "
                + ", ".join(missing)
            )
        workload_id = item["id"].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", workload_id):
            raise HarnessError(
                f"workload id must be filesystem-safe: {workload_id!r}"
            )
        if workload_id in seen_ids:
            raise HarnessError(f"duplicate workload id: {workload_id}")
        seen_ids.add(workload_id)
        if len(item["prompt"]) > 4000:
            raise HarnessError(
                f"workload {workload_id} prompt exceeds 4000 characters"
            )
        if len(item["title"]) > 90:
            raise HarnessError(
                f"workload {workload_id} title exceeds 90 characters"
            )
        repeat = item.get("repeat", 1)
        if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 1:
            raise HarnessError(
                f"workload {workload_id} repeat must be a positive integer"
            )
        quality = item.get("quality", {})
        if not isinstance(quality, dict):
            raise HarnessError(
                f"workload {workload_id} quality must be an object"
            )
        normalized = {
            "id": workload_id,
            "title": item["title"].strip(),
            "prompt": item["prompt"].strip(),
            "quality": quality,
        }
        for _ in range(repeat):
            expanded.append(normalized)
    return expanded


def record_attempt_error(
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    phase: str,
    error: Any,
) -> None:
    """Persist one bounded error on an attempt and in the global journal."""

    item = {
        "timestamp": iso_now(),
        "phase": phase,
        "error": compact_error(error, 1000),
    }
    attempt.setdefault("errors", []).append(item)
    attempt["errors"] = attempt["errors"][-100:]
    store.write_attempt(directory, attempt)
    store.journal(
        "attempt.error",
        sequence=attempt["sequence"],
        workload_id=attempt["workload"]["id"],
        phase=phase,
        error=item["error"],
    )


def probe_api(
    client: BoothClient,
    store: ResultStore,
    label: str,
    path: str,
) -> dict[str, Any]:
    """Capture one best-effort API probe."""

    try:
        body = client.get_json(path)
        value = {"captured_at": iso_now(), "ok": True, "body": body}
    except ApiError as exc:
        value = {
            "captured_at": iso_now(),
            "ok": False,
            "error": compact_error(exc),
            "status": exc.status,
            "body": exc.body,
        }
    atomic_write_json(store.output / f"{label}.json", value)
    return value


def matching_active_run(
    client: BoothClient,
    title: str,
) -> tuple[str | None, str | None]:
    """Return a matching active run id, or a different busy run id."""

    health = client.get_json("/healthz")
    active_id = health.get("active_run")
    if not isinstance(active_id, str) or not active_id:
        return None, None
    run = client.get_json(f"/api/runs/{urllib.parse.quote(active_id)}")
    if run.get("title") == title:
        return active_id, None
    return None, active_id


def submit_attempt(
    client: BoothClient,
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    deadline: datetime,
    poll_interval: float,
) -> str | None:
    """Submit an attempt, recovering ambiguous POST outcomes by title."""

    last_busy_id: str | None = None
    while utc_now() < deadline and not STOP_EVENT.is_set():
        try:
            matching_id, busy_id = matching_active_run(
                client,
                attempt["title"],
            )
            if matching_id:
                attempt["run_id"] = matching_id
                attempt["state"] = "submitted"
                attempt["status"] = "queued"
                attempt.setdefault("submitted_at", iso_now())
                attempt["recovered_submission"] = True
                store.write_attempt(directory, attempt)
                store.journal(
                    "attempt.submission_recovered",
                    sequence=attempt["sequence"],
                    run_id=matching_id,
                )
                return matching_id
            if busy_id:
                if busy_id != last_busy_id:
                    log(
                        f"attempt {attempt['sequence']:05d}: booth busy with "
                        f"run {busy_id}; waiting"
                    )
                    store.journal(
                        "booth.busy",
                        sequence=attempt["sequence"],
                        active_run=busy_id,
                    )
                    last_busy_id = busy_id
                responsive_wait(poll_interval)
                continue
        except ApiError as exc:
            record_attempt_error(
                store,
                directory,
                attempt,
                "submission_preflight",
                exc,
            )
            responsive_wait(poll_interval)
            continue

        if utc_now() >= deadline or STOP_EVENT.is_set():
            break
        attempt["state"] = "submitting"
        attempt["status"] = "submitting"
        attempt["post_started_at"] = iso_now()
        store.write_attempt(directory, attempt)
        try:
            response = client.post_json_once("/api/runs", attempt["request"])
            run_id = response.get("id")
            if not isinstance(run_id, str) or not run_id:
                raise ApiError(
                    "POST /api/runs returned no run id",
                    body=response,
                )
            attempt["run_id"] = run_id
            attempt["state"] = "submitted"
            attempt["status"] = str(response.get("status") or "queued")
            attempt["submitted_at"] = iso_now()
            store.write_attempt(directory, attempt)
            store.journal(
                "attempt.submitted",
                sequence=attempt["sequence"],
                workload_id=attempt["workload"]["id"],
                run_id=run_id,
            )
            log(
                f"attempt {attempt['sequence']:05d} "
                f"({attempt['workload']['id']}) submitted as {run_id}"
            )
            return run_id
        except ApiError as exc:
            record_attempt_error(
                store,
                directory,
                attempt,
                "submission",
                exc,
            )
            try:
                matching_id, _ = matching_active_run(
                    client,
                    attempt["title"],
                )
            except ApiError as recovery_error:
                record_attempt_error(
                    store,
                    directory,
                    attempt,
                    "submission_recovery",
                    recovery_error,
                )
                matching_id = None
            if matching_id:
                attempt["run_id"] = matching_id
                attempt["state"] = "submitted"
                attempt["status"] = "queued"
                attempt["submitted_at"] = iso_now()
                attempt["recovered_submission"] = True
                store.write_attempt(directory, attempt)
                store.journal(
                    "attempt.submission_recovered",
                    sequence=attempt["sequence"],
                    run_id=matching_id,
                )
                log(
                    f"attempt {attempt['sequence']:05d}: recovered "
                    f"ambiguous submission as {matching_id}"
                )
                return matching_id
            if exc.status is not None and not exc.transient:
                break
            responsive_wait(poll_interval)

    if STOP_EVENT.is_set():
        attempt["state"] = "interrupted"
        attempt["status"] = "interrupted"
        attempt["interrupted_at"] = iso_now()
    else:
        attempt["state"] = "submission_failed"
        attempt["status"] = "submission_failed"
        attempt["finished_at"] = iso_now()
    store.write_attempt(directory, attempt)
    store.journal(
        (
            "attempt.interrupted"
            if STOP_EVENT.is_set()
            else "attempt.submission_failed"
        ),
        sequence=attempt["sequence"],
        workload_id=attempt["workload"]["id"],
        status=attempt["status"],
    )
    return None


def snapshot_run(
    client: BoothClient,
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Fetch and persist the latest run snapshot."""

    snapshot = client.get_json(
        f"/api/runs/{urllib.parse.quote(run_id, safe='')}"
    )
    atomic_write_json(directory / "run.latest.json", snapshot)
    attempt["status"] = str(snapshot.get("status") or "unknown")
    attempt["last_snapshot_at"] = iso_now()
    store.write_attempt(directory, attempt)
    return snapshot


def consume_sse(
    client: BoothClient,
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    run_id: str,
    sink: EventSink,
    timeout: float,
    run_deadline: datetime,
) -> None:
    """Consume one SSE connection, appending valid events immediately."""

    path = f"/api/runs/{urllib.parse.quote(run_id, safe='')}/events"
    with client.open_sse(path, timeout) as response:
        data_lines: list[str] = []
        for raw_line in response:
            if STOP_EVENT.is_set() or utc_now() >= run_deadline:
                return
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if data_lines:
                    payload = "\n".join(data_lines)
                    data_lines.clear()
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        append_jsonl(
                            directory / "sse-errors.jsonl",
                            {
                                "timestamp": iso_now(),
                                "error": "invalid SSE JSON",
                                "payload": payload[:4000],
                            },
                        )
                    else:
                        if isinstance(event, dict) and sink.append(event):
                            attempt["event_count"] = sink.count
                            attempt["last_event_at"] = iso_now()
                            store.write_attempt(directory, attempt)
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            payload = "\n".join(data_lines)
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                append_jsonl(
                    directory / "sse-errors.jsonl",
                    {
                        "timestamp": iso_now(),
                        "error": "invalid trailing SSE JSON",
                        "payload": payload[:4000],
                    },
                )
            else:
                if isinstance(event, dict) and sink.append(event):
                    attempt["event_count"] = sink.count
                    attempt["last_event_at"] = iso_now()
                    store.write_attempt(directory, attempt)


def safe_artifact_path(value: str) -> PurePosixPath:
    """Validate a relative artifact path returned by the booth."""

    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise HarnessError(f"unsafe artifact path: {value!r}")
    return path


def download_one_artifact(
    client: BoothClient,
    url: str,
    destination: Path,
    max_bytes: int,
    retries: int,
    retry_interval: float,
) -> dict[str, Any]:
    """Download one artifact atomically and return capture metadata."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        digest = hashlib.sha256()
        size = 0
        try:
            with client.open_artifact(url) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise HarnessError(
                        f"artifact exceeds {max_bytes} byte limit"
                    )
                with temporary.open("wb") as handle:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise HarnessError(
                                f"artifact exceeds {max_bytes} byte limit"
                            )
                        digest.update(chunk)
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            os.replace(temporary, destination)
            return {
                "status": "downloaded",
                "bytes": size,
                "sha256": digest.hexdigest(),
                "local_path": str(destination),
            }
        except (
            ApiError,
            HarnessError,
            http.client.HTTPException,
            OSError,
            ValueError,
        ) as exc:
            last_error = exc
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            transient = (
                isinstance(exc, ApiError) and exc.transient
            ) or isinstance(exc, http.client.HTTPException)
            if (
                not transient
                or attempt >= retries
                or STOP_EVENT.is_set()
            ):
                break
            responsive_wait(retry_delay(attempt, retry_interval))
    assert last_error is not None
    return {
        "status": "failed",
        "error": compact_error(last_error, 1000),
    }


def capture_artifacts(
    client: BoothClient,
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    snapshot: dict[str, Any],
    max_bytes: int,
    retries: int,
    retry_interval: float,
) -> None:
    """Download all artifacts listed by a terminal run snapshot."""

    raw_artifacts = snapshot.get("artifacts") or []
    records: list[dict[str, Any]] = []
    attempt["state"] = "capturing_artifacts"
    attempt["artifact_count"] = len(raw_artifacts)
    store.write_attempt(directory, attempt)
    for index, artifact in enumerate(raw_artifacts):
        record: dict[str, Any] = {
            "index": index,
            "captured_at": iso_now(),
            "remote": artifact,
        }
        try:
            if not isinstance(artifact, dict):
                raise HarnessError("artifact metadata is not an object")
            relative = safe_artifact_path(
                str(artifact.get("path") or artifact.get("name") or "")
            )
            url = (
                "/artifacts/"
                + urllib.parse.quote(
                    str(attempt["run_id"]),
                    safe="",
                )
                + "/"
                + urllib.parse.quote(relative.as_posix(), safe="/")
            )
            destination = directory / "artifacts" / Path(*relative.parts)
            record.update(
                download_one_artifact(
                    client,
                    url,
                    destination,
                    max_bytes,
                    retries,
                    retry_interval,
                )
            )
            if record["status"] == "downloaded":
                record["local_path"] = str(
                    destination.relative_to(directory)
                )
        except (HarnessError, OSError, ValueError) as exc:
            record.update(
                {"status": "failed", "error": compact_error(exc, 1000)}
            )
        records.append(record)
        atomic_write_json(directory / "artifacts.json", records)
        attempt["artifacts_captured"] = sum(
            item.get("status") == "downloaded" for item in records
        )
        attempt["artifact_capture_failures"] = sum(
            item.get("status") == "failed" for item in records
        )
        store.write_attempt(directory, attempt)

    if not raw_artifacts:
        atomic_write_json(directory / "artifacts.json", records)
        attempt["artifacts_captured"] = 0
        attempt["artifact_capture_failures"] = 0


def collect_attempt(
    client: BoothClient,
    store: ResultStore,
    directory: Path,
    attempt: dict[str, Any],
    *,
    poll_interval: float,
    sse_timeout: float,
    run_timeout: float,
    max_artifact_bytes: int,
    retries: int,
    retry_interval: float,
) -> dict[str, Any] | None:
    """Collect one submitted run through terminal status or interruption."""

    run_id = str(attempt["run_id"])
    attempt["state"] = "collecting"
    attempt["collection_started_at"] = attempt.get(
        "collection_started_at",
        iso_now(),
    )
    store.write_attempt(directory, attempt)
    submitted_at = parse_iso(attempt.get("submitted_at")) or utc_now()
    run_deadline = submitted_at + timedelta(seconds=run_timeout)

    def on_event(event: dict[str, Any]) -> None:
        store.journal(
            "run.event",
            sequence=attempt["sequence"],
            run_id=run_id,
            seq=event.get("seq"),
            run_event_type=event.get("type"),
        )

    sink = EventSink(directory / "events.jsonl", on_event)
    attempt["event_count"] = sink.count
    snapshot: dict[str, Any] | None = None
    cancel_requested = bool(attempt.get("timeout_cancel_requested"))

    while not STOP_EVENT.is_set():
        if utc_now() >= run_deadline and not cancel_requested:
            attempt["timeout_cancel_requested"] = True
            attempt["timeout_at"] = iso_now()
            store.write_attempt(directory, attempt)
            try:
                client.post_json_once(
                    f"/api/runs/{urllib.parse.quote(run_id, safe='')}/cancel"
                )
                store.journal(
                    "run.cancel_requested",
                    sequence=attempt["sequence"],
                    run_id=run_id,
                    reason="local run timeout",
                )
            except ApiError as exc:
                record_attempt_error(
                    store,
                    directory,
                    attempt,
                    "timeout_cancel",
                    exc,
                )
            cancel_requested = True

        try:
            snapshot = snapshot_run(
                client,
                store,
                directory,
                attempt,
                run_id,
            )
        except ApiError as exc:
            if exc.status == 404:
                attempt["state"] = "lost"
                attempt["status"] = "lost"
                attempt["finished_at"] = iso_now()
                record_attempt_error(
                    store,
                    directory,
                    attempt,
                    "snapshot",
                    "run no longer exists; booth may have restarted",
                )
                store.write_attempt(directory, attempt)
                store.journal(
                    "run.lost",
                    sequence=attempt["sequence"],
                    run_id=run_id,
                )
                return None
            record_attempt_error(
                store,
                directory,
                attempt,
                "snapshot",
                exc,
            )
            responsive_wait(poll_interval)
            continue

        status = str(snapshot.get("status") or "unknown")
        if status in REMOTE_TERMINAL_STATUSES:
            break

        try:
            consume_sse(
                client,
                store,
                directory,
                attempt,
                run_id,
                sink,
                sse_timeout,
                run_deadline,
            )
        except (
            ApiError,
            http.client.HTTPException,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            ConnectionError,
            OSError,
        ) as exc:
            record_attempt_error(
                store,
                directory,
                attempt,
                "sse",
                exc,
            )
        if not STOP_EVENT.is_set():
            responsive_wait(poll_interval)

    if STOP_EVENT.is_set():
        try:
            snapshot = snapshot_run(
                client,
                store,
                directory,
                attempt,
                run_id,
            )
        except ApiError as exc:
            record_attempt_error(
                store,
                directory,
                attempt,
                "interrupt_snapshot",
                exc,
            )
        if not snapshot or snapshot.get("status") not in REMOTE_TERMINAL_STATUSES:
            attempt["state"] = "interrupted"
            attempt["status"] = (
                str(snapshot.get("status"))
                if snapshot and snapshot.get("status")
                else "interrupted"
            )
            attempt["interrupted_at"] = iso_now()
            store.write_attempt(directory, attempt)
            return snapshot

    if snapshot is None:
        return None
    if snapshot.get("status") not in REMOTE_TERMINAL_STATUSES:
        snapshot = snapshot_run(
            client,
            store,
            directory,
            attempt,
            run_id,
        )
    atomic_write_json(directory / "run.json", snapshot)
    capture_artifacts(
        client,
        store,
        directory,
        attempt,
        snapshot,
        max_artifact_bytes,
        retries,
        retry_interval,
    )
    attempt["state"] = "finished"
    attempt["status"] = str(snapshot.get("status") or "unknown")
    attempt["finished_at"] = iso_now()
    attempt["event_count"] = sink.count
    store.write_attempt(directory, attempt)
    store.journal(
        "attempt.finished",
        sequence=attempt["sequence"],
        workload_id=attempt["workload"]["id"],
        run_id=run_id,
        status=attempt["status"],
        event_count=sink.count,
        artifact_count=attempt.get("artifact_count", 0),
    )
    metrics = snapshot.get("metrics") or {}
    log(
        f"attempt {attempt['sequence']:05d} {attempt['status']}: "
        f"{metrics.get('calls', 0)} model calls, "
        f"{attempt.get('artifacts_captured', 0)} artifacts"
    )
    return snapshot


def recover_incomplete_attempts(
    client: BoothClient,
    store: ResultStore,
    *,
    deadline: datetime,
    poll_interval: float,
    sse_timeout: float,
    run_timeout: float,
    max_artifact_bytes: int,
    retries: int,
    retry_interval: float,
) -> None:
    """Recover attempts left nonterminal by an interrupted process."""

    for directory in store.attempt_directories():
        attempt = read_json(directory / "attempt.json")
        if attempt.get("state") in LOCAL_FINAL_STATES:
            continue
        sequence = int(attempt.get("sequence") or 0)
        run_id = attempt.get("run_id")
        if isinstance(run_id, str) and run_id:
            log(f"resuming collection for attempt {sequence:05d} ({run_id})")
            collect_attempt(
                client,
                store,
                directory,
                attempt,
                poll_interval=poll_interval,
                sse_timeout=sse_timeout,
                run_timeout=run_timeout,
                max_artifact_bytes=max_artifact_bytes,
                retries=retries,
                retry_interval=retry_interval,
            )
            continue
        if attempt.get("state") == "prepared" and utc_now() < deadline:
            run_id = submit_attempt(
                client,
                store,
                directory,
                attempt,
                deadline,
                poll_interval,
            )
            if run_id:
                collect_attempt(
                    client,
                    store,
                    directory,
                    attempt,
                    poll_interval=poll_interval,
                    sse_timeout=sse_timeout,
                    run_timeout=run_timeout,
                    max_artifact_bytes=max_artifact_bytes,
                    retries=retries,
                    retry_interval=retry_interval,
                )
            continue

        # A process may have died after sending POST but before receiving the
        # run id.  Adopt only an active run with our unique title.  If it has
        # already disappeared, preserve the ambiguity instead of duplicating it.
        try:
            matching_id, _ = matching_active_run(client, attempt["title"])
        except ApiError as exc:
            record_attempt_error(
                store,
                directory,
                attempt,
                "resume_submission_recovery",
                exc,
            )
            matching_id = None
        if matching_id:
            attempt["run_id"] = matching_id
            attempt["submitted_at"] = attempt.get("post_started_at", iso_now())
            store.write_attempt(directory, attempt)
            collect_attempt(
                client,
                store,
                directory,
                attempt,
                poll_interval=poll_interval,
                sse_timeout=sse_timeout,
                run_timeout=run_timeout,
                max_artifact_bytes=max_artifact_bytes,
                retries=retries,
                retry_interval=retry_interval,
            )
        else:
            attempt["state"] = "lost"
            attempt["status"] = "ambiguous_submission"
            attempt["finished_at"] = iso_now()
            record_attempt_error(
                store,
                directory,
                attempt,
                "resume_submission_recovery",
                "could not identify the result of the prior POST",
            )
            store.write_attempt(directory, attempt)


def next_sequence_and_index(
    store: ResultStore,
    workload_count: int,
) -> tuple[int, int]:
    """Derive the next sequence and matrix position from durable attempts."""

    directories = store.attempt_directories()
    if not directories:
        return 1, 0
    last = read_json(directories[-1] / "attempt.json")
    sequence = int(last.get("sequence") or len(directories)) + 1
    matrix_index = (int(last.get("matrix_index") or 0) + 1) % workload_count
    return sequence, matrix_index


def install_signal_handlers() -> None:
    """Request a resumable shutdown on SIGINT or SIGTERM."""

    def handle_signal(signum: int, _frame: Any) -> None:
        if not STOP_EVENT.is_set():
            print(
                f"\nreceived signal {signum}; preserving resumable state...",
                file=sys.stderr,
                flush=True,
            )
        STOP_EVENT.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run a sequential AMD booth OpenClaw/vLLM-SR soak and capture "
            "run JSON, SSE events, metrics, and artifacts incrementally."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--duration",
        type=positive_duration,
        default="4h",
        help=(
            "submission window; compact units and combinations such as "
            "4h or 1h30m are accepted (an in-flight run is allowed to finish)"
        ),
    )
    parser.add_argument(
        "--origin",
        default=None,
        help=(
            "booth origin; defaults to BOOTH_ORIGIN, the saved origin when "
            "resuming, or the public demo origin"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "result directory; defaults to "
            "soak-results/YYYYmmddTHHMMSSZ"
        ),
    )
    parser.add_argument(
        "--interval",
        type=nonnegative_duration,
        default="5s",
        help="idle delay between completed workload attempts",
    )
    parser.add_argument(
        "--poll-interval",
        type=positive_duration,
        default="5s",
        help="delay between fallback polls and submission retries",
    )
    parser.add_argument(
        "--workloads",
        type=Path,
        help="JSON workload matrix; omit to use the built-in agentic matrix",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume an existing output directory and its original deadline",
    )
    parser.add_argument(
        "--request-timeout",
        type=positive_duration,
        default="30s",
        help="ordinary HTTP request timeout",
    )
    parser.add_argument(
        "--sse-timeout",
        type=positive_duration,
        default="45s",
        help="SSE socket timeout; booth keepalives normally arrive every 15s",
    )
    parser.add_argument(
        "--run-timeout",
        type=positive_duration,
        default="20m",
        help="local limit before asking the booth to cancel an owned run",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="retries for safe GETs and artifact downloads",
    )
    parser.add_argument(
        "--max-artifact-mib",
        type=int,
        default=100,
        help="maximum bytes to download per artifact, in MiB",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification (test environments only)",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute the soak harness."""

    if args.retries < 0:
        raise HarnessError("--retries cannot be negative")
    if args.max_artifact_mib < 1:
        raise HarnessError("--max-artifact-mib must be at least 1")
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path("soak-results") / timestamp
    store = ResultStore(output, args.resume)

    if args.resume:
        manifest = store.load_manifest()
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise HarnessError(
                "unsupported manifest schema version: "
                f"{manifest.get('schema_version')!r}"
            )
        workloads = manifest.get("workloads")
        if not isinstance(workloads, list) or not workloads:
            raise HarnessError("saved manifest has no workload matrix")
        if args.workloads:
            log("--workloads is ignored during resume; using saved matrix")
        origin = (
            args.origin
            or str(manifest.get("origin") or "")
            or os.getenv("BOOTH_ORIGIN")
            or DEFAULT_ORIGIN
        ).rstrip("/")
        deadline = parse_iso(manifest.get("deadline_at"))
        if deadline is None:
            raise HarnessError("saved manifest has an invalid deadline_at")
        manifest["resume_count"] = int(manifest.get("resume_count") or 0) + 1
        manifest.setdefault("resumed_at", []).append(iso_now())
        manifest["status"] = "running"
        store.write_manifest(manifest)
    else:
        workloads = load_workloads(args.workloads)
        origin = (
            args.origin or os.getenv("BOOTH_ORIGIN") or DEFAULT_ORIGIN
        ).rstrip("/")
        started = utc_now()
        deadline = started + timedelta(seconds=args.duration)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "harness_version": HARNESS_VERSION,
            "status": "running",
            "created_at": started.isoformat(),
            "deadline_at": deadline.isoformat(),
            "duration_seconds": args.duration,
            "interval_seconds": args.interval,
            "poll_interval_seconds": args.poll_interval,
            "origin": origin,
            "workloads": workloads,
            "workload_count": len(workloads),
            "host": {
                "hostname": platform.node(),
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "invocation": {
                "argv": sys.argv,
                "cwd": str(Path.cwd()),
            },
        }
        store.write_manifest(manifest)

    client = BoothClient(
        origin,
        timeout=args.request_timeout,
        retries=args.retries,
        retry_interval=args.poll_interval,
        insecure=args.insecure,
    )
    install_signal_handlers()
    store.journal(
        "soak.started" if not args.resume else "soak.resumed",
        origin=origin,
        deadline_at=deadline.isoformat(),
    )
    log(
        f"soak output: {store.output}; origin: {origin}; "
        f"deadline: {deadline.isoformat()}"
    )

    if not args.resume:
        config_probe = probe_api(
            client,
            store,
            "config-start",
            "/api/config",
        )
        probe_api(client, store, "system-start", "/api/system")
        if config_probe.get("ok"):
            limits = (config_probe.get("body") or {}).get("limits") or {}
            max_chars = int(limits.get("max_prompt_chars") or 4000)
            for workload in workloads:
                if len(workload["prompt"]) > max_chars:
                    raise HarnessError(
                        f"workload {workload['id']} exceeds booth prompt "
                        f"limit of {max_chars} characters"
                    )

    recover_incomplete_attempts(
        client,
        store,
        deadline=deadline,
        poll_interval=args.poll_interval,
        sse_timeout=args.sse_timeout,
        run_timeout=args.run_timeout,
        max_artifact_bytes=args.max_artifact_mib * 1024 * 1024,
        retries=args.retries,
        retry_interval=args.poll_interval,
    )

    sequence, matrix_index = next_sequence_and_index(store, len(workloads))
    while utc_now() < deadline and not STOP_EVENT.is_set():
        workload = workloads[matrix_index]
        directory, attempt = store.create_attempt(
            sequence,
            matrix_index,
            workload,
        )
        run_id = submit_attempt(
            client,
            store,
            directory,
            attempt,
            deadline,
            args.poll_interval,
        )
        if run_id:
            collect_attempt(
                client,
                store,
                directory,
                attempt,
                poll_interval=args.poll_interval,
                sse_timeout=args.sse_timeout,
                run_timeout=args.run_timeout,
                max_artifact_bytes=args.max_artifact_mib * 1024 * 1024,
                retries=args.retries,
                retry_interval=args.poll_interval,
            )
        sequence += 1
        matrix_index = (matrix_index + 1) % len(workloads)
        manifest["attempts"] = sequence - 1
        manifest["next_matrix_index"] = matrix_index
        store.write_manifest(manifest)
        if utc_now() < deadline and not STOP_EVENT.is_set():
            remaining = max(0.0, (deadline - utc_now()).total_seconds())
            responsive_wait(min(args.interval, remaining))

    probe_api(client, store, "config-end", "/api/config")
    probe_api(client, store, "system-end", "/api/system")
    probe_api(client, store, "health-end", "/healthz")
    manifest["status"] = "interrupted" if STOP_EVENT.is_set() else "completed"
    manifest["finished_at"] = iso_now()
    manifest["attempts"] = len(store.attempt_directories())
    store.write_manifest(manifest)
    store.journal(
        "soak.finished",
        status=manifest["status"],
        attempts=manifest["attempts"],
    )
    log(
        f"soak {manifest['status']}; analyze with: "
        f"python3 {Path(__file__).with_name('analyze-soak.py')} "
        f"{store.output}"
    )
    return 130 if STOP_EVENT.is_set() else 0


def main() -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (HarnessError, OSError, json.JSONDecodeError) as exc:
        print(f"soak.py: error: {compact_error(exc, 2000)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Summarize an AMD booth soak directory produced by soak.py.

The analyzer is dependency-free and safe to run while a soak is still active.
It tolerates partial attempt directories and truncated JSONL tails, preferring
final run metrics while using captured route events for model, decision,
latency, cached-token, cloud-token, and quality detail.

Examples:

    python3 deploy/analyze-soak.py soak-results/booth-4h
    python3 deploy/analyze-soak.py soak-results/booth-4h --json
    python3 deploy/analyze-soak.py soak-results/booth-4h \
      --write-json soak-results/booth-4h/summary.json

The text report covers run and workload outcomes, route/model distribution,
route and end-to-end latency, token use, estimated cloud API cost, all-Kimi
and all-GLM counterfactuals, savings, failures, artifact capture, and workload
quality checks declared in the saved matrix.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class AnalysisError(RuntimeError):
    """An actionable problem with a soak result directory."""


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON, returning a default when the file is absent."""

    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read object records while tolerating a truncated final line."""

    records: list[dict[str, Any]] = []
    malformed = 0
    if not path.is_file():
        return records, malformed
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                malformed += 1
    return records, malformed


def deduplicate_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate replayed SSE events by sequence or canonical JSON."""

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for event in events:
        if event.get("seq") is not None:
            key = f"seq:{event['seq']}"
        else:
            key = json.dumps(
                event,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        if key not in seen:
            seen.add(key)
            result.append(event)
    return result


def number(value: Any, default: float = 0.0) -> float:
    """Convert numeric JSON values without propagating bad telemetry."""

    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def integer(value: Any, default: int = 0) -> int:
    """Convert a numeric JSON value to an integer."""

    return int(number(value, float(default)))


def parse_time(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def nearest_rank(values: Iterable[float], percentile: float) -> float | None:
    """Return a nearest-rank percentile."""

    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return None
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def distribution(values: Iterable[float]) -> dict[str, Any]:
    """Return concise descriptive statistics."""

    samples = [value for value in values if math.isfinite(value)]
    if not samples:
        return {
            "count": 0,
            "mean": None,
            "p50": None,
            "p95": None,
            "max": None,
        }
    return {
        "count": len(samples),
        "mean": statistics.fmean(samples),
        "p50": nearest_rank(samples, 50),
        "p95": nearest_rank(samples, 95),
        "max": max(samples),
    }


def money(value: float | None) -> str:
    """Format a small USD amount without hiding sub-cent costs."""

    if value is None:
        return "n/a"
    if abs(value) < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


def percent(numerator: float, denominator: float) -> float | None:
    """Return a percentage, or None for a zero denominator."""

    if denominator <= 0:
        return None
    return numerator / denominator * 100.0


def format_percent(value: float | None) -> str:
    """Format an optional percentage."""

    return "n/a" if value is None else f"{value:.1f}%"


def format_seconds(value: float | None) -> str:
    """Format an optional duration compactly."""

    if value is None:
        return "n/a"
    if value < 1:
        return f"{value * 1000:.0f}ms"
    if value < 60:
        return f"{value:.2f}s"
    minutes, seconds = divmod(value, 60)
    if minutes < 60:
        return f"{int(minutes)}m{seconds:04.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h{int(minutes):02d}m"


def compact(value: Any, limit: int = 160) -> str:
    """Render one bounded report line."""

    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        try:
            text = " ".join(json.dumps(value, ensure_ascii=False).split())
        except (TypeError, ValueError):
            text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def artifact_matches(path: str, pattern: str) -> bool:
    """Match artifact paths using shell or pathlib glob behavior."""

    normalized = path.replace("\\", "/")
    return fnmatch.fnmatchcase(normalized, pattern) or PurePosixPath(
        normalized
    ).match(pattern)


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    """Render a compact aligned text table."""

    rendered = [[str(cell) for cell in row] for row in rows]
    widths = [
        max(
            len(headers[index]),
            *(len(row[index]) for row in rendered),
        )
        for index in range(len(headers))
    ]
    result = [
        "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(headers)
        ),
        "  ".join("-" * width for width in widths),
    ]
    result.extend(
        "  ".join(
            cell.ljust(widths[index])
            for index, cell in enumerate(row)
        )
        for row in rendered
    )
    return result


def model_is_cloud(model: str, info: dict[str, Any]) -> bool:
    """Classify a model as externally billed cloud capacity."""

    tier = str(info.get("tier") or "").lower()
    if tier in {"cloud", "premium"}:
        return True
    if tier == "local":
        return False
    if number(info.get("input_rate")) or number(info.get("output_rate")):
        return True
    return not model.lower().startswith("qwen/")


def usage_from_event(event: dict[str, Any]) -> dict[str, int]:
    """Normalize one route event's usage object."""

    usage = event.get("usage") or {}
    return {
        "prompt_tokens": integer(usage.get("prompt_tokens")),
        "completion_tokens": integer(usage.get("completion_tokens")),
        "cached_tokens": integer(usage.get("cached_tokens")),
        "reasoning_tokens": integer(usage.get("reasoning_tokens")),
    }


def is_model_route(event: dict[str, Any]) -> bool:
    """Return false for router-only fast responses such as the safety guard."""

    decision = str(event.get("decision") or "").lower()
    model = str(event.get("model") or "").lower()
    return decision != "guard" and "safety guard" not in model


def cost_for_model(
    info: dict[str, Any],
    usage: dict[str, int],
) -> float:
    """Calculate token cost from saved per-million-token rates."""

    prompt = usage["prompt_tokens"]
    cached = min(prompt, usage["cached_tokens"])
    uncached = max(0, prompt - cached)
    return (
        uncached * number(info.get("input_rate"))
        + cached * number(info.get("cached_rate"))
        + usage["completion_tokens"] * number(info.get("output_rate"))
    ) / 1_000_000


def quality_checks(
    attempt: dict[str, Any],
    run: dict[str, Any],
    events: list[dict[str, Any]],
    artifact_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate workload expectations saved by soak.py."""

    workload = attempt.get("workload") or {}
    quality = workload.get("quality") or {}
    if not isinstance(quality, dict):
        quality = {}
    status = str(run.get("status") or attempt.get("status") or "unknown")
    metrics = run.get("metrics") or {}
    route_events = [
        event for event in events if event.get("type") == "route.selected"
    ]
    model_route_events = [
        event for event in route_events if is_model_route(event)
    ]
    tool_events = [
        event for event in events if event.get("type") == "tool.call"
    ]
    agents = {
        str(event["agent"])
        for event in events
        if isinstance(event.get("agent"), str) and event["agent"]
    }
    result = str(run.get("result") or "")
    remote_artifacts = [
        artifact
        for artifact in (run.get("artifacts") or [])
        if isinstance(artifact, dict)
    ]
    artifact_paths = [
        str(artifact.get("path") or artifact.get("name") or "")
        for artifact in remote_artifacts
    ]
    model_calls = integer(metrics.get("calls"), len(model_route_events))
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "observed": observed,
                "expected": expected,
            }
        )

    add("run_completed", status == "completed", status, "completed")
    if "min_result_chars" in quality:
        expected = integer(quality["min_result_chars"])
        add(
            "result_chars",
            len(result.strip()) >= expected,
            len(result.strip()),
            f">={expected}",
        )
    if "min_model_calls" in quality:
        expected = integer(quality["min_model_calls"])
        add(
            "model_calls",
            model_calls >= expected,
            model_calls,
            f">={expected}",
        )
    if "min_tool_calls" in quality:
        expected = integer(quality["min_tool_calls"])
        add(
            "tool_calls",
            len(tool_events) >= expected,
            len(tool_events),
            f">={expected}",
        )
    if "min_agents" in quality:
        expected = integer(quality["min_agents"])
        add(
            "distinct_agents",
            len(agents) >= expected,
            len(agents),
            f">={expected}",
        )
    if "min_artifacts" in quality:
        expected = integer(quality["min_artifacts"])
        add(
            "artifacts",
            len(remote_artifacts) >= expected,
            len(remote_artifacts),
            f">={expected}",
        )
    patterns = quality.get("artifact_globs") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    if isinstance(patterns, list):
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue
            add(
                f"artifact:{pattern}",
                any(
                    artifact_matches(path, pattern)
                    for path in artifact_paths
                ),
                ", ".join(artifact_paths) or "(none)",
                pattern,
            )
    required_text = quality.get("result_contains") or []
    if isinstance(required_text, str):
        required_text = [required_text]
    if isinstance(required_text, list):
        result_lower = result.lower()
        for marker in required_text:
            if isinstance(marker, str):
                add(
                    f"result_contains:{marker}",
                    marker.lower() in result_lower,
                    "present" if marker.lower() in result_lower else "absent",
                    marker,
                )

    # Capture completeness is operational telemetry, not a workload gate.
    if remote_artifacts:
        downloaded = sum(
            record.get("status") == "downloaded"
            for record in artifact_records
        )
        checks.append(
            {
                "name": "capture:artifacts_downloaded",
                "passed": downloaded == len(remote_artifacts),
                "observed": downloaded,
                "expected": len(remote_artifacts),
                "informational": True,
            }
        )
    llm_errors = sum(event.get("type") == "llm.error" for event in events)
    checks.append(
        {
            "name": "capture:no_llm_errors",
            "passed": llm_errors == 0,
            "observed": llm_errors,
            "expected": 0,
            "informational": True,
        }
    )
    return checks


def analyze_attempt(
    directory: Path,
    model_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Load and normalize one attempt directory."""

    attempt = read_json(directory / "attempt.json", {})
    if not isinstance(attempt, dict):
        attempt = {}
    run = read_json(directory / "run.json")
    if not isinstance(run, dict):
        run = read_json(directory / "run.latest.json", {})
    if not isinstance(run, dict):
        run = {}
    events_raw, malformed_events = read_jsonl(directory / "events.jsonl")
    events = deduplicate_events(events_raw)
    artifact_records = read_json(directory / "artifacts.json", [])
    if not isinstance(artifact_records, list):
        artifact_records = []

    metrics = run.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    route_events = [
        event for event in events if event.get("type") == "route.selected"
    ]
    model_route_events = [
        event for event in route_events if is_model_route(event)
    ]
    event_model_counts: Counter[str] = Counter(
        str(event.get("model") or "unknown")
        for event in model_route_events
    )
    final_model_counts = metrics.get("model_counts") or {}
    if not isinstance(final_model_counts, dict):
        final_model_counts = {}

    model_rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost": 0.0,
            "latencies": [],
            "tier": "unknown",
        }
    )
    event_token_totals = Counter()
    for event in model_route_events:
        model = str(event.get("model") or "unknown")
        usage = usage_from_event(event)
        info = event.get("model_info") or model_catalog.get(model, {})
        if not isinstance(info, dict):
            info = {}
        row = model_rows[model]
        row["calls"] += 1
        row["tier"] = str(info.get("tier") or row["tier"])
        for key, value in usage.items():
            row[key] += value
            event_token_totals[key] += value
        latency = number(event.get("latency_seconds"), -1.0)
        if latency >= 0:
            row["latencies"].append(latency)
        row["estimated_cost"] += number(
            event.get("estimated_cost"),
            cost_for_model(info, usage),
        )

    for model, count_value in final_model_counts.items():
        model_name = str(model)
        final_count = integer(count_value)
        missing = max(0, final_count - event_model_counts[model_name])
        model_rows[model_name]["calls"] += missing
        info = model_catalog.get(model_name, {})
        if isinstance(info, dict) and info.get("tier"):
            model_rows[model_name]["tier"] = str(info["tier"])

    metrics_present = bool(metrics)
    token_totals = {
        "prompt_tokens": (
            integer(metrics.get("prompt_tokens"))
            if metrics_present
            else event_token_totals["prompt_tokens"]
        ),
        "completion_tokens": (
            integer(metrics.get("completion_tokens"))
            if metrics_present
            else event_token_totals["completion_tokens"]
        ),
        "cached_tokens": event_token_totals["cached_tokens"],
        "reasoning_tokens": (
            integer(metrics.get("reasoning_tokens"))
            if metrics_present
            else event_token_totals["reasoning_tokens"]
        ),
    }
    actual_cost = (
        number(metrics.get("actual_cost"))
        if "actual_cost" in metrics
        else sum(
            number(event.get("estimated_cost"))
            for event in model_route_events
        )
    )
    all_kimi_cost = (
        number(metrics.get("all_kimi_cost"))
        if "all_kimi_cost" in metrics
        else None
    )
    all_glm_cost = (
        number(metrics.get("all_glm_cost"))
        if "all_glm_cost" in metrics
        else None
    )
    status = str(run.get("status") or attempt.get("status") or "unknown")
    workload = attempt.get("workload") or {}
    if not isinstance(workload, dict):
        workload = {}

    started = next(
        (
            parse_time(event.get("timestamp"))
            for event in events
            if event.get("type") == "run.started"
        ),
        None,
    )
    ended = next(
        (
            parse_time(event.get("timestamp"))
            for event in reversed(events)
            if event.get("type")
            in {"run.completed", "run.failed", "run.cancelled"}
        ),
        None,
    )
    started = started or parse_time(attempt.get("submitted_at"))
    ended = ended or parse_time(attempt.get("finished_at"))
    run_seconds = (
        max(0.0, (ended - started).total_seconds())
        if started and ended
        else None
    )

    checks = quality_checks(
        attempt,
        run,
        events,
        artifact_records,
    )
    gating_checks = [
        check for check in checks if not check.get("informational")
    ]
    quality_pass = bool(gating_checks) and all(
        check["passed"] for check in gating_checks
    )
    remote_artifacts = [
        artifact
        for artifact in (run.get("artifacts") or [])
        if isinstance(artifact, dict)
    ]
    downloaded_artifacts = sum(
        record.get("status") == "downloaded"
        for record in artifact_records
    )
    artifact_failures = sum(
        record.get("status") == "failed"
        for record in artifact_records
    )
    llm_errors = [
        event for event in events if event.get("type") == "llm.error"
    ]
    route_latencies = [
        number(event.get("latency_seconds"))
        for event in route_events
        if number(event.get("latency_seconds"), -1) >= 0
    ]
    decisions = Counter(
        str(event.get("decision") or "default")
        for event in route_events
    )
    efforts = Counter(
        str(event.get("effort") or "unknown")
        for event in route_events
    )
    agents = Counter(
        str(event.get("agent") or "unknown")
        for event in route_events
    )

    error_text = str(run.get("error") or "")
    if not error_text:
        errors = attempt.get("errors") or []
        if errors and isinstance(errors[-1], dict):
            error_text = str(errors[-1].get("error") or "")

    return {
        "directory": str(directory),
        "sequence": integer(attempt.get("sequence")),
        "run_id": attempt.get("run_id") or run.get("id"),
        "workload_id": str(workload.get("id") or "unknown"),
        "title": str(workload.get("title") or attempt.get("title") or ""),
        "state": str(attempt.get("state") or "unknown"),
        "status": status,
        "error": compact(error_text, 500),
        "events": len(events),
        "malformed_event_lines": malformed_events,
        "route_events": len(route_events),
        "tool_calls": sum(
            event.get("type") == "tool.call" for event in events
        ),
        "llm_errors": len(llm_errors),
        "route_latencies": route_latencies,
        "run_seconds": run_seconds,
        "decisions": dict(decisions),
        "efforts": dict(efforts),
        "agents": dict(agents),
        "model_rows": dict(model_rows),
        "tokens": token_totals,
        "actual_cost": actual_cost,
        "all_kimi_cost": all_kimi_cost,
        "all_glm_cost": all_glm_cost,
        "remote_artifacts": len(remote_artifacts),
        "downloaded_artifacts": downloaded_artifacts,
        "artifact_failures": artifact_failures,
        "attempt_errors": len(attempt.get("errors") or []),
        "quality_checks": checks,
        "quality_pass": quality_pass,
    }


def load_model_catalog(root: Path) -> dict[str, dict[str, Any]]:
    """Load the model metadata captured at soak start."""

    probe = read_json(root / "config-start.json", {})
    if not isinstance(probe, dict):
        return {}
    body = probe.get("body") or {}
    if not isinstance(body, dict):
        return {}
    models = body.get("models") or {}
    if not isinstance(models, dict):
        return {}
    return {
        str(model): info
        for model, info in models.items()
        if isinstance(info, dict)
    }


def build_summary(root: Path) -> dict[str, Any]:
    """Analyze a soak result directory into a JSON-serializable summary."""

    manifest = read_json(root / "manifest.json")
    if not isinstance(manifest, dict):
        raise AnalysisError(f"missing or invalid {root / 'manifest.json'}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise AnalysisError(
            "unsupported manifest schema version: "
            f"{manifest.get('schema_version')!r}"
        )
    attempts_root = root / "attempts"
    attempt_directories = (
        sorted(
            path
            for path in attempts_root.iterdir()
            if path.is_dir() and (path / "attempt.json").is_file()
        )
        if attempts_root.is_dir()
        else []
    )
    model_catalog = load_model_catalog(root)
    attempts = [
        analyze_attempt(directory, model_catalog)
        for directory in attempt_directories
    ]

    statuses = Counter(attempt["status"] for attempt in attempts)
    states = Counter(attempt["state"] for attempt in attempts)
    completed = statuses["completed"]
    terminal = sum(
        count for status, count in statuses.items()
        if status in TERMINAL_STATUSES
    )
    incomplete = len(attempts) - terminal
    route_latencies: list[float] = []
    run_durations: list[float] = []
    decisions: Counter[str] = Counter()
    efforts: Counter[str] = Counter()
    agents: Counter[str] = Counter()
    model_rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost": 0.0,
            "latencies": [],
            "tier": "unknown",
        }
    )
    token_totals = Counter()
    cloud_tokens = Counter()
    actual_cost = 0.0
    all_kimi_cost = 0.0
    all_glm_cost = 0.0
    actual_cost_kimi_covered = 0.0
    actual_cost_glm_covered = 0.0
    kimi_coverage = 0
    glm_coverage = 0
    workload_rows: dict[str, Counter[str]] = defaultdict(Counter)
    quality_signals: dict[str, Counter[str]] = defaultdict(Counter)
    failures: list[dict[str, Any]] = []
    total_events = 0
    malformed_event_lines = 0
    llm_errors = 0
    attempt_errors = 0
    remote_artifacts = 0
    downloaded_artifacts = 0
    artifact_failures = 0

    for attempt in attempts:
        route_latencies.extend(attempt["route_latencies"])
        if attempt["run_seconds"] is not None:
            run_durations.append(attempt["run_seconds"])
        decisions.update(attempt["decisions"])
        efforts.update(attempt["efforts"])
        agents.update(attempt["agents"])
        for model, source in attempt["model_rows"].items():
            target = model_rows[model]
            for key in (
                "calls",
                "prompt_tokens",
                "completion_tokens",
                "cached_tokens",
                "reasoning_tokens",
            ):
                target[key] += source[key]
            target["estimated_cost"] += source["estimated_cost"]
            target["latencies"].extend(source["latencies"])
            if source.get("tier") and source["tier"] != "unknown":
                target["tier"] = source["tier"]
        token_totals.update(attempt["tokens"])
        actual_cost += attempt["actual_cost"]
        if attempt["all_kimi_cost"] is not None:
            all_kimi_cost += attempt["all_kimi_cost"]
            actual_cost_kimi_covered += attempt["actual_cost"]
            kimi_coverage += 1
        if attempt["all_glm_cost"] is not None:
            all_glm_cost += attempt["all_glm_cost"]
            actual_cost_glm_covered += attempt["actual_cost"]
            glm_coverage += 1
        workload = workload_rows[attempt["workload_id"]]
        workload["attempts"] += 1
        workload[attempt["status"]] += 1
        workload["quality_pass"] += int(attempt["quality_pass"])
        for check in attempt["quality_checks"]:
            signal = quality_signals[check["name"]]
            signal["evaluated"] += 1
            signal["passed"] += int(check["passed"])
            if check.get("informational"):
                signal["informational"] += 1

        total_events += attempt["events"]
        malformed_event_lines += attempt["malformed_event_lines"]
        llm_errors += attempt["llm_errors"]
        attempt_errors += attempt["attempt_errors"]
        remote_artifacts += attempt["remote_artifacts"]
        downloaded_artifacts += attempt["downloaded_artifacts"]
        artifact_failures += attempt["artifact_failures"]

        failed_checks = [
            check["name"]
            for check in attempt["quality_checks"]
            if not check["passed"] and not check.get("informational")
        ]
        if (
            attempt["status"] != "completed"
            or failed_checks
            or attempt["llm_errors"]
            or attempt["artifact_failures"]
        ):
            failures.append(
                {
                    "sequence": attempt["sequence"],
                    "workload_id": attempt["workload_id"],
                    "run_id": attempt["run_id"],
                    "status": attempt["status"],
                    "error": attempt["error"],
                    "failed_quality_checks": failed_checks,
                    "llm_errors": attempt["llm_errors"],
                    "artifact_failures": attempt["artifact_failures"],
                }
            )

    for model, row in model_rows.items():
        info = model_catalog.get(model, {})
        is_cloud = model_is_cloud(model, info or {"tier": row["tier"]})
        row["cloud"] = is_cloud
        if is_cloud:
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "cached_tokens",
                "reasoning_tokens",
            ):
                cloud_tokens[key] += row[key]

    created_at = parse_time(manifest.get("created_at"))
    finished_at = parse_time(manifest.get("finished_at"))
    observed_end = finished_at or datetime.now(timezone.utc)
    observed_seconds = (
        max(0.0, (observed_end - created_at).total_seconds())
        if created_at
        else None
    )
    quality_passes = sum(attempt["quality_pass"] for attempt in attempts)
    total_calls = sum(row["calls"] for row in model_rows.values())
    cloud_calls = sum(
        row["calls"] for row in model_rows.values() if row["cloud"]
    )
    cloud_total_tokens = (
        cloud_tokens["prompt_tokens"] + cloud_tokens["completion_tokens"]
    )
    savings_kimi = (
        all_kimi_cost - actual_cost_kimi_covered
        if kimi_coverage
        else None
    )
    savings_glm = (
        all_glm_cost - actual_cost_glm_covered
        if glm_coverage
        else None
    )

    normalized_models: dict[str, Any] = {}
    for model, row in sorted(
        model_rows.items(),
        key=lambda item: (-item[1]["calls"], item[0]),
    ):
        info = model_catalog.get(model, {})
        normalized_models[model] = {
            **{
                key: row[key]
                for key in (
                    "calls",
                    "prompt_tokens",
                    "completion_tokens",
                    "cached_tokens",
                    "reasoning_tokens",
                    "estimated_cost",
                    "tier",
                    "cloud",
                )
            },
            "label": str(info.get("label") or model),
            "call_share_percent": percent(row["calls"], total_calls),
            "latency_seconds": distribution(row["latencies"]),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "source": str(root),
        "manifest": {
            "status": manifest.get("status"),
            "origin": manifest.get("origin"),
            "created_at": manifest.get("created_at"),
            "deadline_at": manifest.get("deadline_at"),
            "finished_at": manifest.get("finished_at"),
            "duration_seconds": manifest.get("duration_seconds"),
            "observed_seconds": observed_seconds,
        },
        "runs": {
            "attempts": len(attempts),
            "terminal": terminal,
            "completed": completed,
            "failed": statuses["failed"],
            "cancelled": statuses["cancelled"],
            "incomplete": incomplete,
            "success_percent": percent(completed, len(attempts)),
            "quality_passes": quality_passes,
            "quality_pass_percent": percent(quality_passes, len(attempts)),
            "statuses": dict(sorted(statuses.items())),
            "states": dict(sorted(states.items())),
            "throughput_completed_per_hour": (
                completed / (observed_seconds / 3600)
                if observed_seconds and observed_seconds > 0
                else None
            ),
        },
        "routing": {
            "route_selections": sum(decisions.values()),
            "calls": total_calls,
            "cloud_calls": cloud_calls,
            "local_calls": total_calls - cloud_calls,
            "models": normalized_models,
            "decisions": dict(decisions.most_common()),
            "efforts": dict(efforts.most_common()),
            "agents": dict(agents.most_common()),
        },
        "latency_seconds": {
            "route_calls": distribution(route_latencies),
            "runs": distribution(run_durations),
        },
        "tokens": {
            "prompt_tokens": token_totals["prompt_tokens"],
            "completion_tokens": token_totals["completion_tokens"],
            "cached_tokens": token_totals["cached_tokens"],
            "reasoning_tokens": token_totals["reasoning_tokens"],
            "total_tokens": (
                token_totals["prompt_tokens"]
                + token_totals["completion_tokens"]
            ),
            "cloud_prompt_tokens_captured": cloud_tokens["prompt_tokens"],
            "cloud_completion_tokens_captured": cloud_tokens[
                "completion_tokens"
            ],
            "cloud_cached_tokens_captured": cloud_tokens["cached_tokens"],
            "cloud_reasoning_tokens_captured": cloud_tokens[
                "reasoning_tokens"
            ],
            "cloud_total_tokens_captured": cloud_total_tokens,
        },
        "costs_usd": {
            "actual_cloud_api": actual_cost,
            "all_kimi": all_kimi_cost if kimi_coverage else None,
            "all_glm": all_glm_cost if glm_coverage else None,
            "all_kimi_coverage_attempts": kimi_coverage,
            "all_glm_coverage_attempts": glm_coverage,
            "savings_vs_kimi": savings_kimi,
            "savings_vs_kimi_percent": (
                percent(savings_kimi, all_kimi_cost)
                if savings_kimi is not None
                else None
            ),
            "savings_vs_glm": savings_glm,
            "savings_vs_glm_percent": (
                percent(savings_glm, all_glm_cost)
                if savings_glm is not None
                else None
            ),
            "effective_per_million_captured_cloud_tokens": (
                actual_cost / cloud_total_tokens * 1_000_000
                if cloud_total_tokens > 0
                else None
            ),
        },
        "quality": {
            "signals": {
                name: dict(counts)
                for name, counts in sorted(quality_signals.items())
            },
            "workloads": {
                name: dict(counts)
                for name, counts in sorted(workload_rows.items())
            },
        },
        "capture": {
            "events": total_events,
            "malformed_event_lines": malformed_event_lines,
            "attempt_errors": attempt_errors,
            "llm_errors": llm_errors,
            "remote_artifacts": remote_artifacts,
            "downloaded_artifacts": downloaded_artifacts,
            "artifact_failures": artifact_failures,
        },
        "failures": failures,
    }


def render_text(summary: dict[str, Any], max_failures: int) -> str:
    """Render a concise human-readable report."""

    manifest = summary["manifest"]
    runs = summary["runs"]
    routing = summary["routing"]
    latency = summary["latency_seconds"]
    tokens = summary["tokens"]
    costs = summary["costs_usd"]
    quality = summary["quality"]
    capture = summary["capture"]
    lines = [
        "AMD booth soak analysis",
        f"Source: {summary['source']}",
        (
            f"Window: {manifest.get('created_at') or 'unknown'} -> "
            f"{manifest.get('finished_at') or 'in progress'} "
            f"({format_seconds(manifest.get('observed_seconds'))} observed; "
            f"manifest status {manifest.get('status') or 'unknown'})"
        ),
        (
            f"Runs: {runs['attempts']} attempts, {runs['completed']} completed, "
            f"{runs['failed']} failed, {runs['cancelled']} cancelled, "
            f"{runs['incomplete']} incomplete; success "
            f"{format_percent(runs['success_percent'])}; quality "
            f"{runs['quality_passes']}/{runs['attempts']} "
            f"({format_percent(runs['quality_pass_percent'])})"
        ),
    ]
    if runs["throughput_completed_per_hour"] is not None:
        lines.append(
            "Throughput: "
            f"{runs['throughput_completed_per_hour']:.2f} completed runs/hour"
        )

    lines.extend(["", "Model distribution"])
    model_rows: list[list[Any]] = []
    for model, row in routing["models"].items():
        model_rows.append(
            [
                row["label"],
                row["tier"],
                row["calls"],
                format_percent(row["call_share_percent"]),
                row["prompt_tokens"],
                row["completion_tokens"],
                money(row["estimated_cost"]),
                format_seconds(row["latency_seconds"]["p50"]),
                format_seconds(row["latency_seconds"]["p95"]),
            ]
        )
    if model_rows:
        lines.extend(
            table(
                [
                    "Model",
                    "Tier",
                    "Calls",
                    "Share",
                    "Input",
                    "Output",
                    "Route cost",
                    "p50",
                    "p95",
                ],
                model_rows,
            )
        )
    else:
        lines.append("(no route telemetry captured)")

    lines.extend(["", "Routing"])
    lines.append(
        f"Route selections: {routing['route_selections']}; model calls: "
        f"{routing['calls']} total, {routing['local_calls']} local, "
        f"{routing['cloud_calls']} cloud"
    )
    if routing["decisions"]:
        lines.append(
            "Decisions: "
            + ", ".join(
                f"{name}={count}"
                for name, count in routing["decisions"].items()
            )
        )
    if routing["efforts"]:
        lines.append(
            "Effort: "
            + ", ".join(
                f"{name}={count}"
                for name, count in routing["efforts"].items()
            )
        )
    if routing["agents"]:
        lines.append(
            "Agents: "
            + ", ".join(
                f"{name}={count}"
                for name, count in routing["agents"].items()
            )
        )

    route_latency = latency["route_calls"]
    run_latency = latency["runs"]
    lines.extend(
        [
            "",
            "Latency",
            (
                f"Route calls ({route_latency['count']}): mean "
                f"{format_seconds(route_latency['mean'])}, p50 "
                f"{format_seconds(route_latency['p50'])}, p95 "
                f"{format_seconds(route_latency['p95'])}, max "
                f"{format_seconds(route_latency['max'])}"
            ),
            (
                f"End-to-end runs ({run_latency['count']}): mean "
                f"{format_seconds(run_latency['mean'])}, p50 "
                f"{format_seconds(run_latency['p50'])}, p95 "
                f"{format_seconds(run_latency['p95'])}, max "
                f"{format_seconds(run_latency['max'])}"
            ),
        ]
    )

    lines.extend(
        [
            "",
            "Tokens and cloud API cost",
            (
                f"Tokens: {tokens['prompt_tokens']} input "
                f"({tokens['cached_tokens']} cached captured), "
                f"{tokens['completion_tokens']} output, "
                f"{tokens['reasoning_tokens']} reasoning; "
                f"{tokens['total_tokens']} input+output"
            ),
            (
                "Captured cloud-route tokens: "
                f"{tokens['cloud_prompt_tokens_captured']} input, "
                f"{tokens['cloud_completion_tokens_captured']} output "
                f"({tokens['cloud_total_tokens_captured']} total)"
            ),
            (
                f"Actual estimated cloud API cost: "
                f"{money(costs['actual_cloud_api'])}; effective "
                f"{money(costs['effective_per_million_captured_cloud_tokens'])}"
                " per 1M captured cloud tokens"
            ),
            (
                f"All-Kimi counterfactual: {money(costs['all_kimi'])}; "
                f"savings {money(costs['savings_vs_kimi'])} "
                f"({format_percent(costs['savings_vs_kimi_percent'])})"
            ),
            (
                f"All-GLM counterfactual: {money(costs['all_glm'])}; "
                f"savings {money(costs['savings_vs_glm'])} "
                f"({format_percent(costs['savings_vs_glm_percent'])})"
            ),
        ]
    )

    lines.extend(["", "Workload quality"])
    workload_rows = []
    for workload, counts in quality["workloads"].items():
        workload_rows.append(
            [
                workload,
                counts.get("attempts", 0),
                counts.get("completed", 0),
                counts.get("quality_pass", 0),
                format_percent(
                    percent(
                        counts.get("quality_pass", 0),
                        counts.get("attempts", 0),
                    )
                ),
            ]
        )
    if workload_rows:
        lines.extend(
            table(
                ["Workload", "Runs", "Complete", "Quality", "Pass rate"],
                workload_rows,
            )
        )
    signal_failures = [
        (name, counts)
        for name, counts in quality["signals"].items()
        if counts.get("passed", 0) < counts.get("evaluated", 0)
    ]
    if signal_failures:
        lines.append(
            "Signals below 100%: "
            + ", ".join(
                f"{name}={counts.get('passed', 0)}/"
                f"{counts.get('evaluated', 0)}"
                for name, counts in signal_failures
            )
        )

    lines.extend(
        [
            "",
            "Reliability and capture",
            (
                f"Events: {capture['events']} captured, "
                f"{capture['malformed_event_lines']} malformed JSONL lines; "
                f"{capture['llm_errors']} LLM errors; "
                f"{capture['attempt_errors']} harness/API retry records"
            ),
            (
                f"Artifacts: {capture['downloaded_artifacts']}/"
                f"{capture['remote_artifacts']} downloaded; "
                f"{capture['artifact_failures']} capture failures"
            ),
        ]
    )
    failures = summary["failures"]
    if failures:
        lines.extend(["", f"Failures/quality misses ({len(failures)})"])
        for failure in failures[:max_failures]:
            details: list[str] = []
            if failure["error"]:
                details.append(failure["error"])
            if failure["failed_quality_checks"]:
                details.append(
                    "quality: "
                    + ", ".join(failure["failed_quality_checks"])
                )
            if failure["llm_errors"]:
                details.append(f"llm_errors={failure['llm_errors']}")
            if failure["artifact_failures"]:
                details.append(
                    f"artifact_failures={failure['artifact_failures']}"
                )
            lines.append(
                f"- #{failure['sequence']:05d} "
                f"{failure['workload_id']} [{failure['status']}]"
                + (": " + "; ".join(details) if details else "")
            )
        if len(failures) > max_failures:
            lines.append(
                f"- ... {len(failures) - max_failures} additional entries"
            )
    else:
        lines.extend(["", "Failures/quality misses: none"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Analyze an AMD booth soak output directory, including partial "
            "runs, route latency, token/cost savings, failures, and quality."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "output",
        type=Path,
        help="soak.py output directory containing manifest.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the complete machine-readable summary instead of text",
    )
    parser.add_argument(
        "--write-json",
        type=Path,
        help="also write the machine-readable summary to this path",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=10,
        help="maximum failure/quality-miss details in the text report",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "exit nonzero when a run failed, was incomplete, missed workload "
            "quality checks, or an artifact failed to download"
        ),
    )
    return parser


def main() -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()
    if args.max_failures < 0:
        parser.error("--max-failures cannot be negative")
    try:
        summary = build_summary(args.output.resolve())
    except (AnalysisError, OSError, json.JSONDecodeError) as exc:
        print(f"analyze-soak.py: error: {compact(exc, 2000)}", file=sys.stderr)
        return 2

    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        with args.write_json.open("w", encoding="utf-8") as handle:
            json.dump(
                summary,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            handle.write("\n")
    if args.json:
        json.dump(
            summary,
            sys.stdout,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
    else:
        print(render_text(summary, args.max_failures))

    if args.strict:
        runs = summary["runs"]
        capture = summary["capture"]
        if (
            runs["failed"]
            or runs["cancelled"]
            or runs["incomplete"]
            or runs["quality_passes"] != runs["attempts"]
            or capture["artifact_failures"]
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

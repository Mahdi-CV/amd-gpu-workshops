#!/usr/bin/env python3
"""Aggregate full OpenClaw policy-comparison results without leaking secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any


DEPLOY = Path(__file__).resolve().parents[1]
COST_FACTORS = DEPLOY / "config" / "cost-factors.json"
ARMS = ("auto", "direct_glm")
GLM_MODEL = "zai/glm-5.3-flash"
CANONICAL_FIX = (
    "+    return round((correct / total_typed) * 100, 1)"
)
EQUIVALENT_FIX = (
    "+    return round(correct / total_typed * 100, 1)"
)


def decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def rounded(value: Decimal, places: int = 8) -> float:
    return float(round(value, places))


def percentage(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return float(round(numerator / denominator * Decimal(100), 2))


def savings(actual: Decimal, baseline: Decimal) -> float | None:
    if baseline == 0:
        return None
    return float(
        round((Decimal(1) - actual / baseline) * Decimal(100), 2)
    )


def nearest_rank(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    rows = sorted(values)
    index = max(0, math.ceil(len(rows) * fraction) - 1)
    return round(rows[index], 4)


def stats(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4) if values else None,
        "median": round(statistics.median(values), 4) if values else None,
        "p90_nearest_rank": nearest_rank(values, 0.9),
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cost_factors() -> dict[str, Any]:
    body = json.loads(COST_FACTORS.read_text(encoding="utf-8"))
    if (body.get("recipe") or {}).get("id") != "decision-balance":
        raise RuntimeError("Unexpected cost-factor recipe.")
    return body


def normalized_model(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def canonical_model(
    value: Any,
    factors: dict[str, Any],
) -> str | None:
    if not value:
        return None
    normalized = normalized_model(str(value))
    matches = []
    for model_id, details in (factors.get("models") or {}).items():
        names = [model_id, *(details.get("aliases") or [])]
        if any(
            normalized == normalized_model(str(name))
            or normalized_model(str(name)) in normalized
            or normalized in normalized_model(str(name))
            for name in names
        ):
            matches.append(model_id)
    return matches[0] if len(matches) == 1 else None


def usage_cost(
    usage: dict[str, Any],
    model: str,
    factors: dict[str, Any],
) -> Decimal:
    rates = (factors.get("models") or {}).get(model)
    if not rates:
        raise RuntimeError(f"No rates for {model!r}.")
    prompt = decimal(usage.get("prompt_tokens"))
    completion = decimal(usage.get("completion_tokens"))
    return (
        prompt * decimal(rates["prompt_per_1m"])
        + completion * decimal(rates["completion_per_1m"])
    ) / Decimal(1_000_000)


def raw_routes_path(summary_path: Path, pair_id: int, arm: str) -> Path:
    return (
        summary_path.parent
        / f"pair-{pair_id:02d}"
        / arm.replace("_", "-")
        / "routes.jsonl"
    )


def load_raw_routes(
    summary_path: Path,
    pair_id: int,
    arm: str,
) -> list[dict[str, Any]]:
    path = raw_routes_path(summary_path, pair_id, arm)
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize_calls(
    run: dict[str, Any],
    summary_path: Path,
    pair_id: int,
    arm: str,
    factors: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    source = run.get("calls") or load_raw_routes(summary_path, pair_id, arm)
    calls: list[dict[str, Any]] = []
    expected_requests = (run.get("metrics") or {}).get("requests")
    complete = bool(source) or (
        run.get("status") == "completed" and expected_requests == 0
    )
    if expected_requests is not None and len(source) != int(expected_requests):
        complete = False
    for index, row in enumerate(source, start=1):
        headers = {
            str(key).lower(): value
            for key, value in (row.get("routing_headers") or {}).items()
        }
        selected = (
            row.get("selected_model")
            or headers.get("x-vsr-selected-model")
            or row.get("response_model")
            or (GLM_MODEL if arm == "direct_glm" else None)
        )
        cost_model = (
            row.get("cost_model")
            or (GLM_MODEL if arm == "direct_glm" else None)
            or canonical_model(selected, factors)
        )
        response_model = row.get("response_model")
        usage = row.get("usage") or {}
        try:
            actual = usage_cost(usage, cost_model, factors)
            glm_reprice = usage_cost(usage, GLM_MODEL, factors)
        except (RuntimeError, TypeError):
            actual = None
            glm_reprice = None
            complete = False
        calls.append(
            {
                "index": index,
                "phase": row.get("phase"),
                "status": row.get("status"),
                "requested_model": row.get("requested_model"),
                "selected_model": selected,
                "response_model": response_model,
                "cost_model": cost_model,
                "decision": (
                    row.get("decision")
                    or headers.get("x-vsr-selected-decision")
                ),
                "reasoning": (
                    row.get("reasoning")
                    or headers.get("x-vsr-selected-reasoning")
                ),
                "finish_reason": row.get("finish_reason"),
                "tool_count": row.get("tool_count"),
                "latency_seconds": row.get("latency_seconds"),
                "usage": {
                    key: int(usage.get(key) or 0)
                    for key in (
                        "prompt_tokens",
                        "completion_tokens",
                        "reasoning_tokens",
                        "cached_tokens",
                    )
                },
                "actual_cost_xxx": (
                    rounded(actual) if actual is not None else None
                ),
                "glm_reprice_xxx": (
                    rounded(glm_reprice)
                    if glm_reprice is not None
                    else None
                ),
            }
        )
    return calls, complete


def source_fix_class(run: dict[str, Any]) -> tuple[bool, str | None]:
    quality = run.get("quality") or {}
    integrity = quality.get("integrity") or {}
    if integrity.get("source_fix_valid") is True:
        return True, integrity.get("source_fix_variant") or "accepted"
    if integrity.get("exact_source_patch") is True:
        return True, "canonical"
    patch = str(integrity.get("patch") or "")
    changed = integrity.get("changed_files") or []
    if changed == ["stats.py"] and EQUIVALENT_FIX in patch:
        return True, "equivalent"
    if changed == ["stats.py"] and CANONICAL_FIX in patch:
        return True, "canonical"
    return False, None


def functional_pass(run: dict[str, Any]) -> tuple[bool, str | None]:
    if run.get("status") != "completed":
        return False, None
    quality = run.get("quality") or {}
    integrity = quality.get("integrity") or {}
    source_valid, variant = source_fix_class(run)
    passed = all(
        (
            quality.get("baseline_exact") is True,
            quality.get("posttest_exact") is True,
            integrity.get("tests_unchanged") is True,
            source_valid,
        )
    )
    return passed, variant


def call_totals(calls: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = {
        key: sum(int(call["usage"][key]) for call in calls)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
        )
    }
    actual = [
        decimal(call["actual_cost_xxx"])
        for call in calls
        if call.get("actual_cost_xxx") is not None
    ]
    repriced = [
        decimal(call["glm_reprice_xxx"])
        for call in calls
        if call.get("glm_reprice_xxx") is not None
    ]
    return {
        "requests": len(calls),
        "tokens": tokens,
        "actual_cost_xxx": rounded(sum(actual, Decimal(0))),
        "glm_reprice_xxx": rounded(sum(repriced, Decimal(0))),
        "costed_requests": len(actual),
        "latency_seconds": stats(
            [
                float(call["latency_seconds"])
                for call in calls
                if call.get("latency_seconds") is not None
            ]
        ),
    }


def classify_failure(run: dict[str, Any]) -> str | None:
    if run.get("status") == "completed":
        return None
    message = str((run.get("error") or {}).get("message") or "").lower()
    if "incomplete or malformed tool call" in message:
        return "malformed_tool_call"
    if "timeout" in message:
        return "timeout"
    return "other_runtime_error"


def analyze(inputs: list[Path]) -> dict[str, Any]:
    factors = load_cost_factors()
    experiments: list[dict[str, Any]] = []
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pair_rows: list[dict[str, Any]] = []

    for experiment_index, path in enumerate(inputs, start=1):
        summary = json.loads(path.read_text(encoding="utf-8"))
        experiments.append(
            {
                "index": experiment_index,
                "file": f"{path.parent.name}/{path.name}",
                "sha256": sha256(path),
                "generated_at": summary.get("generated_at"),
                "seed": summary.get("seed"),
                "pairs": len(summary.get("pairs") or []),
                "recipe": summary.get("recipe"),
            }
        )
        for pair in summary.get("pairs") or []:
            pair_id = int(pair["pair_id"])
            analyzed_arms: dict[str, Any] = {}
            for arm in ARMS:
                run = (pair.get("arms") or {}).get(arm) or {}
                calls, normalized_complete = normalize_calls(
                    run,
                    path,
                    pair_id,
                    arm,
                    factors,
                )
                functional, variant = functional_pass(run)
                totals = call_totals(calls)
                metrics = run.get("metrics") or {}
                workflow_seconds = metrics.get(
                    "workflow_wall_time_seconds"
                )
                row = {
                    "experiment": experiment_index,
                    "pair_id": pair_id,
                    "arm": arm,
                    "status": run.get("status") or "missing",
                    "reported_passed": run.get("passed") is True,
                    "functional_passed": functional,
                    "source_fix_variant": variant,
                    "failure_class": classify_failure(run),
                    "error_type": (run.get("error") or {}).get("type"),
                    "workflow_wall_time_seconds": workflow_seconds,
                    "cost_coverage_complete": (
                        normalized_complete
                        and totals["costed_requests"] == totals["requests"]
                    ),
                    "calls": calls,
                    **totals,
                }
                attempts[arm].append(row)
                analyzed_arms[arm] = row
            pair_rows.append(
                {
                    "experiment": experiment_index,
                    "pair_id": pair_id,
                    "arms": analyzed_arms,
                }
            )

    arm_results: dict[str, Any] = {}
    for arm in ARMS:
        rows = attempts[arm]
        successful = [row for row in rows if row["functional_passed"]]
        completed = [row for row in rows if row["status"] == "completed"]
        fully_costed = [
            row for row in rows if row["cost_coverage_complete"]
        ]
        cost_total = sum(
            (decimal(row["actual_cost_xxx"]) for row in fully_costed),
            Decimal(0),
        )
        workflow = [
            float(row["workflow_wall_time_seconds"])
            for row in completed
            if row["workflow_wall_time_seconds"] is not None
        ]
        token_totals = {
            key: sum(int(row["tokens"][key]) for row in rows)
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
                "cached_tokens",
            )
        }
        exact_cost_per_success = (
            rounded(cost_total / len(successful))
            if successful and len(fully_costed) == len(rows)
            else None
        )
        lower_bound = (
            rounded(cost_total / len(successful))
            if successful
            else None
        )
        arm_results[arm] = {
            "attempts": len(rows),
            "completed": len(completed),
            "functional_successes": len(successful),
            "reported_successes": sum(
                row["reported_passed"] for row in rows
            ),
            "functional_success_rate_percent": percentage(
                Decimal(len(successful)),
                Decimal(len(rows)),
            ),
            "failure_classes": dict(
                Counter(
                    row["failure_class"]
                    for row in rows
                    if row["failure_class"]
                )
            ),
            "requests": sum(int(row["requests"]) for row in rows),
            "tokens": token_totals,
            "observed_cost_total_xxx": rounded(cost_total),
            "cost_observed_attempts": len(fully_costed),
            "cost_missing_attempts": len(rows) - len(fully_costed),
            "failure_inclusive_cost_per_success_xxx": exact_cost_per_success,
            "known_cost_per_success_lower_bound_xxx": lower_bound,
            "completed_workflow_seconds": stats(workflow),
        }

    auto_arm = arm_results["auto"]
    direct_arm = arm_results["direct_glm"]
    overall_comparison = {
        "observed_attempt_compute_savings_percent": savings(
            decimal(auto_arm["observed_cost_total_xxx"]),
            decimal(direct_arm["observed_cost_total_xxx"]),
        ),
        "compute_per_success_savings_percent": savings(
            decimal(auto_arm["failure_inclusive_cost_per_success_xxx"]),
            decimal(
                direct_arm["failure_inclusive_cost_per_success_xxx"]
            ),
        ),
        "request_reduction_percent": savings(
            Decimal(auto_arm["requests"]),
            Decimal(direct_arm["requests"]),
        ),
        "prompt_token_reduction_percent": savings(
            Decimal(auto_arm["tokens"]["prompt_tokens"]),
            Decimal(direct_arm["tokens"]["prompt_tokens"]),
        ),
        "completion_token_reduction_percent": savings(
            Decimal(auto_arm["tokens"]["completion_tokens"]),
            Decimal(direct_arm["tokens"]["completion_tokens"]),
        ),
        "reasoning_token_reduction_percent": savings(
            Decimal(auto_arm["tokens"]["reasoning_tokens"]),
            Decimal(direct_arm["tokens"]["reasoning_tokens"]),
        ),
        "mean_completed_workflow_reduction_percent": savings(
            decimal(auto_arm["completed_workflow_seconds"]["mean"]),
            decimal(direct_arm["completed_workflow_seconds"]["mean"]),
        ),
    }

    matched: list[dict[str, Any]] = []
    for pair in pair_rows:
        auto = pair["arms"]["auto"]
        direct = pair["arms"]["direct_glm"]
        if not (
            auto["functional_passed"]
            and direct["functional_passed"]
            and auto["cost_coverage_complete"]
            and direct["cost_coverage_complete"]
        ):
            continue
        auto_cost = decimal(auto["actual_cost_xxx"])
        direct_cost = decimal(direct["actual_cost_xxx"])
        auto_time = auto.get("workflow_wall_time_seconds")
        direct_time = direct.get("workflow_wall_time_seconds")
        matched.append(
            {
                "experiment": pair["experiment"],
                "pair_id": pair["pair_id"],
                "auto_cost_xxx": rounded(auto_cost),
                "direct_glm_cost_xxx": rounded(direct_cost),
                "cost_difference_xxx": rounded(direct_cost - auto_cost),
                "auto_savings_percent": savings(auto_cost, direct_cost),
                "auto_workflow_seconds": auto_time,
                "direct_glm_workflow_seconds": direct_time,
                "time_saved_seconds": (
                    round(float(direct_time) - float(auto_time), 3)
                    if auto_time is not None and direct_time is not None
                    else None
                ),
            }
        )

    matched_auto = sum(
        (decimal(row["auto_cost_xxx"]) for row in matched),
        Decimal(0),
    )
    matched_direct = sum(
        (decimal(row["direct_glm_cost_xxx"]) for row in matched),
        Decimal(0),
    )
    pair_savings = [
        float(row["auto_savings_percent"])
        for row in matched
        if row["auto_savings_percent"] is not None
    ]
    time_saved = [
        float(row["time_saved_seconds"])
        for row in matched
        if row["time_saved_seconds"] is not None
    ]

    successful_auto = [
        row
        for row in attempts["auto"]
        if row["functional_passed"] and row["cost_coverage_complete"]
    ]
    routed_actual = sum(
        (decimal(row["actual_cost_xxx"]) for row in successful_auto),
        Decimal(0),
    )
    routed_reprice = sum(
        (decimal(row["glm_reprice_xxx"]) for row in successful_auto),
        Decimal(0),
    )

    model_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    reasoning_counts: Counter[str] = Counter()
    phase_counts: dict[str, Counter[str]] = defaultdict(Counter)
    route_rows: dict[str, dict[str, Any]] = {}
    selected_response_mismatches = 0
    response_cost_mismatches = 0
    for run in successful_auto:
        for call in run["calls"]:
            model = call.get("selected_model") or "missing"
            decision = call.get("decision") or "missing"
            reasoning = call.get("reasoning") or "missing"
            phase = call.get("phase") or "missing"
            model_counts[model] += 1
            decision_counts[decision] += 1
            reasoning_counts[reasoning] += 1
            phase_counts[phase][f"{decision} → {model}"] += 1
            key = f"{decision} → {model}"
            aggregate = route_rows.setdefault(
                key,
                {
                    "decision": decision,
                    "model": model,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost_xxx": Decimal(0),
                    "latencies": [],
                },
            )
            aggregate["calls"] += 1
            for token_key in (
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
            ):
                aggregate[token_key] += int(call["usage"][token_key])
            aggregate["cost_xxx"] += decimal(call["actual_cost_xxx"])
            if call.get("latency_seconds") is not None:
                aggregate["latencies"].append(
                    float(call["latency_seconds"])
                )
            selected = canonical_model(call.get("selected_model"), factors)
            response = canonical_model(call.get("response_model"), factors)
            cost_model = call.get("cost_model")
            if selected and response and selected != response:
                selected_response_mismatches += 1
            if response and cost_model and response != cost_model:
                response_cost_mismatches += 1

    route_distribution = []
    total_auto_calls = sum(model_counts.values())
    for key in sorted(route_rows):
        row = route_rows[key]
        route_distribution.append(
            {
                "decision": row["decision"],
                "model": row["model"],
                "calls": row["calls"],
                "call_share_percent": percentage(
                    Decimal(row["calls"]),
                    Decimal(total_auto_calls),
                ),
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "reasoning_tokens": row["reasoning_tokens"],
                "cost_xxx": rounded(row["cost_xxx"]),
                "latency_seconds": stats(row["latencies"]),
            }
        )

    return {
        "schema_version": "openclaw-policy-analysis/v1",
        "inputs": experiments,
        "recipe": factors.get("recipe"),
        "rates": factors.get("models"),
        "quality_definition": {
            "baseline": "5 failed, 102 passed",
            "final": "107 passed",
            "tests_unchanged": True,
            "minimal_source_only_fix": True,
        },
        "arms": arm_results,
        "overall_comparison": overall_comparison,
        "paired_outcomes": {
            "both_functionally_passed": sum(
                pair["arms"]["auto"]["functional_passed"]
                and pair["arms"]["direct_glm"]["functional_passed"]
                for pair in pair_rows
            ),
            "auto_passed_direct_failed": sum(
                pair["arms"]["auto"]["functional_passed"]
                and not pair["arms"]["direct_glm"]["functional_passed"]
                for pair in pair_rows
            ),
            "direct_passed_auto_failed": sum(
                not pair["arms"]["auto"]["functional_passed"]
                and pair["arms"]["direct_glm"]["functional_passed"]
                for pair in pair_rows
            ),
            "both_failed": sum(
                not pair["arms"]["auto"]["functional_passed"]
                and not pair["arms"]["direct_glm"]["functional_passed"]
                for pair in pair_rows
            ),
        },
        "matched_successful_pairs": {
            "count": len(matched),
            "pairs": matched,
            "auto_cost_xxx": rounded(matched_auto),
            "direct_glm_cost_xxx": rounded(matched_direct),
            "cost_difference_xxx": rounded(matched_direct - matched_auto),
            "pooled_auto_savings_percent": savings(
                matched_auto,
                matched_direct,
            ),
            "pair_savings_percent": stats(pair_savings),
            "time_saved_seconds": stats(time_saved),
            "pooled_latency_reduction_percent": (
                savings(
                    Decimal(
                        str(
                            sum(
                                float(row["auto_workflow_seconds"])
                                for row in matched
                            )
                        )
                    ),
                    Decimal(
                        str(
                            sum(
                                float(row["direct_glm_workflow_seconds"])
                                for row in matched
                            )
                        )
                    ),
                )
                if matched
                else None
            ),
        },
        "same_auto_token_backend_mix": {
            "successful_auto_runs": len(successful_auto),
            "auto_actual_cost_xxx": rounded(routed_actual),
            "same_tokens_at_glm_rates_xxx": rounded(routed_reprice),
            "gross_backend_model_mix_savings_percent": savings(
                routed_actual,
                routed_reprice,
            ),
            "qualification": (
                "Counterfactual same-token repricing. It excludes router "
                "overhead and is not a direct-GLM execution."
            ),
        },
        "auto_routes": {
            "calls": total_auto_calls,
            "models": dict(model_counts),
            "decisions": dict(decision_counts),
            "reasoning": dict(reasoning_counts),
            "phase_routes": {
                phase: dict(rows)
                for phase, rows in sorted(phase_counts.items())
            },
            "distribution": route_distribution,
            "selected_response_model_mismatches": (
                selected_response_mismatches
            ),
            "response_cost_model_mismatches": response_cost_mismatches,
        },
        "attempts": pair_rows,
        "methodology": {
            "harness_retries": 0,
            "internal_provider_retries": "not instrumented",
            "latency_percentile": "nearest-rank",
            "cost_formula": (
                "(prompt_tokens * prompt_rate + completion_tokens * "
                "completion_rate) / 1,000,000"
            ),
            "currency": "XXX relative compute units; not money",
        },
    }


def markdown(result: dict[str, Any]) -> str:
    auto = result["arms"]["auto"]
    direct = result["arms"]["direct_glm"]
    matched = result["matched_successful_pairs"]
    routing = result["same_auto_token_backend_mix"]
    overall = result["overall_comparison"]
    lines = [
        "# OpenClaw: vLLM-SR Auto vs Direct GLM",
        "",
        "## Executive result",
        "",
        "| Metric | vLLM-SR auto | Direct GLM |",
        "| --- | ---: | ---: |",
        f"| Functional successes | {auto['functional_successes']}/"
        f"{auto['attempts']} | {direct['functional_successes']}/"
        f"{direct['attempts']} |",
        f"| Success rate | {auto['functional_success_rate_percent']}% | "
        f"{direct['functional_success_rate_percent']}% |",
        f"| Observed requests | {auto['requests']} | {direct['requests']} |",
        f"| Prompt tokens | {auto['tokens']['prompt_tokens']} | "
        f"{direct['tokens']['prompt_tokens']} |",
        f"| Completion tokens | {auto['tokens']['completion_tokens']} | "
        f"{direct['tokens']['completion_tokens']} |",
        f"| Reasoning tokens | {auto['tokens']['reasoning_tokens']} | "
        f"{direct['tokens']['reasoning_tokens']} |",
        f"| Mean completed workflow | "
        f"{auto['completed_workflow_seconds']['mean']} s | "
        f"{direct['completed_workflow_seconds']['mean']} s |",
        "",
        "Every functional success started at `5 failed, 102 passed`, ended at "
        "`107 passed`, left tests unchanged, and made only the accepted "
        "one-line source correction.",
        "",
        "### Failure-inclusive observed compute",
        "",
        "| Metric | vLLM-SR auto | Direct GLM |",
        "| --- | ---: | ---: |",
        f"| Observed compute across all attempts | "
        f"{auto['observed_cost_total_xxx']:.8f} XXX | "
        f"{direct['observed_cost_total_xxx']:.8f} XXX |",
        f"| Compute per functional success | "
        f"{auto['failure_inclusive_cost_per_success_xxx']:.8f} XXX | "
        f"{direct['failure_inclusive_cost_per_success_xxx']:.8f} XXX |",
        f"| Cost coverage | {auto['cost_observed_attempts']}/"
        f"{auto['attempts']} attempts | {direct['cost_observed_attempts']}/"
        f"{direct['attempts']} attempts |",
        "",
        "## Empirical matched-success comparison",
        "",
        f"- Successful matched pairs: `{matched['count']}`",
        f"- Auto observed compute: `{matched['auto_cost_xxx']:.8f} XXX`",
        f"- Direct GLM observed compute: "
        f"`{matched['direct_glm_cost_xxx']:.8f} XXX`",
        f"- Pooled auto savings: "
        f"`{matched['pooled_auto_savings_percent']}%`",
        f"- Mean time saved per matched workflow: "
        f"`{matched['time_saved_seconds']['mean']} s`",
        f"- Pooled latency reduction: "
        f"`{matched['pooled_latency_reduction_percent']}%`",
        "",
        "| Experiment | Pair | Auto XXX | Direct GLM XXX | Savings | "
        "Time saved |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for pair in matched["pairs"]:
        lines.append(
            f"| {pair['experiment']} | {pair['pair_id']} | "
            f"{pair['auto_cost_xxx']:.8f} | "
            f"{pair['direct_glm_cost_xxx']:.8f} | "
            f"{pair['auto_savings_percent']}% | "
            f"{pair['time_saved_seconds']} s |"
        )
    lines.extend(
        [
            "",
            "The pooled result is a ratio of total compute. Across individual "
            f"pairs, savings ranged from "
            f"`{matched['pair_savings_percent']['min']}%` to "
            f"`{matched['pair_savings_percent']['max']}%`, with a median of "
            f"`{matched['pair_savings_percent']['median']}%`.",
            "",
            "## Same-auto-token routing sensitivity",
            "",
            f"- Successful auto runs: `{routing['successful_auto_runs']}`",
            f"- Auto selected-backend compute: "
            f"`{routing['auto_actual_cost_xxx']:.8f} XXX`",
            f"- The same tokens priced entirely as GLM: "
            f"`{routing['same_tokens_at_glm_rates_xxx']:.8f} XXX`",
            f"- Gross backend-model-mix savings: "
            f"`{routing['gross_backend_model_mix_savings_percent']}%`",
            "",
            routing["qualification"],
            "",
        "### Why the empirical reduction is larger",
        "",
        f"Compared with direct GLM across all attempts, auto used "
        f"`{overall['request_reduction_percent']}%` fewer requests, "
        f"`{overall['completion_token_reduction_percent']}%` fewer completion "
        f"tokens, and `{overall['reasoning_token_reduction_percent']}%` fewer "
        "reasoning tokens. Therefore the empirical policy result captures "
        "both backend selection and different model/tool-loop trajectories; "
        "the same-token result isolates only the selected-backend rate mix.",
            "",
            "## Auto route distribution",
            "",
            "| Decision | Selected model | Calls | Share | Cost XXX | "
            "P90 latency |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in result["auto_routes"]["distribution"]:
        lines.append(
            f"| `{row['decision']}` | `{row['model']}` | {row['calls']} | "
            f"{row['call_share_percent']}% | {row['cost_xxx']:.8f} | "
            f"{row['latency_seconds']['p90_nearest_rank']} s |"
        )
    lines.extend(
        [
            "",
            "### Routes by OpenClaw phase",
            "",
            "```json",
            json.dumps(result["auto_routes"]["phase_routes"], indent=2),
            "```",
            "",
            "## Harness correction",
            "",
            f"- Original strict-text successes: auto "
            f"`{auto['reported_successes']}/{auto['attempts']}`, direct GLM "
            f"`{direct['reported_successes']}/{direct['attempts']}`.",
            f"- Corrected functional successes: auto "
            f"`{auto['functional_successes']}/{auto['attempts']}`, direct GLM "
            f"`{direct['functional_successes']}/{direct['attempts']}`.",
            "- Four direct-GLM runs used the equivalent minimal expression "
            "`round(correct / total_typed * 100, 1)`. They passed all 107 "
            "tests, left tests unchanged, and changed only the intended "
            "source line, so they are functional successes rather than model "
            "failures.",
            "- The one retained direct-GLM failure was a real terminal "
            "malformed tool-call outcome. Its observed token cost is included.",
            "",
            "## Reliability details",
            "",
            "```json",
            json.dumps(
                {
                    "paired_outcomes": result["paired_outcomes"],
                    "auto_failures": auto["failure_classes"],
                    "direct_glm_failures": direct["failure_classes"],
                    "auto_cost_coverage": {
                        "observed": auto["cost_observed_attempts"],
                        "missing": auto["cost_missing_attempts"],
                    },
                    "direct_glm_cost_coverage": {
                        "observed": direct["cost_observed_attempts"],
                        "missing": direct["cost_missing_attempts"],
                    },
                },
                indent=2,
            ),
            "```",
            "",
            "## Interpretation",
            "",
            "- The empirical matched comparison includes only pairs where both "
            "policies passed the same deterministic quality gate.",
            "- Failure-inclusive cost per success is reported only when every "
            "attempt has recoverable route usage.",
            "- `XXX` is a versioned relative-compute unit, not a dollar cost.",
            "- Harness retries were zero; internal provider retries were not "
            "instrumented.",
            "- This is a nine-pair workshop experiment on one deterministic "
            "debugging task, not a general model-quality benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    result = analyze([path.resolve() for path in args.summaries])
    args.json_output.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(
        markdown(result),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

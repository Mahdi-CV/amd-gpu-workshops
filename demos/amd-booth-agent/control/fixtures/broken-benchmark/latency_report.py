"""Small latency report used by the AMD booth agent demo."""

from __future__ import annotations


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    # BUG: integer division collapses every percentile below 100 to index 0.
    index = round((percent // 100) * (len(ordered) - 1))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }

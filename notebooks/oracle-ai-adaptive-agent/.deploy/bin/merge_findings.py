#!/usr/bin/env python3
"""Deterministically deduplicate specialist findings into ReviewBench JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "so",
    "the",
    "this",
    "to",
    "with",
}


def tokens(message: str) -> set[str]:
    return {
        value
        for value in re.findall(r"[a-z0-9_]+", message.lower())
        if len(value) > 2 and value not in STOPWORDS
    }


def signature(message: str) -> str:
    value = message.lower()
    if ("paginate" in value or "pagination" in value) and "review" in value:
        return "reviews-pagination"
    if ("paginate" in value or "pagination" in value) and "commit" in value:
        return "commits-pagination"
    if "minimize" in value and ("outdated" in value or "fresh" in value):
        return "mutation-before-freshness"
    if "commit_id" in value and (
        "timestamp" in value or "submitted_at" in value or "head sha" in value
    ):
        return "timestamp-vs-sha"
    if "hascopilotpendingreview" in value and (
        "doubl" in value or "same endpoint" in value or "single call" in value
    ):
        return "duplicate-review-fetch"
    if "checkcopilotreviewstatus" in value or (
        "pr body" in value and "single pass" in value
    ):
        return "pr-contract-mismatch"
    if "test" in value and ("missing" in value or "no automated" in value):
        return "missing-tests"
    if "same second" in value or "strict after" in value:
        return "timestamp-boundary"
    return ""


def nearby(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["file"] != right["file"]:
        return False
    left_start = int(left["start_line"])
    left_end = int(left["end_line"])
    right_start = int(right["start_line"])
    right_end = int(right["end_line"])
    return not (left_end < right_start - 5 or right_end < left_start - 5)


def similar(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not nearby(left, right):
        return False
    left_signature = signature(left["message"])
    right_signature = signature(right["message"])
    if left_signature and left_signature == right_signature:
        return True
    left_tokens = tokens(left["message"])
    right_tokens = tokens(right["message"])
    if not left_tokens or not right_tokens:
        return False
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    anchors = {
        "paginate",
        "pagination",
        "commits",
        "reviews",
        "commit_id",
        "timestamp",
        "minimize",
        "outdated",
        "test",
        "single",
        "duplicate",
    }
    shared_anchors = left_tokens & right_tokens & anchors
    return jaccard >= 0.36 or (jaccard >= 0.24 and bool(shared_anchors))


def choose(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    def score(item: dict[str, Any]) -> tuple[int, int]:
        span = int(item["end_line"]) - int(item["start_line"])
        return (len(item["message"]), -span)

    return max(cluster, key=score)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    packet = json.loads(args.packet.read_text())
    findings: list[dict[str, Any]] = []
    for path in args.input:
        findings.extend(json.loads(path.read_text()).get("findings", []))

    clusters: list[list[dict[str, Any]]] = []
    for finding in findings:
        for cluster in clusters:
            if any(similar(finding, existing) for existing in cluster):
                cluster.append(finding)
                break
        else:
            clusters.append([finding])

    merged = []
    for cluster in clusters:
        selected = choose(cluster)
        merged.append(
            {
                "file": selected["file"],
                "start_line": int(selected["start_line"]),
                "end_line": int(selected["end_line"]),
                "message": selected["message"],
                "producer": "openclaw-vllm-sr-panel",
            }
        )
    merged.sort(key=lambda item: (item["file"], item["start_line"], item["end_line"]))

    task = packet["task"]
    contract = {
        "pr": {
            "repo": task["repo"],
            "pr_number": task["pr_number"],
            "base": task["base"],
            "head": task["head"],
        },
        "agent": "openclaw-vllm-sr-panel",
        "findings": merged,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n")
    print(
        json.dumps(
            {
                "input_findings": len(findings),
                "clusters": len(clusters),
                "output_findings": len(merged),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

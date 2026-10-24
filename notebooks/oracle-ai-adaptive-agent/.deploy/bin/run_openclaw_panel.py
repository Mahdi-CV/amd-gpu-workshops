#!/usr/bin/env python3
"""Run the tool-free OpenClaw panel and emit ReviewBench findings JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from merge_findings import choose, similar


def compact_packet(packet: dict[str, Any]) -> str:
    task = packet["task"]
    file_sections = "\n\n".join(
        f"===== FILE {item['path']} AT HEAD =====\n{item['content']}"
        for item in packet["files"]
    )
    return (
        f"REPOSITORY: {task['nwo']}\n"
        f"PR: {task['pr_number']}\n"
        f"TITLE: {task['title']}\n"
        f"BODY:\n{task['body']}\n\n"
        f"===== BASE...HEAD DIFF =====\n{packet['diff']}\n\n"
        f"{file_sections}"
    )


def output_contract(agent: str) -> str:
    return f"""
Return only JSON in this shape:
{{
  "findings": [
    {{
      "file": "repository/relative/path",
      "start_line": 1,
      "end_line": 1,
      "message": "Specific actionable issue and why it matters.",
      "producer": "{agent}"
    }}
  ]
}}

Rules:
- Zero to nine findings.
- One logical issue per finding.
- Anchor to line numbers in the head file.
- Report only actionable issues introduced or exacerbated by this PR.
- Do not report formatting preferences or vague concerns.
- Keep each message under 280 characters while stating the concrete failure.
- Do not use markdown fences.
""".strip()


def extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", value, re.S)
    if fence:
        value = fence.group(1).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(value[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"Could not parse JSON from agent output: {text[:500]}")


def validate_findings(
    findings: list[dict[str, Any]],
    changed_files: set[str],
    producer: str,
) -> list[dict[str, Any]]:
    validated = []
    for finding in findings:
        file = str(finding.get("file") or "").lstrip("./")
        start = int(finding.get("start_line") or 0)
        end = int(finding.get("end_line") or start)
        message = str(finding.get("message") or "").strip()
        if not file or not message or start <= 0 or end < start:
            continue
        validated.append(
            {
                "file": file,
                "start_line": start,
                "end_line": end,
                "message": message,
                "producer": producer,
                "changed_file": file in changed_files,
            }
        )
    return validated


def run_agent(
    args: argparse.Namespace,
    agent: str,
    session_id: str,
    message: str,
) -> tuple[str, dict[str, Any], float]:
    env = dict(os.environ)
    env["OPENCLAW_STATE_DIR"] = str(args.state_dir)
    started = time.perf_counter()
    result = subprocess.run(
        [
            args.openclaw,
            "agent",
            "--agent",
            agent,
            "--session-id",
            session_id,
            "--local",
            "--json",
            "--timeout",
            "900",
            "--message",
            message,
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if result.returncode:
        raise RuntimeError(
            f"OpenClaw agent {agent} failed with status {result.returncode}: "
            f"{result.stderr[-1200:]}"
        )
    body = json.loads(result.stdout)
    text = body["payloads"][0]["text"]
    return text, body, elapsed


def run_json_agent(
    args: argparse.Namespace,
    *,
    agent: str,
    session_id: str,
    prompt: str,
    output_prefix: str,
) -> tuple[dict[str, Any], float]:
    text, body, elapsed = run_agent(args, agent, session_id, prompt)
    (args.output_dir / f"{output_prefix}.raw.txt").write_text(text)
    (args.output_dir / f"{output_prefix}.openclaw.json").write_text(
        json.dumps(body, indent=2) + "\n"
    )
    try:
        return extract_json(text), elapsed
    except (ValueError, json.JSONDecodeError) as exc:
        retry_prompt = (
            "Your previous response was not valid JSON. Return the same findings "
            "again as one valid JSON object only. Escape every quote inside "
            "message strings, do not use markdown fences, and do not add or "
            f"remove findings. Parser error: {type(exc).__name__}."
        )
        retry_text, retry_body, retry_elapsed = run_agent(
            args,
            agent,
            session_id,
            retry_prompt,
        )
        (args.output_dir / f"{output_prefix}.retry.raw.txt").write_text(
            retry_text
        )
        (args.output_dir / f"{output_prefix}.retry.openclaw.json").write_text(
            json.dumps(retry_body, indent=2) + "\n"
        )
        return extract_json(retry_text), elapsed + retry_elapsed


def deterministic_union(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for group in groups:
        for item in group:
            key = (
                item["file"],
                item["start_line"],
                item["end_line"],
                item["message"].lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--reuse-specialists-from", type=Path, default=None)
    parser.add_argument(
        "--llm-merge",
        action="store_true",
        help="Use rb_merger instead of deterministic finding deduplication.",
    )
    parser.add_argument(
        "--openclaw",
        default=os.getenv("OPENCLAW_BIN")
        or shutil.which("openclaw")
        or "openclaw",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    packet = json.loads(args.packet.read_text())
    review_packet = compact_packet(packet)
    changed_files = set(packet["changed_files"])
    run_tag = str(int(time.time()))

    prompts = {
        "rb_correctness": (
            "Act as the correctness and security reviewer. Inspect the frozen "
            "pull-request packet below. Focus on behavioral bugs, security, "
            "reliability, and missing tests. Check the PR description against "
            "the implementation.\n\n"
            + output_contract("rb_correctness")
            + "\n\n"
            + review_packet
        ),
        "rb_reliability": (
            "Act as the reliability and performance reviewer. Inspect the "
            "frozen pull-request packet below. Focus on performance, duplicate "
            "work, API behavior, maintainability, pagination, ordering, and "
            "operational failure modes. Check the PR description against the "
            "implementation.\n\n"
            + output_contract("rb_reliability")
            + "\n\n"
            + review_packet
        ),
        "rb_integration": (
            "Act as the integration and control-flow reviewer. Inspect the "
            "frozen pull-request packet below. Trace caller ordering, state "
            "mutation, cross-file behavior, pagination, and whether an earlier "
            "operation destroys or invalidates state needed by a later one. "
            "For every new condition or early return, inspect the mutating "
            "operations that execute before it and determine whether returning "
            "early preserves externally visible state. Start with the changed "
            "call site in cmd/root.go and its preceding operations. Return at "
            "most three high-confidence findings. Check the PR description "
            "against the implementation.\n\n"
            + output_contract("rb_integration")
            + "\n\n"
            + review_packet
        ),
    }

    specialist_findings: dict[str, list[dict[str, Any]]] = {}
    timings: dict[str, float] = {}
    for agent, prompt in prompts.items():
        reusable = (
            args.reuse_specialists_from / f"{agent}.findings.json"
            if args.reuse_specialists_from
            else None
        )
        if reusable and reusable.is_file():
            findings = json.loads(reusable.read_text()).get("findings", [])
            specialist_findings[agent] = findings
            timings[agent] = 0.0
            (args.output_dir / f"{agent}.findings.json").write_text(
                json.dumps({"findings": findings}, indent=2) + "\n"
            )
            continue
        parsed, elapsed = run_json_agent(
            args,
            agent=agent,
            session_id=f"reviewbench-{run_tag}-{agent}",
            prompt=prompt,
            output_prefix=agent,
        )
        findings = validate_findings(
            parsed.get("findings", []),
            changed_files,
            agent,
        )
        specialist_findings[agent] = findings
        timings[agent] = round(elapsed, 3)
        (args.output_dir / f"{agent}.findings.json").write_text(
            json.dumps({"findings": findings}, indent=2) + "\n"
        )

    union = deterministic_union(list(specialist_findings.values()))
    if args.llm_merge:
        merge_prompt = (
            "Merge these reviewer result sets. Preserve every distinct, "
            "actionable issue. Remove only true duplicates. Return valid JSON.\n\n"
            + output_contract("openclaw-vllm-sr-panel")
            + "\n\nCANDIDATE FINDINGS:\n"
            + json.dumps(union, indent=2)
        )
        merge_parsed, merge_elapsed = run_json_agent(
            args,
            agent="rb_merger",
            session_id=f"reviewbench-{run_tag}-merger",
            prompt=merge_prompt,
            output_prefix="merger",
        )
        merged = validate_findings(
            merge_parsed.get("findings", []),
            changed_files,
            "openclaw-vllm-sr-panel",
        )
        timings["rb_merger"] = round(merge_elapsed, 3)
    else:
        clusters: list[list[dict[str, Any]]] = []
        for finding in union:
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
                    "start_line": selected["start_line"],
                    "end_line": selected["end_line"],
                    "message": selected["message"],
                    "producer": "openclaw-vllm-sr-panel",
                    "changed_file": selected.get("changed_file", False),
                }
            )
        merged.sort(
            key=lambda item: (
                item["file"],
                item["start_line"],
                item["end_line"],
            )
        )
        timings["deterministic_merge"] = 0.0

    task = packet["task"]
    contract = {
        "pr": {
            "repo": task["repo"],
            "pr_number": task["pr_number"],
            "base": task["base"],
            "head": task["head"],
        },
        "agent": "openclaw-vllm-sr-panel",
        "findings": [
            {
                key: item[key]
                for key in ("file", "start_line", "end_line", "message", "producer")
            }
            for item in merged
        ],
    }
    union_contract = {
        **contract,
        "agent": "openclaw-vllm-sr-union",
        "findings": [
            {
                "file": item["file"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
                "message": item["message"],
                "producer": item["producer"],
            }
            for item in union
        ],
    }
    (args.output_dir / "findings.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )
    (args.output_dir / "findings-union.json").write_text(
        json.dumps(union_contract, indent=2) + "\n"
    )
    summary = {
        "task": task["nwo"] + "#" + str(task["pr_number"]),
        "specialist_counts": {
            key: len(value) for key, value in specialist_findings.items()
        },
        "union_count": len(union),
        "merged_count": len(merged),
        "timings_seconds": timings,
    }
    (args.output_dir / "run-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

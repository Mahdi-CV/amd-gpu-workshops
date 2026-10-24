#!/usr/bin/env python3
"""Build a frozen, line-numbered ReviewBench packet without golden findings."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def run_git(checkout: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def numbered(text: str) -> str:
    return "\n".join(
        f"{index:5d} | {line}"
        for index, line in enumerate(text.splitlines(), start=1)
    )


def bounded_file(path: Path, max_chars: int) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "path": str(path),
        "content": numbered(text),
        "truncated": truncated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewbench-root", type=Path, required=True)
    parser.add_argument("--task-index", type=int, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-file-chars", type=int, default=30000)
    args = parser.parse_args()

    tasks = json.loads(
        (args.reviewbench_root / "corpus/test/test.json").read_text()
    )
    task = tasks[args.task_index]
    head = run_git(args.checkout, "rev-parse", "HEAD").strip()
    if head != task["head"]:
        raise SystemExit(f"Checkout is at {head}, expected {task['head']}")

    diff = run_git(args.checkout, "diff", f"{task['base']}...{task['head']}")
    changed_files = [
        value.strip()
        for value in run_git(
            args.checkout,
            "diff",
            "--name-only",
            f"{task['base']}...{task['head']}",
        ).splitlines()
        if value.strip()
    ]
    files = []
    for relative in changed_files:
        path = args.checkout / relative
        if path.is_file():
            item = bounded_file(path, args.max_file_chars)
            item["path"] = relative
            files.append(item)

    packet = {
        "schema_version": "openclaw-review-packet/v1",
        "task": task,
        "diff": diff,
        "changed_files": changed_files,
        "files": files,
        "instructions": {
            "no_network": True,
            "review_head": task["head"],
            "line_numbers": "All file line numbers refer to the head commit.",
            "scope": (
                "Report actionable issues introduced or exacerbated by this PR. "
                "Do not report trivial style preferences."
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "changed_files": changed_files,
                "diff_chars": len(diff),
                "file_context_chars": sum(
                    len(item["content"]) for item in files
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

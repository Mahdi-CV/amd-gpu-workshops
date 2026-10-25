#!/usr/bin/env python3
"""Verify a comparison summary and its summary-derived CSV/report."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType


def load_compare_module() -> ModuleType:
    path = Path(__file__).resolve().with_name("compare-policies.py")
    spec = importlib.util.spec_from_file_location("compare_policies", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "summary",
        nargs="?",
        type=Path,
        default=(
            Path(os.environ["COMPARISON_SUMMARY"])
            if os.getenv("COMPARISON_SUMMARY")
            else None
        ),
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Regenerate comparison.csv and report.md before verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.summary is None:
        raise SystemExit(
            "Pass summary.json or set COMPARISON_SUMMARY."
        )
    module = load_compare_module()
    module.render_derived(args.summary)
    errors = module.verify_summary_file(args.summary)
    result = {
        "summary": str(args.summary),
        "passed": not errors,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

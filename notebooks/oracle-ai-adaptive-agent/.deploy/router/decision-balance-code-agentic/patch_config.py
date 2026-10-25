#!/usr/bin/env python3
"""Insert the tested code_agentic decision into a Decision Balance config."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - operator dependency error
    raise SystemExit(
        "PyYAML is required. Install it with: python3 -m pip install PyYAML"
    ) from exc


ROUTE_NAME = "code_agentic"
ROUTE_PRIORITY = 750
REQUIRED_DECISIONS = {
    "recovery": 800,
    "agentic": 700,
    "code": 450,
}

CODE_AGENTIC_DECISION: dict[str, Any] = {
    "algorithm": {"type": "static"},
    "description": (
        "Code-review and debugging requests that use tools go to Flash-Next, "
        "while non-code tool work and recovery still use GLM."
    ),
    "modelRefs": [
        {
            "model": "qwen/qwen3.8-flash-next",
            "reasoning_effort": "medium",
            "use_reasoning": True,
        }
    ],
    "name": ROUTE_NAME,
    "priority": ROUTE_PRIORITY,
    "rules": {
        "conditions": [
            {
                "label": "code",
                "name": "task",
                "type": "decision",
            },
            {
                "conditions": [
                    {
                        "name": "has_tools",
                        "type": "conversation",
                    },
                    {
                        "name": "tool_loop",
                        "type": "conversation",
                    },
                ],
                "operator": "OR",
            },
        ],
        "on_unknown": "no_match",
        "operator": "AND",
    },
}


class ConfigError(RuntimeError):
    """Raised when a config is not a compatible Decision Balance document."""


def _decisions(document: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        rows = document["routing"]["decisions"]
    except (KeyError, TypeError) as exc:
        raise ConfigError("Config lacks routing.decisions.") from exc
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) for row in rows
    ):
        raise ConfigError("routing.decisions must be a list of objects.")
    return rows


def _validate_base(rows: list[dict[str, Any]]) -> None:
    by_name = {
        str(row.get("name")): row
        for row in rows
        if row.get("name") is not None
    }
    missing = sorted(set(REQUIRED_DECISIONS) - set(by_name))
    if missing:
        raise ConfigError(
            "Config is not a compatible Decision Balance config; missing "
            f"decisions: {', '.join(missing)}."
        )
    for name, expected_priority in REQUIRED_DECISIONS.items():
        actual = by_name[name].get("priority")
        if actual != expected_priority:
            raise ConfigError(
                f"Decision {name!r} has priority {actual!r}; expected "
                f"{expected_priority}. Refusing to guess insertion order."
            )


def _validate_provider(document: dict[str, Any]) -> None:
    models = ((document.get("providers") or {}).get("models") or [])
    names = {
        str(model.get("name"))
        for model in models
        if isinstance(model, dict)
    }
    if "qwen/qwen3.8-flash-next" not in names:
        raise ConfigError(
            "Config does not define provider model "
            "'qwen/qwen3.8-flash-next'."
        )


def patch_document(
    document: dict[str, Any],
    *,
    replace_existing: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Return a patched copy and whether the document changed."""

    patched = copy.deepcopy(document)
    rows = _decisions(patched)
    _validate_base(rows)
    _validate_provider(patched)

    existing = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("name") == ROUTE_NAME
    ]
    if len(existing) > 1:
        raise ConfigError(f"Config contains multiple {ROUTE_NAME!r} decisions.")
    if existing:
        index, row = existing[0]
        if row == CODE_AGENTIC_DECISION:
            return patched, False
        if not replace_existing:
            raise ConfigError(
                f"Config already contains a different {ROUTE_NAME!r} "
                "decision. Re-run with --replace-existing only after review."
            )
        rows.pop(index)

    collision = [
        str(row.get("name"))
        for row in rows
        if row.get("priority") == ROUTE_PRIORITY
    ]
    if collision:
        raise ConfigError(
            f"Priority {ROUTE_PRIORITY} is already used by: "
            f"{', '.join(collision)}."
        )

    agentic_index = next(
        index
        for index, row in enumerate(rows)
        if row.get("name") == "agentic"
    )
    rows.insert(agentic_index, copy.deepcopy(CODE_AGENTIC_DECISION))
    return patched, True


def render_yaml(document: dict[str, Any]) -> str:
    return yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Input config does not exist: {args.input}")
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"Output already exists: {args.output}; pass --force to replace."
        )

    source = yaml.safe_load(args.input.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise SystemExit("Input config is not a YAML object.")
    try:
        patched, changed = patch_document(
            source,
            replace_existing=args.replace_existing,
        )
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    rendered = render_yaml(patched)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "changed": changed,
                "decision": ROUTE_NAME,
                "priority": ROUTE_PRIORITY,
                "sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

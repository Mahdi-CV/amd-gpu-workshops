#!/usr/bin/env python3
"""Validate, plan, and optionally hot-apply a complete router config."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_token(args: argparse.Namespace) -> str:
    if args.token_file:
        token = args.token_file.read_text(encoding="utf-8").strip()
    else:
        token = os.getenv(args.token_env, "").strip()
    if not token:
        raise SystemExit(
            f"Set {args.token_env} or pass --token-file. The token is never "
            "written to receipts."
        )
    return token


def request_json(
    *,
    endpoint: str,
    path: str,
    token: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> tuple[dict[str, Any], dict[str, str], int]:
    raw = json.dumps(body).encode() if body is not None else None
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if raw else {}),
        **(headers or {}),
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + path,
        data=raw,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_raw = response.read()
            status = response.status
            response_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        response_raw = exc.read()
        raise RuntimeError(
            f"{method} {path} failed with HTTP {exc.code}: "
            f"{response_raw.decode(errors='replace')[:2000]}"
        ) from exc
    payload = json.loads(response_raw or b"{}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"{method} {path} returned a non-object response.")
    return payload, response_headers, status


def write_receipt(path: Path, body: dict[str, Any]) -> None:
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080",
        help="Router management base URL.",
    )
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--token-env", default="VSR_MGMT_TOKEN")
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply after validation and planning. Default is dry-run.",
    )
    args = parser.parse_args()

    if not args.config.is_file():
        raise SystemExit(f"Config does not exist: {args.config}")
    token = load_token(args)
    yaml_text = args.config.read_text(encoding="utf-8")
    receipt_dir = args.receipt_dir or Path(
        f"code-agentic-receipts-{utc_stamp()}"
    )
    receipt_dir.mkdir(parents=True, exist_ok=False)

    current, current_headers, _ = request_json(
        endpoint=args.endpoint,
        path="/api/v1/config",
        token=token,
        timeout=args.timeout,
    )
    etag = current_headers.get("etag")
    if not etag:
        raise RuntimeError("GET /api/v1/config returned no ETag.")
    write_receipt(
        receipt_dir / "config-before-metadata.json",
        {
            "etag": etag,
            "config_hash": current_headers.get("x-vsr-config-hash"),
            "config_version": current_headers.get("x-vsr-config-version"),
            "decisions": [
                str(row.get("name"))
                for row in (
                    ((current.get("routing") or {}).get("decisions") or [])
                )
                if isinstance(row, dict)
            ],
        },
    )

    validation, _, _ = request_json(
        endpoint=args.endpoint,
        path="/api/v1/config/validate",
        token=token,
        method="POST",
        body={"yaml": yaml_text},
        timeout=args.timeout,
    )
    write_receipt(
        receipt_dir / "validate.json",
        {
            "valid": validation.get("valid"),
            "warnings": validation.get("warnings") or [],
        },
    )
    if validation.get("valid") is not True:
        raise RuntimeError("Router rejected the candidate config.")

    plan, _, _ = request_json(
        endpoint=args.endpoint,
        path="/api/v1/config/plan",
        token=token,
        method="POST",
        body={"mode": "replace", "yaml": yaml_text},
        timeout=args.timeout,
    )
    write_receipt(receipt_dir / "plan.json", plan)
    if plan.get("valid") is not True:
        raise RuntimeError("Router could not plan the candidate config.")

    summary: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "endpoint": args.endpoint,
        "current_etag": plan.get("current_etag", etag),
        "candidate_etag": plan.get("candidate_etag"),
        "changed": plan.get("changed"),
        "receipts": str(receipt_dir),
    }
    if not args.apply:
        print(json.dumps(summary, indent=2))
        return 0

    apply_body, apply_headers, status = request_json(
        endpoint=args.endpoint,
        path="/api/v1/config",
        token=token,
        method="PUT",
        body={"yaml": yaml_text},
        headers={"If-Match": str(plan.get("current_etag") or etag)},
        timeout=args.timeout,
    )
    write_receipt(receipt_dir / "apply.json", apply_body)
    summary["http_status"] = status
    summary["activation_status"] = apply_body.get("activation_status")

    candidate_hash = str(plan.get("candidate_etag") or "").strip('"')
    active = False
    for _ in range(60):
        status_body, _, _ = request_json(
            endpoint=args.endpoint,
            path="/api/v1/status",
            token=token,
            timeout=args.timeout,
        )
        write_receipt(receipt_dir / "status.json", status_body)
        config_status = status_body.get("config") or {}
        if (
            config_status.get("active_hash") == candidate_hash
            and config_status.get("activation_status") == "active"
        ):
            active = True
            summary["active_version"] = config_status.get("active_version")
            summary["active_hash"] = config_status.get("active_hash")
            break
        time.sleep(1)
    if not active:
        raise RuntimeError(
            "Candidate was persisted but did not become the active config."
        )

    safe_headers = {
        key: value
        for key, value in apply_headers.items()
        if key in {"etag", "x-request-id"}
    }
    write_receipt(receipt_dir / "apply-headers.json", safe_headers)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

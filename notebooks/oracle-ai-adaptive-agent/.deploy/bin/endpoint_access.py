"""Resolve a configurable OpenAI-compatible endpoint without storing secrets."""

from __future__ import annotations

import os


def endpoint_and_key(
    *,
    base_url: str = "",
    api_key: str = "",
) -> tuple[str, str]:
    resolved_url = (
        base_url
        or os.getenv("OPENAI_BASE_URL", "")
        or os.getenv("ADAPTIVE_AI_BASE_URL", "")
    ).strip()
    resolved_key = (
        api_key
        or os.getenv("OPENAI_API_KEY", "")
        or os.getenv("ADAPTIVE_AI_API_KEY", "")
    ).strip()

    if not resolved_url:
        raise RuntimeError(
            "Set OPENAI_BASE_URL or pass --base-url."
        )
    if not resolved_key:
        raise RuntimeError(
            "Set OPENAI_API_KEY or pass --api-key."
        )

    url = resolved_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url, resolved_key

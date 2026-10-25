"""Resolve OpenAI-compatible endpoint settings from file-backed secrets."""

from __future__ import annotations

import os
from pathlib import Path


def _read_secret(path_value: str, label: str) -> str:
    if not path_value:
        return ""
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise RuntimeError(f"{label} does not name a readable file: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{label} names an empty file: {path}")
    return value


def endpoint_and_key(
    *,
    base_url: str = "",
    api_key: str = "",
    api_key_file: str = "",
) -> tuple[str, str]:
    resolved_url = (
        base_url
        or os.getenv("OPENAI_BASE_URL", "")
        or os.getenv("AUTO_BASE_URL", "")
    ).strip()
    resolved_key = (
        api_key
        or _read_secret(
            api_key_file
            or os.getenv("OPENAI_API_KEY_FILE", "")
            or os.getenv("AUTO_API_KEY_FILE", ""),
            "API key file",
        )
    ).strip()

    if not resolved_url:
        raise RuntimeError("Set OPENAI_BASE_URL or AUTO_BASE_URL.")
    if not resolved_key:
        raise RuntimeError("Set OPENAI_API_KEY_FILE or AUTO_API_KEY_FILE.")

    url = resolved_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url, resolved_key

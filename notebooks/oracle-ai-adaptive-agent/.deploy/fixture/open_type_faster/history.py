"""
history.py
----------
Persistent session storage using a single JSON file in the user's home dir.

Schema
~~~~~~
{
    "sessions": [
        {
            "id":            "uuid4 string",
            "timestamp":     "ISO-8601 datetime",
            "mode":          "words" | "time" | "practice",
            "difficulty":    "easy" | "medium" | "hard" | "mixed",
            "word_count":    int,
            "duration":      float,           # seconds
            "gross_wpm":     float,
            "net_wpm":       float,
            "accuracy":      float,           # 0–100
            "correct_chars": int,
            "error_count":   int,
            "backspaces":    int,
            "mistyped_words": [str, ...]
        },
        ...
    ],
    "word_errors": {
        "<word>": <cumulative error count>,
        ...
    }
}

The module exposes a clean interface so callers never touch raw JSON.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stats import SessionResult


# ── Public interface ───────────────────────────────────────────────────────────

def save_session(
    result: SessionResult,
    *,
    mode: str,
    difficulty: str,
    history_file: Path,
) -> None:
    """
    Append a completed session to the history file and update per-word error
    counts.  Creates the file if it does not yet exist.
    """
    data = _load_raw(history_file)

    record: dict[str, Any] = {
        "id":            str(uuid.uuid4()),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "mode":          mode,
        "difficulty":    difficulty,
        "word_count":    result.word_count_typed,
        "duration":      round(result.duration, 2),
        "gross_wpm":     result.gross_wpm,
        "net_wpm":       result.net_wpm,
        "accuracy":      result.accuracy,
        "correct_chars": result.correct_chars,
        "error_count":   result.error_count,
        "backspaces":    result.backspaces,
        "mistyped_words": result.mistyped_words,
    }

    data["sessions"].append(record)

    # Accumulate word-level errors
    for word in result.mistyped_words:
        data["word_errors"][word] = data["word_errors"].get(word, 0) + 1

    _write_raw(data, history_file)


def load_sessions(history_file: Path) -> list[dict[str, Any]]:
    """Return all past sessions, newest first."""
    data = _load_raw(history_file)
    return list(reversed(data["sessions"]))


def load_word_errors(history_file: Path) -> dict[str, int]:
    """Return the cumulative per-word error map."""
    return _load_raw(history_file)["word_errors"]


def load_weak_words(history_file: Path, top_n: int = 20) -> list[str]:
    """
    Return up to *top_n* words the user has mistyped most often across all
    sessions.  Used by practice mode to generate targeted tests.
    """
    errors = load_word_errors(history_file)
    ranked = sorted(errors.items(), key=lambda kv: -kv[1])
    return [word for word, _ in ranked[:top_n]]


def summarise(history_file: Path) -> dict[str, Any] | None:
    """
    Compute aggregate statistics over the full history.
    Returns None if no sessions exist yet.
    """
    sessions = load_sessions(history_file)
    if not sessions:
        return None

    net_wpms = [s["net_wpm"] for s in sessions]
    accuracies = [s["accuracy"] for s in sessions]

    return {
        "total_sessions": len(sessions),
        "best_wpm":        max(net_wpms),
        "avg_wpm":         round(sum(net_wpms) / len(net_wpms), 1),
        "latest_wpm":      net_wpms[0],          # sessions are newest-first
        "best_accuracy":   max(accuracies),
        "avg_accuracy":    round(sum(accuracies) / len(accuracies), 1),
        "total_time_min":  round(sum(s["duration"] for s in sessions) / 60, 1),
        "top_weak_words":  load_weak_words(history_file, top_n=5),
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _empty_store() -> dict[str, Any]:
    return {"sessions": [], "word_errors": {}}


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        # Ensure expected top-level keys exist (forward-compat)
        data.setdefault("sessions", [])
        data.setdefault("word_errors", {})
        return data
    except (json.JSONDecodeError, OSError):
        return _empty_store()


def _write_raw(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

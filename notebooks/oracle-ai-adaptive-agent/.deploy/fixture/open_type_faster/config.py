"""
config.py
---------
Central configuration for Open Type Faster.
All tuneable defaults live here so AI agents (and humans) have a single
place to look when understanding or extending the app.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ── Paths ─────────────────────────────────────────────────────────────────────

# History is stored in the user's home directory so it persists across sessions.
HISTORY_FILE: Path = Path.home() / ".open_type_faster_history.json"


# ── Typing test defaults ───────────────────────────────────────────────────────

@dataclass
class Config:
    # Number of words in a standard test
    word_count: int = 25

    # Timed-mode duration in seconds (0 = no time limit)
    time_limit: int = 0

    # Test mode: "words" = fixed word count, "time" = countdown, "practice" = weak spots
    mode: Literal["words", "time", "practice"] = "words"

    # Allow the user to delete characters with backspace
    allow_backspace: bool = True

    # Path where session history is saved/loaded
    history_file: Path = field(default_factory=lambda: HISTORY_FILE)


# ── UI / colour theme ──────────────────────────────────────────────────────────

@dataclass
class Theme:
    # Correctly typed character
    correct: str = "bold green"

    # Incorrectly typed character
    error: str = "bold red"

    # Character that has not been reached yet
    pending: str = "white"

    # The character the cursor is sitting on
    cursor: str = "bold white on blue"

    # Accent colour for stats and borders
    accent: str = "cyan"

    # Subdued text (labels, hints)
    muted: str = "grey50"


# ── Singleton instances used throughout the app ────────────────────────────────

DEFAULT_CONFIG = Config()
DEFAULT_THEME = Theme()

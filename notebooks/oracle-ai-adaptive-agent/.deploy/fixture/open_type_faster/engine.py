"""
engine.py
---------
Core typing session loop.

The TypingSession class owns all mutable state for a single test.  It knows
nothing about Rich or the terminal — it just tracks what the user has typed
and exposes the current snapshot to whoever is rendering.

The run() free function wires TypingSession together with display.py and
handles the readchar event loop.  Separating state (TypingSession) from the
loop (run) makes both easier to test and easier for AI agents to repurpose
for a web back-end (e.g. a WebSocket handler could replace run() while
TypingSession stays the same).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import readchar
from rich.live import Live

import display
import stats as stats_module
from config import Config, Theme, DEFAULT_THEME
from stats import SessionResult
from words import words_in


# ── Session state ──────────────────────────────────────────────────────────────

@dataclass
class TypingSession:
    """
    Holds all mutable state for one typing test.

    Attributes
    ----------
    target : str
        The full text the user must type.
    typed : list[str]
        Characters the user has entered so far (one item per position).
    start_time : float | None
        Wall-clock timestamp of the first valid keystroke; None until then.
    end_time : float | None
        Wall-clock timestamp when the session finished; None until then.
    backspaces : int
        Total backspace presses recorded.
    aborted : bool
        True if the user pressed Escape before finishing.
    """

    target: str
    config: Config

    typed: list[str] = field(default_factory=list)
    start_time: float | None = None
    end_time: float | None = None
    backspaces: int = 0
    aborted: bool = False

    # ── Read-only derived properties ───────────────────────────────────────────

    @property
    def current_pos(self) -> int:
        """Index of the next character the user needs to type."""
        return len(self.typed)

    @property
    def is_complete(self) -> bool:
        return self.current_pos >= len(self.target)

    @property
    def elapsed(self) -> float:
        """Seconds since the first keystroke (0 if not started yet)."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.monotonic()
        return end - self.start_time

    @property
    def time_expired(self) -> bool:
        """True when a time-limited test has run out of time."""
        if self.config.time_limit <= 0:
            return False
        return self.elapsed >= self.config.time_limit

    # ── Mutation ───────────────────────────────────────────────────────────────

    def process_key(self, key: str) -> bool:
        """
        Handle a single raw key.

        Returns True when the session should end (complete, aborted, or time
        expired), False to keep going.
        """
        # Escape → quit early
        if key == readchar.key.ESC or key == "\x1b":
            self.aborted = True
            if self.end_time is None:
                self.end_time = time.monotonic()
            return True

        # Ctrl-C → hard quit (re-raise so the process exits cleanly)
        if key == readchar.key.CTRL_C:
            raise KeyboardInterrupt

        # Start the timer on the first real keystroke
        if self.start_time is None and key not in (
            readchar.key.ENTER,
            readchar.key.TAB,
            readchar.key.BACKSPACE,
            "\x7f",
        ):
            self.start_time = time.monotonic()

        # Backspace — \x7f (DEL) is what most terminals send for backspace
        if key in (readchar.key.BACKSPACE, "\x7f"):
            if self.typed and self.config.allow_backspace:
                self.typed.pop()
                self.backspaces += 1
            return False

        # Only accept printable single characters
        if len(key) == 1 and key.isprintable():
            if self.current_pos < len(self.target):
                self.typed.append(key)

            if self.is_complete:
                self.end_time = time.monotonic()
                return True

        # Check time limit (evaluated after processing the key)
        if self.time_expired:
            if self.end_time is None:
                self.end_time = time.monotonic()
            return True

        return False

    # ── Snapshot for rendering ─────────────────────────────────────────────────

    def live_stats(self) -> dict:
        """
        Compute live WPM / accuracy without creating a full SessionResult.
        Called on every keystroke so it must be fast.
        """
        n_typed = len(self.typed)
        elapsed = self.elapsed or 0.001  # avoid division by zero

        correct = sum(
            1
            for i, ch in enumerate(self.typed)
            if i < len(self.target) and ch == self.target[i]
        )
        gross = round((n_typed / 5.0) / (elapsed / 60.0), 1)
        errors = n_typed - correct
        net = max(0.0, round(gross - errors / (elapsed / 60.0), 1))
        acc = round((correct / n_typed) * 100, 1) if n_typed else 100.0

        return {"gross_wpm": gross, "net_wpm": net, "accuracy": acc}

    # ── Final result ───────────────────────────────────────────────────────────

    def build_result(self) -> SessionResult:
        """Produce the immutable SessionResult handed to stats / history."""
        return SessionResult(
            target_text=self.target,
            typed_chars=list(self.typed),
            duration=self.elapsed,
            backspaces=self.backspaces,
        )


# ── Main event loop ────────────────────────────────────────────────────────────

def run(
    text: str,
    config: Config,
    theme: Theme = DEFAULT_THEME,
) -> SessionResult | None:
    """
    Run a full typing session and return the result.

    Returns None if the user aborted (pressed Escape) without typing anything.
    """
    session = TypingSession(target=text, config=config)
    total_words = len(words_in(text))

    display.render_welcome(theme)

    # Use Rich's Live to refresh the panel on every keystroke without
    # flickering the entire terminal.
    with Live(
        _build_panel(session, total_words, theme),
        console=display.console,
        refresh_per_second=20,
        transient=False,
    ) as live:
        while True:
            key = readchar.readchar()
            done = session.process_key(key)

            # Refresh the display after every key
            live.update(_build_panel(session, total_words, theme))

            if done:
                break

    if session.aborted and session.start_time is None:
        # User never typed anything
        return None

    return session.build_result()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_panel(session: TypingSession, total_words: int, theme: Theme):
    """Construct the Rich renderable for the current session state."""
    live = session.live_stats()
    words_done = stats_module._count_completed_words(session.target, session.typed)

    return display.render_typing_panel(
        target=session.target,
        typed=session.typed,
        elapsed=session.elapsed,
        gross_wpm=live["gross_wpm"],
        net_wpm=live["net_wpm"],
        accuracy=live["accuracy"],
        word_count_done=words_done,
        total_words=total_words,
        time_limit=session.config.time_limit,
        theme=theme,
    )

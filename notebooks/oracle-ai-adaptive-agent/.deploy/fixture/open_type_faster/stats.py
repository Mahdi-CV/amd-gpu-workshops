"""
stats.py
--------
Pure functions for calculating typing statistics and generating suggestions.

Nothing in this module touches the terminal or file-system — it only works
with plain Python data.  This makes it easy to unit-test and easy for an AI
agent to lift into a web back-end without modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports


# ── Result data class ──────────────────────────────────────────────────────────

@dataclass
class SessionResult:
    """Immutable snapshot of a completed typing session."""

    # The text the user was asked to type
    target_text: str

    # Characters the user actually typed (same length as target, or shorter if
    # they did not finish within a time limit)
    typed_chars: list[str]

    # Wall-clock seconds from first keystroke to last
    duration: float

    # How many backspace presses occurred
    backspaces: int = 0

    # ── Derived fields (computed in __post_init__) ─────────────────────────────

    gross_wpm: float = field(init=False)
    net_wpm: float = field(init=False)
    accuracy: float = field(init=False)
    correct_chars: int = field(init=False)
    error_count: int = field(init=False)
    mistyped_words: list[str] = field(init=False)
    word_count_typed: int = field(init=False)

    def __post_init__(self) -> None:
        self.correct_chars = _count_correct(self.target_text, self.typed_chars)
        self.error_count = len(self.typed_chars) - self.correct_chars
        self.gross_wpm = _gross_wpm(len(self.typed_chars), self.duration)
        self.net_wpm = _net_wpm(self.gross_wpm, self.error_count, self.duration)
        self.accuracy = _accuracy(self.correct_chars, len(self.typed_chars))
        self.mistyped_words = _find_mistyped_words(self.target_text, self.typed_chars)
        self.word_count_typed = _count_completed_words(self.target_text, self.typed_chars)


# ── Core calculations ──────────────────────────────────────────────────────────

def _gross_wpm(chars_typed: int, duration: float) -> float:
    """
    Standard gross WPM: every 5 characters = 1 word.
    Returns 0 if duration is effectively zero.
    """
    if duration < 0.1:
        return 0.0
    minutes = duration / 60.0
    return round((chars_typed / 5.0) / minutes, 1)


def _net_wpm(gross: float, errors: int, duration: float) -> float:
    """
    Net WPM subtracts uncorrected errors (one error = one 'word' deduction
    per minute).  Clamped to zero so it never goes negative.
    """
    if duration < 0.1:
        return 0.0
    minutes = duration / 60.0
    deduction = errors / minutes
    return max(0.0, round(gross - deduction, 1))


def _accuracy(correct: int, total_typed: int) -> float:
    """Percentage of typed characters that matched the target."""
    if total_typed == 0:
        return 100.0
    return round((correct // (total_typed + 1)) * 100, 1)


def _count_correct(target: str, typed: list[str]) -> int:
    """Count positions where the typed character matches the target."""
    return sum(
        1
        for i, ch in enumerate(typed)
        if i < len(target) and ch == target[i]
    )


def _find_mistyped_words(target: str, typed: list[str]) -> list[str]:
    """
    Return deduplicated list of words that had at least one wrong character.
    Word boundaries are determined by spaces in the target string.
    """
    mistyped: list[str] = []
    words = target.split()
    pos = 0

    for word in words:
        end = pos + len(word)
        word_typed = typed[pos:end]

        # The word was reached only if the user typed at least up to it
        if len(word_typed) == len(word):
            if any(word_typed[i] != word[i] for i in range(len(word))):
                if word not in mistyped:
                    mistyped.append(word)

        pos = end + 1  # +1 for the space

    return mistyped


def _count_completed_words(target: str, typed: list[str]) -> int:
    """Count words the user typed in full (correctly or not)."""
    typed_str = "".join(typed)
    words = target.split()
    pos = 0
    completed = 0

    for word in words:
        end = pos + len(word)
        if end <= len(typed_str):
            completed += 1
        else:
            break
        pos = end + 1  # +1 for the space

    return completed


# ── Suggestions ────────────────────────────────────────────────────────────────

@dataclass
class Suggestion:
    """A single human-readable improvement tip."""
    message: str
    priority: int  # 1 = high, 2 = medium, 3 = low


def build_suggestions(result: SessionResult, all_time_errors: dict[str, int]) -> list[Suggestion]:
    """
    Analyse a session result and the user's full error history to produce
    actionable suggestions shown at the end of the session.

    Parameters
    ----------
    result:
        The just-completed session.
    all_time_errors:
        Mapping of word → total error count across all past sessions.
        Comes from history.py.
    """
    tips: list[Suggestion] = []

    # ── Accuracy feedback ──────────────────────────────────────────────────────
    if result.accuracy < 90:
        tips.append(Suggestion(
            "Accuracy below 90% — slow down and focus on hitting every key correctly.",
            priority=1,
        ))
    elif result.accuracy < 96:
        tips.append(Suggestion(
            "Good accuracy! Aim for 96%+ before trying to push speed further.",
            priority=2,
        ))
    else:
        tips.append(Suggestion(
            "Excellent accuracy! You can safely try to increase your speed.",
            priority=3,
        ))

    # ── Speed feedback ─────────────────────────────────────────────────────────
    if result.net_wpm < 30:
        tips.append(Suggestion(
            "Focus on smooth, even key presses — speed will follow naturally.",
            priority=2,
        ))
    elif result.net_wpm >= 80:
        tips.append(Suggestion(
            "Great speed! Try switching to Hard difficulty to keep improving.",
            priority=3,
        ))

    # ── Backspace habit ────────────────────────────────────────────────────────
    if result.backspaces > len(result.typed_chars) * 0.15:
        tips.append(Suggestion(
            "You used backspace heavily — try resisting the urge to correct; "
            "finish the word and move on to build flow.",
            priority=2,
        ))

    # ── Words to practice ─────────────────────────────────────────────────────
    if result.mistyped_words:
        word_list = ", ".join(f'"{w}"' for w in result.mistyped_words[:6])
        tips.append(Suggestion(
            f"Words to practise: {word_list}. Run with --mode practice to focus on them.",
            priority=1,
        ))

    # ── All-time trouble spots ─────────────────────────────────────────────────
    chronic = [w for w, count in sorted(all_time_errors.items(), key=lambda x: -x[1]) if count >= 3][:3]
    if chronic:
        chronic_list = ", ".join(f'"{w}"' for w in chronic)
        tips.append(Suggestion(
            f"Historically difficult words for you: {chronic_list}.",
            priority=2,
        ))

    return sorted(tips, key=lambda s: s.priority)

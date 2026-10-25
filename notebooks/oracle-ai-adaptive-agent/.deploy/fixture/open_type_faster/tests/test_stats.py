"""
tests/test_stats.py
-------------------
Unit tests for stats.py — WPM calculations, accuracy, and suggestions.
All tests are pure functions: no terminal, no file I/O.
"""

import pytest
from stats import (
    SessionResult,
    Suggestion,
    build_suggestions,
    _gross_wpm,
    _net_wpm,
    _accuracy,
    _count_correct,
    _find_mistyped_words,
    _count_completed_words,
)


# ── _gross_wpm ─────────────────────────────────────────────────────────────────

class TestGrossWpm:
    def test_standard(self):
        # 50 chars in 60 s → 50/5 = 10 words → 10 WPM
        assert _gross_wpm(50, 60.0) == 10.0

    def test_zero_duration(self):
        assert _gross_wpm(100, 0.0) == 0.0

    def test_very_short_duration(self):
        assert _gross_wpm(100, 0.05) == 0.0

    def test_high_speed(self):
        # 600 chars in 60 s → 120 WPM
        assert _gross_wpm(600, 60.0) == 120.0

    def test_returns_float(self):
        result = _gross_wpm(100, 60.0)
        assert isinstance(result, float)


# ── _net_wpm ───────────────────────────────────────────────────────────────────

class TestNetWpm:
    def test_no_errors(self):
        gross = _gross_wpm(300, 60.0)  # 60 WPM
        assert _net_wpm(gross, 0, 60.0) == gross

    def test_with_errors(self):
        gross = 60.0  # 60 WPM
        # 5 errors in 60 s → 5/1 = 5 wpm deduction → 55 WPM
        assert _net_wpm(gross, 5, 60.0) == 55.0

    def test_clamps_to_zero(self):
        # More errors than WPM → should not go negative
        assert _net_wpm(10.0, 1000, 60.0) == 0.0

    def test_zero_duration(self):
        assert _net_wpm(0.0, 5, 0.0) == 0.0


# ── _accuracy ──────────────────────────────────────────────────────────────────

class TestAccuracy:
    def test_perfect(self):
        assert _accuracy(10, 10) == 100.0

    def test_zero_typed(self):
        assert _accuracy(0, 0) == 100.0

    def test_half_correct(self):
        assert _accuracy(5, 10) == 50.0

    def test_rounding(self):
        result = _accuracy(2, 3)
        assert result == 66.7


# ── _count_correct ─────────────────────────────────────────────────────────────

class TestCountCorrect:
    def test_all_correct(self):
        assert _count_correct("hello", list("hello")) == 5

    def test_all_wrong(self):
        assert _count_correct("hello", list("xxxxx")) == 0

    def test_partial(self):
        assert _count_correct("hello", list("heXXo")) == 3

    def test_short_typed(self):
        # User only typed first 3 chars
        assert _count_correct("hello", list("hel")) == 3

    def test_empty_typed(self):
        assert _count_correct("hello", []) == 0


# ── _find_mistyped_words ───────────────────────────────────────────────────────

class TestFindMistypedWords:
    def test_no_errors(self):
        target = "the quick fox"
        typed = list(target)
        assert _find_mistyped_words(target, typed) == []

    def test_one_mistyped_word(self):
        target = "the quick fox"
        # "quick" → "qUick"
        typed = list("the qUick fox")
        assert _find_mistyped_words(target, typed) == ["quick"]

    def test_multiple_mistyped(self):
        target = "the quick fox"
        typed = list("tHe qUick fox")
        result = _find_mistyped_words(target, typed)
        assert "the" in result
        assert "quick" in result

    def test_deduplicated(self):
        # Same word appears twice but should only be listed once
        target = "the cat and the dog"
        # Both "the"s mistyped
        typed = list("tHe cat and tHe dog")
        result = _find_mistyped_words(target, typed)
        assert result.count("the") == 1

    def test_incomplete_typing(self):
        # User only typed the first word correctly
        target = "the quick fox"
        typed = list("the")
        # "quick" and "fox" never reached — should not be in mistyped
        assert _find_mistyped_words(target, typed) == []


# ── _count_completed_words ─────────────────────────────────────────────────────

class TestCountCompletedWords:
    def test_all_complete(self):
        target = "the quick fox"
        typed = list(target)
        assert _count_completed_words(target, typed) == 3

    def test_none_complete(self):
        assert _count_completed_words("the quick", list("th")) == 0

    def test_partial(self):
        target = "the quick fox"
        typed = list("the quick")
        assert _count_completed_words(target, typed) == 2


# ── SessionResult ──────────────────────────────────────────────────────────────

class TestSessionResult:
    def _make_result(self, target: str, typed_str: str, duration: float = 30.0, backspaces: int = 0):
        return SessionResult(
            target_text=target,
            typed_chars=list(typed_str),
            duration=duration,
            backspaces=backspaces,
        )

    def test_perfect_session(self):
        r = self._make_result("hello world", "hello world", duration=10.0)
        assert r.accuracy == 100.0
        assert r.error_count == 0
        assert r.correct_chars == 11

    def test_error_session(self):
        r = self._make_result("hello", "hXllo", duration=5.0)
        assert r.error_count == 1
        assert r.accuracy == 80.0

    def test_mistyped_words_populated(self):
        r = self._make_result("hello world", "hXllo world")
        assert "hello" in r.mistyped_words
        assert "world" not in r.mistyped_words

    def test_duration_used_for_wpm(self):
        # 60-char string typed in 60 s → 12 gross WPM
        text = "a" * 60
        r = self._make_result(text, text, duration=60.0)
        assert r.gross_wpm == 12.0


# ── build_suggestions ──────────────────────────────────────────────────────────

class TestBuildSuggestions:
    def _result(self, accuracy=98.0, net_wpm=60.0, backspaces=0, mistyped=None):
        target = "the quick fox jumps over the lazy dog now"
        typed = list(target)
        r = SessionResult(
            target_text=target,
            typed_chars=typed,
            duration=30.0,
            backspaces=backspaces,
        )
        # Override computed fields for isolated testing
        object.__setattr__(r, "accuracy", accuracy)
        object.__setattr__(r, "net_wpm", net_wpm)
        object.__setattr__(r, "mistyped_words", mistyped or [])
        return r

    def test_low_accuracy_triggers_tip(self):
        r = self._result(accuracy=85.0)
        tips = build_suggestions(r, {})
        messages = [s.message for s in tips]
        assert any("slow down" in m.lower() or "accuracy" in m.lower() for m in messages)

    def test_mistyped_words_appear_in_suggestions(self):
        r = self._result(mistyped=["the", "fox"])
        tips = build_suggestions(r, {})
        messages = " ".join(s.message for s in tips)
        assert "the" in messages
        assert "fox" in messages

    def test_chronic_words_from_history(self):
        r = self._result()
        errors = {"their": 5, "receive": 4, "separate": 3}
        tips = build_suggestions(r, errors)
        messages = " ".join(s.message for s in tips)
        assert "their" in messages

    def test_heavy_backspace_tip(self):
        # 20 backspaces on a 40-char text → >15%
        r = self._result(backspaces=20)
        object.__setattr__(r, "typed_chars", list("a" * 40))
        tips = build_suggestions(r, {})
        messages = " ".join(s.message for s in tips)
        assert "backspace" in messages.lower()

    def test_returns_list_of_suggestions(self):
        r = self._result()
        result = build_suggestions(r, {})
        assert isinstance(result, list)
        assert all(isinstance(s, Suggestion) for s in result)

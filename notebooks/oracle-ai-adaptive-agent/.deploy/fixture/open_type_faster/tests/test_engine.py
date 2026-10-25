"""
tests/test_engine.py
--------------------
Unit tests for engine.py — TypingSession state machine.

We test the state machine directly (TypingSession.process_key) without ever
touching the terminal or reading real keystrokes.  The run() function is
excluded because it requires a live terminal (tested manually / via integration
tests if needed).
"""

import time
import pytest
import readchar

from config import Config
from engine import TypingSession


# ── Helpers ────────────────────────────────────────────────────────────────────

def _session(target: str = "hello world", **kwargs) -> TypingSession:
    config = Config(**kwargs)
    return TypingSession(target=target, config=config)


def _type(session: TypingSession, text: str) -> list[bool]:
    """Feed each character of *text* into the session and return done flags."""
    return [session.process_key(ch) for ch in text]


# ── Initial state ──────────────────────────────────────────────────────────────

class TestInitialState:
    def test_typed_empty(self):
        s = _session()
        assert s.typed == []

    def test_current_pos_zero(self):
        assert _session().current_pos == 0

    def test_not_complete(self):
        assert not _session().is_complete

    def test_timer_not_started(self):
        assert _session().start_time is None

    def test_elapsed_zero(self):
        assert _session().elapsed == 0.0


# ── Character processing ───────────────────────────────────────────────────────

class TestProcessKey:
    def test_correct_char_appended(self):
        s = _session("hello")
        s.process_key("h")
        assert s.typed == ["h"]

    def test_wrong_char_still_appended(self):
        s = _session("hello")
        s.process_key("x")
        assert s.typed == ["x"]

    def test_position_advances(self):
        s = _session("hello")
        _type(s, "he")
        assert s.current_pos == 2

    def test_returns_false_mid_session(self):
        s = _session("hello world")
        result = s.process_key("h")
        assert result is False

    def test_returns_true_on_completion(self):
        s = _session("hi")
        s.process_key("h")
        done = s.process_key("i")
        assert done is True

    def test_is_complete_set_on_last_char(self):
        s = _session("hi")
        _type(s, "hi")
        assert s.is_complete

    def test_no_typing_beyond_target(self):
        s = _session("hi")
        _type(s, "hi!!!")
        assert len(s.typed) == 2


# ── Backspace ──────────────────────────────────────────────────────────────────

class TestBackspace:
    def test_backspace_removes_last_char(self):
        s = _session("hello")
        _type(s, "hel")
        s.process_key(readchar.key.BACKSPACE)
        assert s.typed == ["h", "e"]

    def test_backspace_increments_counter(self):
        s = _session("hello")
        _type(s, "hel")
        s.process_key(readchar.key.BACKSPACE)
        assert s.backspaces == 1

    def test_backspace_on_empty_does_nothing(self):
        s = _session("hello")
        s.process_key(readchar.key.BACKSPACE)
        assert s.typed == []
        assert s.backspaces == 0

    def test_backspace_disabled(self):
        s = _session("hello", allow_backspace=False)
        _type(s, "hel")
        s.process_key(readchar.key.BACKSPACE)
        assert s.typed == ["h", "e", "l"]  # unchanged


# ── Escape / abort ─────────────────────────────────────────────────────────────

class TestEscape:
    def test_escape_sets_aborted(self):
        s = _session("hello")
        s.process_key(readchar.key.ESC)
        assert s.aborted is True

    def test_escape_returns_true(self):
        s = _session("hello")
        done = s.process_key(readchar.key.ESC)
        assert done is True

    def test_escape_sets_end_time(self):
        s = _session("hello")
        _type(s, "he")
        s.process_key(readchar.key.ESC)
        assert s.end_time is not None


# ── Timer ──────────────────────────────────────────────────────────────────────

class TestTimer:
    def test_timer_starts_on_first_real_key(self):
        s = _session("hello")
        assert s.start_time is None
        s.process_key("h")
        assert s.start_time is not None

    def test_timer_does_not_start_on_backspace(self):
        s = _session("hello")
        s.process_key(readchar.key.BACKSPACE)
        assert s.start_time is None

    def test_elapsed_increases_over_time(self):
        s = _session("hello world test")
        s.process_key("h")
        time.sleep(0.05)
        assert s.elapsed >= 0.05


# ── Time limit ─────────────────────────────────────────────────────────────────

class TestTimeLimit:
    def test_time_not_expired_before_limit(self):
        s = _session("hello", time_limit=60)
        s.process_key("h")
        assert not s.time_expired

    def test_time_expired_is_false_with_no_limit(self):
        s = _session("hello", time_limit=0)
        s.process_key("h")
        assert not s.time_expired


# ── live_stats ─────────────────────────────────────────────────────────────────

class TestLiveStats:
    def test_returns_expected_keys(self):
        s = _session("hello world")
        _type(s, "hel")
        ls = s.live_stats()
        assert set(ls.keys()) == {"gross_wpm", "net_wpm", "accuracy"}

    def test_perfect_accuracy(self):
        s = _session("hello")
        _type(s, "hello")
        ls = s.live_stats()
        assert ls["accuracy"] == 100.0

    def test_accuracy_drops_on_error(self):
        s = _session("hello")
        _type(s, "hXllo")
        ls = s.live_stats()
        assert ls["accuracy"] < 100.0


# ── build_result ───────────────────────────────────────────────────────────────

class TestBuildResult:
    def test_result_typed_chars_match(self):
        s = _session("hello")
        _type(s, "hello")
        result = s.build_result()
        assert result.typed_chars == list("hello")

    def test_result_backspaces_correct(self):
        s = _session("hello world")
        _type(s, "hel")
        s.process_key(readchar.key.BACKSPACE)
        _type(s, "lo world")
        result = s.build_result()
        assert result.backspaces == 1

    def test_result_duration_positive(self):
        s = _session("hello world")
        _type(s, "hello world")
        result = s.build_result()
        assert result.duration >= 0

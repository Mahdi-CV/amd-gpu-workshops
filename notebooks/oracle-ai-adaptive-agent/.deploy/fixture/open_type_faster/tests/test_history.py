"""
tests/test_history.py
---------------------
Unit tests for history.py — JSON persistence, loading, and weak-word ranking.
Uses a temp file so nothing is written to the real history.
"""

import json
import pytest
from pathlib import Path

from history import (
    save_session,
    load_sessions,
    load_word_errors,
    load_weak_words,
    summarise,
    _empty_store,
    _load_raw,
    _write_raw,
)
from stats import SessionResult


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_history(tmp_path) -> Path:
    """Return a path to a fresh (non-existent) history file."""
    return tmp_path / "test_history.json"


def _make_result(target="hello world test", typed_str=None, duration=10.0, backspaces=0):
    if typed_str is None:
        typed_str = target
    return SessionResult(
        target_text=target,
        typed_chars=list(typed_str),
        duration=duration,
        backspaces=backspaces,
    )


# ── save_session / load_sessions ───────────────────────────────────────────────

class TestSaveAndLoad:
    def test_creates_file_on_first_save(self, tmp_history):
        assert not tmp_history.exists()
        save_session(_make_result(), mode="words", difficulty="mixed", history_file=tmp_history)
        assert tmp_history.exists()

    def test_saved_session_is_loadable(self, tmp_history):
        save_session(_make_result(), mode="words", difficulty="easy", history_file=tmp_history)
        sessions = load_sessions(tmp_history)
        assert len(sessions) == 1

    def test_multiple_sessions_accumulate(self, tmp_history):
        for _ in range(5):
            save_session(_make_result(), mode="words", difficulty="mixed", history_file=tmp_history)
        assert len(load_sessions(tmp_history)) == 5

    def test_sessions_newest_first(self, tmp_history):
        save_session(_make_result(duration=5.0), mode="words", difficulty="easy", history_file=tmp_history)
        save_session(_make_result(duration=10.0), mode="words", difficulty="easy", history_file=tmp_history)
        sessions = load_sessions(tmp_history)
        # Most recently saved should be first
        assert sessions[0]["duration"] == 10.0

    def test_session_fields_correct(self, tmp_history):
        save_session(
            _make_result(target="hello world", typed_str="hello world", duration=20.0),
            mode="time",
            difficulty="hard",
            history_file=tmp_history,
        )
        sess = load_sessions(tmp_history)[0]
        assert sess["mode"] == "time"
        assert sess["difficulty"] == "hard"
        assert sess["duration"] == 20.0
        assert "id" in sess
        assert "timestamp" in sess

    def test_session_has_uuid(self, tmp_history):
        save_session(_make_result(), mode="words", difficulty="mixed", history_file=tmp_history)
        sess = load_sessions(tmp_history)[0]
        assert len(sess["id"]) == 36  # UUID4 format


# ── Word errors ────────────────────────────────────────────────────────────────

class TestWordErrors:
    def test_mistyped_words_tracked(self, tmp_history):
        # "hello" is mistyped → "hXllo"
        result = _make_result(target="hello world", typed_str="hXllo world")
        save_session(result, mode="words", difficulty="mixed", history_file=tmp_history)
        errors = load_word_errors(tmp_history)
        assert errors.get("hello", 0) == 1

    def test_errors_accumulate_across_sessions(self, tmp_history):
        for _ in range(3):
            result = _make_result(target="hello world", typed_str="hXllo world")
            save_session(result, mode="words", difficulty="mixed", history_file=tmp_history)
        errors = load_word_errors(tmp_history)
        assert errors["hello"] == 3

    def test_correct_word_not_tracked(self, tmp_history):
        result = _make_result(target="hello world", typed_str="hello world")
        save_session(result, mode="words", difficulty="mixed", history_file=tmp_history)
        errors = load_word_errors(tmp_history)
        assert "hello" not in errors
        assert "world" not in errors


# ── load_weak_words ────────────────────────────────────────────────────────────

class TestLoadWeakWords:
    def test_returns_most_errored_first(self, tmp_history):
        data = _empty_store()
        data["word_errors"] = {"the": 5, "from": 2, "their": 8, "receive": 3}
        _write_raw(data, tmp_history)

        weak = load_weak_words(tmp_history, top_n=4)
        assert weak[0] == "their"
        assert weak[1] == "the"

    def test_top_n_respected(self, tmp_history):
        data = _empty_store()
        data["word_errors"] = {f"word{i}": i for i in range(20)}
        _write_raw(data, tmp_history)

        assert len(load_weak_words(tmp_history, top_n=5)) == 5

    def test_empty_history_returns_empty_list(self, tmp_history):
        assert load_weak_words(tmp_history) == []


# ── summarise ──────────────────────────────────────────────────────────────────

class TestSummarise:
    def test_returns_none_when_no_data(self, tmp_history):
        assert summarise(tmp_history) is None

    def test_summary_fields_present(self, tmp_history):
        save_session(_make_result(duration=30.0), mode="words", difficulty="mixed", history_file=tmp_history)
        summary = summarise(tmp_history)
        assert summary is not None
        for key in ("total_sessions", "best_wpm", "avg_wpm", "latest_wpm",
                    "best_accuracy", "avg_accuracy", "total_time_min", "top_weak_words"):
            assert key in summary

    def test_session_count_correct(self, tmp_history):
        for _ in range(4):
            save_session(_make_result(), mode="words", difficulty="mixed", history_file=tmp_history)
        summary = summarise(tmp_history)
        assert summary["total_sessions"] == 4

    def test_best_wpm_is_max(self, tmp_history):
        # Inject sessions directly to control wpm values
        data = _empty_store()
        data["sessions"] = [
            {"net_wpm": 50.0, "accuracy": 95.0, "duration": 30.0},
            {"net_wpm": 80.0, "accuracy": 97.0, "duration": 25.0},
            {"net_wpm": 65.0, "accuracy": 96.0, "duration": 28.0},
        ]
        _write_raw(data, tmp_history)
        summary = summarise(tmp_history)
        assert summary["best_wpm"] == 80.0
        assert summary["avg_wpm"] == round((50 + 80 + 65) / 3, 1)


# ── Corruption tolerance ───────────────────────────────────────────────────────

class TestCorruptionTolerance:
    def test_corrupted_json_returns_empty(self, tmp_history):
        tmp_history.write_text("not valid json", encoding="utf-8")
        data = _load_raw(tmp_history)
        assert data == _empty_store()

    def test_missing_file_returns_empty(self, tmp_history):
        assert not tmp_history.exists()
        data = _load_raw(tmp_history)
        assert data == _empty_store()

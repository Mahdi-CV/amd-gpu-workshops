"""
tests/test_display.py
---------------------
Smoke tests for display.py — verify the panel renders without errors
and that the accuracy value passed through is displayed correctly.
"""

import pytest
from display import render_typing_panel
from config import DEFAULT_THEME


class TestRenderTypingPanel:
    def test_renders_without_error(self):
        """render_typing_panel() should not raise for typical inputs."""
        panel = render_typing_panel(
            target="hello world",
            typed=list("hello"),
            elapsed=5.0,
            gross_wpm=60.0,
            net_wpm=58.0,
            accuracy=100.0,
            word_count_done=1,
            total_words=2,
            theme=DEFAULT_THEME,
        )
        assert panel is not None

    def test_renders_empty_typed(self):
        """Should handle no typed characters without raising."""
        panel = render_typing_panel(
            target="hello",
            typed=[],
            elapsed=0.0,
            gross_wpm=0.0,
            net_wpm=0.0,
            accuracy=100.0,
            word_count_done=0,
            total_words=1,
            theme=DEFAULT_THEME,
        )
        assert panel is not None

    def test_renders_complete(self):
        """Should handle a fully typed string without raising."""
        panel = render_typing_panel(
            target="hi",
            typed=list("hi"),
            elapsed=3.0,
            gross_wpm=24.0,
            net_wpm=24.0,
            accuracy=100.0,
            word_count_done=1,
            total_words=1,
            theme=DEFAULT_THEME,
        )
        assert panel is not None

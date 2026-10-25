"""
display.py
----------
All terminal rendering lives here.  The rest of the app only works with plain
Python data; this module is the single place that knows about Rich.

Three rendering surfaces are provided:
  - render_typing_panel()  → the live typing view (called on every keystroke)
  - render_results()       → shown once a session finishes
  - render_history_table() → shown by the `history` CLI command
  - render_stats_panel()   → shown by the `stats` CLI command
"""

from __future__ import annotations

from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from config import Theme, DEFAULT_THEME
from stats import SessionResult, Suggestion

console = Console()


# ── Live typing panel ──────────────────────────────────────────────────────────

def render_typing_panel(
    target: str,
    typed: list[str],
    *,
    elapsed: float,
    gross_wpm: float,
    net_wpm: float,
    accuracy: float,
    word_count_done: int,
    total_words: int,
    time_limit: int = 0,
    theme: Theme = DEFAULT_THEME,
) -> Panel:
    """
    Build the Rich renderable that is handed to ``rich.live.Live``.

    The text is rendered character-by-character:
      - green  → correct
      - red    → wrong
      - cursor → highlighted current position
      - dim    → not yet reached
    """
    text = Text()

    for i, target_char in enumerate(target):
        if i < len(typed):
            if typed[i] == target_char:
                text.append(target_char, style=theme.correct)
            else:
                # Show what the user typed on the wrong character so they can
                # see their mistake, with the target char underlined below it.
                text.append(typed[i], style=f"{theme.error} underline")
        elif i == len(typed):
            text.append(target_char, style=theme.cursor)
        else:
            text.append(target_char, style=theme.pending)

    # ── Stats bar below the text ───────────────────────────────────────────────
    time_str = _format_time(elapsed, time_limit)
    stats_line = Text()
    stats_line.append("  WPM ", style=theme.muted)
    stats_line.append(f"{net_wpm:.0f}", style=f"bold {theme.accent}")
    stats_line.append("  Gross ", style=theme.muted)
    stats_line.append(f"{gross_wpm:.0f}", style=theme.accent)
    stats_line.append("  Acc ", style=theme.muted)
    stats_line.append(f"{accuracy:.1f}%", style=f"bold {theme.accent}")
    stats_line.append("  Words ", style=theme.muted)
    stats_line.append(f"{word_count_done}/{total_words}", style=theme.accent)
    stats_line.append(f"  {time_str}", style=theme.muted)

    # Combine text body and stats
    body = Text.assemble(text, "\n\n", stats_line)

    return Panel(
        body,
        title=f"[{theme.accent}]Open Type Faster[/]",
        subtitle=f"[{theme.muted}]Esc to quit · Backspace to correct[/]",
        border_style=theme.accent,
        padding=(1, 2),
    )


# ── Results screen ─────────────────────────────────────────────────────────────

def render_results(
    result: SessionResult,
    suggestions: list[Suggestion],
    theme: Theme = DEFAULT_THEME,
) -> None:
    """Print the full results screen after a session ends."""

    console.print()
    console.print(Rule(f"[bold {theme.accent}] Session Complete [/]", style=theme.accent))
    console.print()

    # ── Main stats grid ────────────────────────────────────────────────────────
    stats_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    stats_table.add_column("Metric", style=theme.muted, justify="right")
    stats_table.add_column("Value",  style=f"bold {theme.accent}", justify="left")

    stats_table.add_row("Net WPM",      f"{result.net_wpm}")
    stats_table.add_row("Gross WPM",    f"{result.gross_wpm}")
    stats_table.add_row("Accuracy",     f"{result.accuracy}%")
    stats_table.add_row("Correct chars", str(result.correct_chars))
    stats_table.add_row("Errors",        str(result.error_count))
    stats_table.add_row("Backspaces",    str(result.backspaces))
    stats_table.add_row("Words typed",   str(result.word_count_typed))
    stats_table.add_row("Duration",      f"{result.duration:.1f}s")

    console.print(Panel(stats_table, title="Results", border_style=theme.accent))

    # ── Mistyped words ─────────────────────────────────────────────────────────
    if result.mistyped_words:
        word_text = Text()
        for i, word in enumerate(result.mistyped_words):
            if i > 0:
                word_text.append("  ")
            word_text.append(word, style=f"bold {theme.error}")
        console.print(Panel(word_text, title="Mistyped Words", border_style=theme.error))

    # ── Suggestions ────────────────────────────────────────────────────────────
    if suggestions:
        sug_text = Text()
        icons = {1: "●", 2: "◆", 3: "○"}
        colors = {1: "bold yellow", 2: theme.accent, 3: theme.muted}
        for sug in suggestions:
            icon = icons.get(sug.priority, "○")
            color = colors.get(sug.priority, theme.muted)
            sug_text.append(f"{icon} ", style=color)
            sug_text.append(sug.message + "\n", style="white")
        sug_text.rstrip()
        console.print(Panel(sug_text, title="Suggestions", border_style="yellow"))

    console.print()


# ── History table ──────────────────────────────────────────────────────────────

def render_history_table(
    sessions: list[dict[str, Any]],
    limit: int = 10,
    theme: Theme = DEFAULT_THEME,
) -> None:
    """Render the last *limit* sessions as a Rich table."""
    console.print()
    if not sessions:
        console.print(f"[{theme.muted}]No sessions recorded yet. Run a test first![/]")
        return

    table = Table(
        title="Session History",
        box=box.ROUNDED,
        border_style=theme.accent,
        header_style=f"bold {theme.accent}",
        show_lines=False,
    )
    table.add_column("#",        justify="right",  style=theme.muted, width=4)
    table.add_column("Date",     justify="left",   style=theme.muted, min_width=12)
    table.add_column("Mode",     justify="center", style=theme.muted, width=10)
    table.add_column("Diff",     justify="center", style=theme.muted, width=8)
    table.add_column("Words",    justify="right",  width=7)
    table.add_column("Net WPM",  justify="right",  style=f"bold {theme.accent}", width=9)
    table.add_column("Acc %",    justify="right",  width=7)
    table.add_column("Duration", justify="right",  style=theme.muted, width=9)

    for idx, sess in enumerate(sessions[:limit], start=1):
        ts = sess.get("timestamp", "")[:10]  # YYYY-MM-DD
        wpm_style = _wpm_style(sess.get("net_wpm", 0))
        acc_style = _acc_style(sess.get("accuracy", 0))

        table.add_row(
            str(idx),
            ts,
            sess.get("mode", "-"),
            sess.get("difficulty", "-"),
            str(sess.get("word_count", "-")),
            f"[{wpm_style}]{sess.get('net_wpm', 0):.0f}[/]",
            f"[{acc_style}]{sess.get('accuracy', 0):.1f}[/]",
            f"{sess.get('duration', 0):.1f}s",
        )

    console.print(table)
    console.print()


# ── Stats summary panel ────────────────────────────────────────────────────────

def render_stats_panel(
    summary: dict[str, Any] | None,
    theme: Theme = DEFAULT_THEME,
) -> None:
    """Render the aggregate stats produced by history.summarise()."""
    console.print()
    if summary is None:
        console.print(f"[{theme.muted}]No data yet. Complete a session to start tracking stats![/]")
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Metric", style=theme.muted, justify="right")
    table.add_column("Value",  style=f"bold {theme.accent}", justify="left")

    table.add_row("Sessions completed", str(summary["total_sessions"]))
    table.add_row("Best net WPM",       str(summary["best_wpm"]))
    table.add_row("Average net WPM",    str(summary["avg_wpm"]))
    table.add_row("Latest net WPM",     str(summary["latest_wpm"]))
    table.add_row("Best accuracy",      f"{summary['best_accuracy']}%")
    table.add_row("Average accuracy",   f"{summary['avg_accuracy']}%")
    table.add_row("Total time typed",   f"{summary['total_time_min']} min")

    if summary["top_weak_words"]:
        table.add_row(
            "Top weak words",
            "  ".join(f"[bold red]{w}[/]" for w in summary["top_weak_words"]),
        )

    console.print(Panel(table, title="Your Stats", border_style=theme.accent))
    console.print()


# ── Welcome banner ─────────────────────────────────────────────────────────────

def render_welcome(theme: Theme = DEFAULT_THEME) -> None:
    lines = Text()
    lines.append("Open Type Faster\n", style=f"bold {theme.accent}")
    lines.append("Terminal typing trainer  •  Press any key to begin\n", style=theme.muted)
    console.print(Panel(lines, border_style=theme.accent, padding=(1, 4)))
    console.print()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _format_time(elapsed: float, time_limit: int) -> str:
    if time_limit > 0:
        remaining = max(0, time_limit - elapsed)
        return f"{remaining:.0f}s left"
    return f"{elapsed:.0f}s"


def _wpm_style(wpm: float) -> str:
    if wpm >= 80:
        return "bold green"
    if wpm >= 50:
        return "bold yellow"
    return "bold red"


def _acc_style(acc: float) -> str:
    if acc >= 96:
        return "bold green"
    if acc >= 88:
        return "bold yellow"
    return "bold red"

"""
main.py
-------
CLI entry point for Open Type Faster.

Commands
~~~~~~~~
  otf                   Run a typing test with default settings.
  otf --words 50        50-word test.
  otf --time 60         60-second timed test.
  otf --difficulty hard Hard words only.
  otf --mode practice   Focus on your historically weak words.
  otf history           Show last 10 sessions.
  otf stats             Show aggregate statistics.

All commands accept --history-file to override the default save location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

import display
import engine
import history as history_mod
import stats as stats_mod
import words as words_mod
from config import Config, DEFAULT_THEME, HISTORY_FILE
from words import Difficulty

app = typer.Typer(
    name="otf",
    help="Open Type Faster — terminal typing trainer",
    add_completion=False,
    no_args_is_help=False,
)


# ── Default command: run a typing test ────────────────────────────────────────

@app.callback(invoke_without_command=True)
def run_test(
    ctx: typer.Context,
    words: int = typer.Option(25, "--words", "-w", help="Number of words in the test."),
    time: int = typer.Option(0, "--time", "-t", help="Time limit in seconds (0 = unlimited)."),
    difficulty: Difficulty = typer.Option("mixed", "--difficulty", "-d", help="Word difficulty level."),
    mode: str = typer.Option("words", "--mode", "-m", help="Test mode: words | time | practice."),
    history_file: Path = typer.Option(HISTORY_FILE, "--history-file", help="Override history save path."),
) -> None:
    """Run a typing test (default command)."""

    # Subcommands (history, stats) must not trigger a test
    if ctx.invoked_subcommand is not None:
        return

    # ── Resolve mode ───────────────────────────────────────────────────────────
    if time > 0:
        mode = "time"

    config = Config(
        word_count=words,
        time_limit=time,
        mode=mode,
        history_file=history_file,
    )

    # ── Generate test text ─────────────────────────────────────────────────────
    if mode == "practice":
        weak = history_mod.load_weak_words(history_file, top_n=30)
        if weak:
            text = words_mod.generate_from_pool(weak, words)
            display.console.print(
                f"[{DEFAULT_THEME.muted}]Practice mode: using your {len(weak)} most-missed words.[/]\n"
            )
        else:
            display.console.print(
                f"[{DEFAULT_THEME.muted}]No history yet — using mixed words for practice mode.[/]\n"
            )
            text = words_mod.generate(words, "mixed")
    else:
        text = words_mod.generate(words, difficulty)

    # ── Run the session ────────────────────────────────────────────────────────
    try:
        result = engine.run(text, config, DEFAULT_THEME)
    except KeyboardInterrupt:
        display.console.print("\n[grey50]Session cancelled.[/]")
        raise typer.Exit()

    if result is None:
        display.console.print("[grey50]Session aborted — no data saved.[/]")
        raise typer.Exit()

    # ── Load error history for suggestions ────────────────────────────────────
    all_time_errors = history_mod.load_word_errors(history_file)
    suggestions = stats_mod.build_suggestions(result, all_time_errors)

    # ── Render results ─────────────────────────────────────────────────────────
    display.render_results(result, suggestions, DEFAULT_THEME)

    # ── Persist session ────────────────────────────────────────────────────────
    history_mod.save_session(
        result,
        mode=mode,
        difficulty=difficulty,
        history_file=history_file,
    )
    display.console.print(
        f"[{DEFAULT_THEME.muted}]Session saved to {history_file}[/]\n"
    )


# ── history subcommand ─────────────────────────────────────────────────────────

@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent sessions to display."),
    history_file: Path = typer.Option(HISTORY_FILE, "--history-file", help="Override history file path."),
) -> None:
    """Show your recent typing sessions."""
    sessions = history_mod.load_sessions(history_file)
    display.render_history_table(sessions, limit=limit, theme=DEFAULT_THEME)


# ── stats subcommand ───────────────────────────────────────────────────────────

@app.command()
def stats(
    history_file: Path = typer.Option(HISTORY_FILE, "--history-file", help="Override history file path."),
) -> None:
    """Show aggregate statistics across all past sessions."""
    summary = history_mod.summarise(history_file)
    display.render_stats_panel(summary, theme=DEFAULT_THEME)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()

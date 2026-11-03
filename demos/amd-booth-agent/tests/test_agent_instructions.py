from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_INSTRUCTIONS = ROOT / "control/templates/main-AGENTS.md"
BOOTSTRAP = ROOT / "control/bootstrap_openclaw.py"


def test_main_agent_avoids_tools_for_self_contained_work() -> None:
    instructions = MAIN_INSTRUCTIONS.read_text(encoding="utf-8")
    normalized = " ".join(instructions.split())
    assert "answer directly" in normalized
    assert "Do not use tools merely to make the task look more agentic" in normalized
    assert "Respect explicit requests such as \"do not use tools\"" in normalized
    assert "For direct-response tasks, return only the requested answer" in normalized


def test_bootstrap_prefers_direct_answers_by_default() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert "Prefer direct answers for self-contained tasks" in bootstrap
    assert "depends on external information" in bootstrap

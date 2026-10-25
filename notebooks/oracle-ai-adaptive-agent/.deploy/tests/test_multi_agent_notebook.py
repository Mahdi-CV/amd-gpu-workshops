from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "openclaw-multi-agent-workshop.ipynb"


def notebook_text(path: Path) -> tuple[dict, str]:
    body = json.loads(path.read_text(encoding="utf-8"))
    text = "\n".join(
        "".join(cell.get("source") or [])
        for cell in body["cells"]
    )
    return body, text


def test_multi_agent_notebook_preserves_story_and_uses_vllm():
    body, text = notebook_text(NOTEBOOK)
    assert "AMD Instinct MI300X" in text
    assert "vllm serve Qwen/Qwen3.8-Flash-Next-FP8" in text
    assert "vllm-sr/auto" in text
    assert "Build a review panel (multi-agent)" in text
    assert "performance" in text
    assert "readability" in text
    assert "Review Panel Protocol" in text
    assert (
        "Run the review panel on "
        "https://github.com/Mahdi-CV/sloppy-sales"
    ) in text
    assert "https://github.com/Mahdi-CV/catch-the-bug.git" in text
    assert "fixer" in text.lower()
    assert 'lab.mark_phase("review_panel")' in text
    assert 'lab.mark_phase("fixer_challenge")' in text
    assert "lab.show_routing_summary(" in text
    assert 'source="live"' in text
    assert "agents.entries.main.subagents.allowAgents" in text
    assert "agents.entries.main.tools.alsoAllow" in text
    assert "openclaw agents add <name>" in text
    assert body["metadata"]["title"].startswith("AI Agents, Powered by AMD")


def test_multi_agent_notebook_removes_old_backend_assumptions():
    _, text = notebook_text(NOTEBOOK)
    lowered = text.lower()
    for forbidden in (
        "ollama",
        "llama.cpp",
        "llama-server",
        "llamacpp",
        "radeon",
        "/root/.openclaw",
        "local model reliable",
    ):
        assert forbidden not in lowered


def test_multi_agent_notebook_is_clean_for_participants():
    body, text = notebook_text(NOTEBOOK)
    code_cells = [
        cell for cell in body["cells"] if cell["cell_type"] == "code"
    ]
    assert code_cells
    assert all(cell.get("execution_count") is None for cell in code_cells)
    assert all((cell.get("outputs") or []) == [] for cell in code_cells)
    assert "This file will appear after" not in text


def test_multi_agent_notebook_uses_aggregate_route_reveal():
    _, text = notebook_text(NOTEBOOK)
    assert "Total routed LLM calls" in text
    assert "all-GLM-5.3-Flash" in text
    assert "panel_routes = lab.route_report" not in text
    assert "live_routes = lab.route_report" not in text

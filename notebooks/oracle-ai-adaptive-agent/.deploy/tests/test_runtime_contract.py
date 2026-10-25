from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("WORKSHOP_ROOT", str(ROOT.parent))
os.environ.setdefault(
    "WORKSHOP_WORKSPACE", "/tmp/openclaw-runtime-contract-workspace"
)
os.environ.setdefault(
    "WORKSHOP_RUNTIME_DIR",
    "/tmp/openclaw-runtime-contract-workspace/runtime",
)
os.environ.setdefault(
    "OPENCLAW_STATE_DIR",
    "/tmp/openclaw-runtime-contract-workspace/state/openclaw",
)
os.environ.setdefault(
    "OPENCLAW_WORKSHOP_WORKSPACES",
    "/tmp/openclaw-runtime-contract-workspace/agents",
)
os.environ.setdefault(
    "OPENCLAW_WORKSHOP_DEMO_ROOT",
    "/tmp/openclaw-runtime-contract-workspace/demo",
)

from workshop_lab import NEW_ACCURACY_LINE, OLD_ACCURACY_LINE, WorkshopLab


def test_handoff_requires_both_reviews():
    try:
        WorkshopLab.build_fixer_prompt("", "tests")
    except ValueError:
        pass
    else:
        raise AssertionError("empty bug review should be rejected")

    value = WorkshopLab.build_fixer_prompt("bug", "tests")
    assert "BUG REVIEW:\nbug" in value
    assert "TEST REVIEW:\ntests" in value


def test_main_prompt_uses_actual_verification():
    value = WorkshopLab.build_main_prompt(
        {"passed": False, "pytest_summary": "1 failed"}
    )
    assert '"passed": false' in value
    assert "1 failed" in value


def test_tree_hashes_ignore_caches(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_x.py").write_text("pass\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__/x.pyc").write_bytes(b"cache")
    rows = WorkshopLab._tree_hashes(tmp_path)
    assert rows == {
        "tests/test_x.py": hashlib.sha256(b"pass\n").hexdigest()
    }


def test_expected_patch_constants():
    assert "//" in OLD_ACCURACY_LINE
    assert "total_typed + 1" in OLD_ACCURACY_LINE
    assert NEW_ACCURACY_LINE == (
        "    return round((correct / total_typed) * 100, 1)"
    )


def test_bootstrap_preserves_openclaw_first_run_templates():
    script = (ROOT / "bin/bootstrap-workshop.sh").read_text(
        encoding="utf-8"
    )
    assert "--skip-bootstrap" not in script
    assert "AGENTS.md SOUL.md IDENTITY.md USER.md BOOTSTRAP.md" in script
    assert 'grep -q "^## First Run"' in script


def test_policy_comparison_artifact_is_notebook_ready():
    value = WorkshopLab().policy_comparison()
    assert value["reliability"] == {
        "vllm_sr_auto": "9/9",
        "direct_glm": "8/9",
    }
    assert (
        value["empirical_matched_successes"]["auto_savings_percent"]
        == 51.66
    )
    assert (
        value["same_auto_token_sensitivity"][
            "gross_backend_model_mix_savings_percent"
        ]
        == 14.81
    )


def test_routing_summary_aggregates_models_and_glm_baseline(tmp_path):
    lab = WorkshopLab()
    lab.routes = tmp_path / "routes.jsonl"
    rows = [
        {
            "request_id": 1,
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 100,
                "reasoning_tokens": 40,
            },
            "estimated_relative_cost_xxx": 0.000399,
            "routing_headers": {
                "x-vsr-selected-model": "qwen/qwen3.8-flash-next",
                "x-vsr-selected-decision": "code_agentic",
                "x-vsr-selected-reasoning": "on",
                "x-vsr-matched-projections": "effort_medium",
            },
        },
        {
            "request_id": 2,
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 20,
                "reasoning_tokens": 0,
            },
            "estimated_relative_cost_xxx": 0.00007,
            "routing_headers": {
                "x-vsr-selected-model": "qwen/qwen3.8-27b",
                "x-vsr-selected-decision": "fast",
                "x-vsr-selected-reasoning": "off",
                "x-vsr-matched-projections": "effort_off",
            },
        },
        {
            "request_id": 3,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 0,
                "reasoning_tokens": 0,
            },
            "estimated_relative_cost_xxx": None,
            "routing_headers": {},
        },
    ]
    lab.routes.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    summary = lab.routing_summary()

    assert summary["total_calls"] == 2
    assert [row["calls"] for row in summary["models"]] == [1, 1]
    assert summary["reasoning_efforts"] == {"medium": 1, "off": 1}
    assert summary["relative_compute"]["incomplete_cost_calls"] == []
    assert (
        summary["relative_compute"][
            "all_glm_flash_max_same_tokens_xxx"
        ]
        == 0.001182
    )
    assert summary["relative_compute"]["reduction_percent"] == 60.32

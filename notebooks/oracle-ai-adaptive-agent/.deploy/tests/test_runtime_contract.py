from __future__ import annotations

import hashlib
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

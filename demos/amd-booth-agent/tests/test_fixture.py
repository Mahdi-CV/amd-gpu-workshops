from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "control/fixtures/broken-benchmark"


def test_fixture_starts_with_four_failures():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=FIXTURE,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "4 failed, 1 passed" in result.stdout

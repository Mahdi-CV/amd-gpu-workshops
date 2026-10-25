from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "compare-policies.py"
SPEC = importlib.util.spec_from_file_location("compare_policies", SCRIPT)
assert SPEC and SPEC.loader
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def test_execution_plan_is_deterministic_matched_and_sequential():
    first = compare.build_execution_plan(8675309)
    second = compare.build_execution_plan(8675309)
    assert first == second
    assert len(first) == 6
    for pair_id in (1, 2, 3):
        rows = [row for row in first if row["pair_id"] == pair_id]
        assert {row["arm"] for row in rows} == {"auto", "direct_glm"}
        positions = sorted(row["position"] for row in rows)
        assert positions[1] == positions[0] + 1


def test_discover_glm_prefers_exact_and_honors_override():
    models = [
        "qwen/qwen3.8-27b",
        "s3/workshop-glm-5-3-flash-import-abc",
        "zai/glm-5.3-flash",
    ]
    assert compare.discover_glm_model(models) == "zai/glm-5.3-flash"
    assert (
        compare.discover_glm_model(
            models,
            "s3/workshop-glm-5-3-flash-import-abc",
        )
        == "s3/workshop-glm-5-3-flash-import-abc"
    )


def test_discover_glm_rejects_missing_override():
    with pytest.raises(RuntimeError):
        compare.discover_glm_model(["qwen/qwen3.8-27b"], "missing")


def test_recipe_costs_use_exact_prompt_and_completion_rates():
    factors = compare.load_cost_factors()
    usage = {"prompt_tokens": 1000, "completion_tokens": 100}
    assert compare.usage_cost_xxx(
        usage,
        "zai/glm-5.3-flash",
        factors,
    ) == 0.000875
    assert compare.usage_cost_xxx(
        usage,
        "qwen/qwen3.8-flash-next",
        factors,
    ) == 0.000399


def test_imported_response_model_maps_to_recipe_model():
    factors = compare.load_cost_factors()
    assert (
        compare.canonical_model_id(
            "s3/workshop-glm-5-3-flash-import-c8de8d7b",
            factors,
        )
        == "zai/glm-5.3-flash"
    )


def test_reviewer_and_pytest_handoffs_are_verbatim():
    bug = 'bug output\nwith "quotes"\n'
    tests = "test output\n"
    fixer = compare.build_fixer_prompt(bug, tests)
    assert bug in fixer
    assert tests in fixer
    pytest_result = {
        "returncode": 0,
        "stdout": "107 passed in 0.31s\n",
        "stderr": "",
    }
    main = compare.build_main_prompt(pytest_result)
    assert pytest_result["stdout"] in main
    assert "returncode: 0" in main


def test_parse_pytest_counts_uses_terminal_summary():
    parsed = compare.parse_pytest_counts(
        "progress\n5 failed, 102 passed in 0.45s\n"
    )
    assert parsed["counts"] == {"failed": 5, "passed": 102}
    assert parsed["summary_line"].startswith("5 failed")


def test_source_integrity_accepts_minimal_equivalent_stats_fixes(tmp_path):
    before = {
        "stats.py": (
            "def f():\n"
            f"{compare.OLD_ACCURACY_LINE}\n"
        ).encode(),
        "tests/test_stats.py": b"def test_it(): pass\n",
    }
    after = dict(before)
    after["stats.py"] = (
        "def f():\n"
        f"{compare.NEW_ACCURACY_LINE}\n"
    ).encode()
    result = compare.source_integrity(before, after)
    assert result["tests_unchanged"]
    assert result["source_fix_valid"]
    assert result["source_fix_variant"] == "canonical"
    assert result["exact_source_patch"]

    equivalent = dict(before)
    equivalent["stats.py"] = (
        "def f():\n"
        f"{compare.EQUIVALENT_ACCURACY_LINE}\n"
    ).encode()
    result = compare.source_integrity(before, equivalent)
    assert result["source_fix_valid"]
    assert result["source_fix_variant"] == "equivalent"
    assert not result["exact_source_patch"]

    after["tests/test_stats.py"] = b"changed\n"
    assert not compare.source_integrity(before, after)["tests_unchanged"]

    extra_edit = dict(before)
    extra_edit["stats.py"] = (
        "# unrelated edit\n"
        "def f():\n"
        f"{compare.NEW_ACCURACY_LINE}\n"
    ).encode()
    assert not compare.source_integrity(before, extra_edit)["source_fix_valid"]


def test_source_integrity_accepts_equivalent_parentheses():
    before = {
        "stats.py": (
            "def f():\n"
            f"{compare.OLD_ACCURACY_LINE}\n"
        ).encode(),
    }
    after = {
        "stats.py": (
            "def f():\n"
            "    return round(correct / total_typed * 100, 1)\n"
        ).encode(),
    }
    result = compare.source_integrity(before, after)
    assert result["source_fix_valid"]
    assert result["source_fix_variant"] == "equivalent"
    assert not result["exact_source_patch"]
    after["stats.py"] = (
        "def f():\n"
        "    return round(correct / (total_typed * 100), 1)\n"
    ).encode()
    assert not compare.source_integrity(before, after)["source_fix_valid"]


def test_get_models_uses_bearer_credential_without_returning_it(tmp_path):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            seen["authorization"] = self.headers.get("Authorization")
            body = json.dumps(
                {"data": [{"id": "vllm-sr/auto"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        result = compare.get_models(
            f"http://127.0.0.1:{port}/v1",
            "test-secret",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert seen["authorization"] == "Bearer test-secret"
    assert "test-secret" not in json.dumps(result)


def test_schema_and_cost_json_are_valid():
    schema = compare.SCHEMA
    assert json.loads(schema.read_text())["$id"] == compare.SCHEMA_VERSION
    factors = compare.load_cost_factors()
    assert factors["recipe"]["version"] == "0.3.2"


def test_verify_summary_uses_declared_pair_count_not_module_default():
    factors = compare.load_cost_factors()
    summary = {
        "schema_version": compare.SCHEMA_VERSION,
        "recipe": {"version": "0.3.2"},
        "design": {"matched_pairs": 1},
        "execution_plan": [
            {"pair_id": 1, "arm": "auto", "position": 1},
            {"pair_id": 1, "arm": "direct_glm", "position": 2},
        ],
        "pairs": [
            {
                "pair_id": 1,
                "arms": {
                    "auto": {"status": "error", "passed": False},
                    "direct_glm": {"status": "error", "passed": False},
                },
            }
        ],
    }
    errors = compare.verify_summary(summary, factors)
    assert not any("exactly three" in error for error in errors)
    assert not any("execution plan" in error for error in errors)


def test_aggregate_includes_observed_partial_failure_cost():
    completed_metrics = {
        "requests": 2,
        "assistant_turns": 1,
        "tokens": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 1,
            "cached_tokens": 0,
        },
        "workflow_wall_time_seconds": 4.0,
        "actual_cost_xxx": 0.2,
        "auto_tokens_glm_reprice_xxx": 0.3,
    }
    failed_metrics = {
        "requests": 1,
        "assistant_turns": 0,
        "tokens": {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "reasoning_tokens": 1,
            "cached_tokens": 0,
        },
        "workflow_wall_time_seconds": 2.0,
        "actual_cost_xxx": 0.1,
        "auto_tokens_glm_reprice_xxx": 0.15,
    }
    pairs = [
        {
            "arms": {
                "auto": {
                    "status": "completed",
                    "passed": True,
                    "metrics": completed_metrics,
                },
                "direct_glm": {
                    "status": "completed",
                    "passed": True,
                    "metrics": {
                        **completed_metrics,
                        "auto_tokens_glm_reprice_xxx": None,
                    },
                },
            }
        },
        {
            "arms": {
                "auto": {
                    "status": "error",
                    "passed": False,
                    "metrics": failed_metrics,
                },
                "direct_glm": {
                    "status": "error",
                    "passed": False,
                    "metrics": {
                        **failed_metrics,
                        "auto_tokens_glm_reprice_xxx": None,
                    },
                },
            }
        },
    ]
    aggregate = compare.aggregate_summary(pairs)
    auto = aggregate["arms"]["auto"]
    assert auto["attempts"] == 2
    assert auto["completed"] == 1
    assert auto["cost_observed_attempts"] == 2
    assert auto["actual_cost_xxx"] == 0.3

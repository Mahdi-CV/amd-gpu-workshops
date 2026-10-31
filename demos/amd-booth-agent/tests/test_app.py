from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["BOOTH_APP_ROOT"] = str(ROOT / "control")
spec = importlib.util.spec_from_file_location("booth_app", ROOT / "control/app.py")
assert spec and spec.loader
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


def test_sse_usage_and_tool_calls_are_recovered():
    raw = "\n".join(
        [
            'data: {"model":"moonshot/kimi-k3","choices":[{"delta":'
            '{"tool_calls":[{"index":0,"id":"call-1","type":"function",'
            '"function":{"name":"browser","arguments":"{\\"url\\":\\"https://"}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            '"function":{"name":"_open","arguments":"example.com\\"}"}}]},'
            '"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":100,'
            '"completion_tokens":20,"completion_tokens_details":'
            '{"reasoning_tokens":7}}}',
            "data: [DONE]",
        ]
    ).encode()
    parsed = app.parse_upstream_response(raw, "text/event-stream")
    assert parsed["model"] == "moonshot/kimi-k3"
    assert parsed["usage"]["prompt_tokens"] == 100
    call = parsed["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "browser_open"


def test_reasoning_effort_reports_selected_policy_not_projection():
    headers = {
        "x-vsr-selected-decision": "agentic",
        "x-vsr-matched-projections": "effort_off",
        "x-vsr-selected-reasoning": "on",
    }
    assert app.parse_effort(headers) == "high"


def test_costs_use_cached_and_uncached_rates():
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "cached_tokens": 400,
        "reasoning_tokens": 50,
    }
    value = app.cost_for_model("moonshot/kimi-k3", usage)
    assert value == (600 * 3.0 + 400 * 0.3 + 100 * 15.0) / 1_000_000
    assert app.cost_for_model("qwen/qwen3.8-27b", usage) == 0


def test_run_metrics_report_both_counterfactuals(tmp_path):
    run = app.RunRecord(
        id="demo",
        task="demo",
        title="demo",
        run_dir=tmp_path,
    )
    run.actual_cost = 0.01
    run.all_kimi_cost = 0.10
    run.all_glm_cost = 0.02
    run.model_counts = {"qwen/qwen3.8-27b": 2}
    metrics = run.metrics()
    assert metrics["savings_vs_kimi_percent"] == 90.0
    assert metrics["savings_vs_glm_percent"] == 50.0


def test_final_text_from_history_uses_response_after_latest_yield():
    history = {
        "messages": [
            {
                "role": "assistant",
                "api": "openai-completions",
                "provider": "booth-main",
                "stopReason": "stop",
                "timestamp": 10,
                "content": [{"type": "text", "text": "Early result"}],
            },
            {
                "role": "toolResult",
                "toolName": "sessions_yield",
                "timestamp": 20,
            },
            {
                "role": "assistant",
                "timestamp": 21,
                "content": [{"type": "text", "text": "Still waiting"}],
            },
            {
                "role": "assistant",
                "api": "openai-completions",
                "provider": "booth-main",
                "stopReason": "stop",
                "timestamp": 30,
                "content": [{"type": "text", "text": "Verified final result"}],
            },
            {
                "role": "assistant",
                "api": "openclaw-transcript",
                "provider": "openclaw",
                "stopReason": "stop",
                "timestamp": 40,
                "content": [{"type": "text", "text": "Learned a skill"}],
            },
        ]
    }
    assert app.final_text_from_history(history) == "Verified final result"

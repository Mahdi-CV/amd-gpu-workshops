from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fireworks_shim",
    ROOT / "control/fireworks_shim.py",
)
assert spec and spec.loader
shim = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shim
spec.loader.exec_module(shim)


def test_nonstream_extensions_are_removed():
    payload = {
        "choices": [
            {
                "raw_output": None,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tools": None,
                    "tool_calls": [
                        {
                            "index": 0,
                            "name": None,
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "inspect_file",
                                "arguments": '{"path":"/tmp/demo.py"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "completion_tokens_details": {"reasoning_tokens": 4},
            "output_tokens_details": {"reasoning_tokens": 4},
        },
    }
    value = shim.normalize_fireworks_payload(payload, streaming=False)
    choice = value["choices"][0]
    call = choice["message"]["tool_calls"][0]
    assert "raw_output" not in choice
    assert "tools" not in choice["message"]
    assert "index" not in call
    assert "name" not in call
    assert "output_tokens_details" not in value["usage"]
    assert value["usage"]["completion_tokens_details"]["reasoning_tokens"] == 4


def test_stream_tool_index_is_preserved():
    payload = {
        "choices": [
            {
                "raw_output": None,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": "{}"},
                        }
                    ]
                },
            }
        ],
        "usage": None,
    }
    value = shim.normalize_fireworks_payload(payload, streaming=True)
    choice = value["choices"][0]
    assert "raw_output" not in choice
    assert choice["delta"]["tool_calls"][0]["index"] == 0

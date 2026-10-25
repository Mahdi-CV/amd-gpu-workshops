# Build an OpenClaw Debugging Team

This is a simple, TUI-first workshop with two goals:

1. teach how OpenClaw agents, workspaces, roles, and tools work; and
2. show how `vllm-sr/auto` selects different models for different agent roles.

Open:

```text
workshop.ipynb
```

## Team

```text
main             short final reporter
bug_reviewer     tool-free code diagnosis
test_reviewer    tool-free regression-test reasoning
fixer            tool-capable source edit and pytest verification
```

Participants switch agents interactively in one OpenClaw TUI.

## Expected route split

The workshop targets Decision Balance recipe `0.3.2`:

| Agent work | Decision | Expected model |
| --- | --- | --- |
| Bug review | `code` | Qwen3.8-Flash-Next |
| Test review | `code` | Qwen3.8-Flash-Next |
| File editing and pytest | `agentic` or `recovery` | GLM-5.3-Flash |
| One-sentence verified summary | `fast` | Qwen3.8-27B |

Every agent requests only:

```text
vllm-sr/auto
```

## Quality gate

The frozen `open_type_faster` fixture begins with:

```text
5 failed, 102 passed
```

The Fixer succeeds only when:

```text
107 passed
```

No LLM judge is used.

## Endpoint configuration

```bash
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint.example/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="vllm-sr/auto"
export VLLM_SR_DASHBOARD_URL="https://your-dashboard.example"
```

The key is not printed or stored in the notebook.

## Included files

```text
.deploy/fixture/open_type_faster/   frozen debugging project
.deploy/bin/logging_proxy.py        sanitized route logger
.deploy/artifacts/simple-route-results.md
.deploy/PRESENTER-GUIDE.md          presenter-only notes
```

The participant flow does not use a hidden orchestration or scoring harness.

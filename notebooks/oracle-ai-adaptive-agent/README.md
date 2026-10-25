# Build an OpenClaw Debugging Team

This participant workshop teaches:

1. how to build and switch between OpenClaw agents; and
2. how `vllm-sr/auto` selects model capability per role.

The Docker runtime already contains OpenClaw, the fixture, endpoint proxy,
state paths, and lifecycle commands. Open:

```text
workshop.ipynb
```

## Team

```text
bug_reviewer     focused code diagnosis
test_reviewer    focused regression reasoning
fixer            source editing and pytest
main             one-sentence verified report
```

All agents use the normal `vllm-sr/auto` provider:

- reviewers and `main` use OpenClaw's `minimal` profile;
- the Fixer uses the `coding` profile.

Expected Decision Balance `0.3.2` routes:

```text
reviewers → code    → Qwen3.8-Flash-Next
fixer     → agentic → GLM-5.3-Flash
main      → fast    → Qwen3.8-27B
```

## Quality gate

```text
Before: 5 failed, 102 passed
After:  107 passed
```

The notebook also verifies that tests are unchanged and only the intended
source line changed.

## Runtime commands

Inside the container:

```bash
workshop-status
workshop-reset
workshop-verify-image
workshop-verify-e2e
workshop-compare --repetitions 3
```

Deployment and coworker instructions are under `.deploy/`.

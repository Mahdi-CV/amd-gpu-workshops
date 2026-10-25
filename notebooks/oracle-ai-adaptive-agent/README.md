# Build an OpenClaw Debugging Team

This participant workshop teaches:

1. how to build and switch between OpenClaw agents; and
2. how `vllm-sr/auto` selects model capability per role.

The Docker runtime already contains OpenClaw, the fixture, endpoint proxy,
state paths, and lifecycle commands.

For the original performance/readability/Fixer workshop with the minimally
updated MI300X + vLLM setup, open:

```text
openclaw-multi-agent-workshop.ipynb
```

The controlled debugging-team evaluation remains available as:

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
reviewers → code_agentic → Qwen3.8-Flash-Next
fixer     → code_agentic → Qwen3.8-Flash-Next
fixer     → recovery     → GLM-5.3-Flash
main      → fast         → Qwen3.8-27B
```

## Quality gate

```text
Before: 5 failed, 102 passed
After:  107 passed
```

The notebook also verifies that tests are unchanged and only the intended
source line changed.

## Verified policy evidence

The bundled sanitized analysis combines nine matched attempts:

```text
vllm-sr/auto functional success: 9/9
Direct GLM functional success:   8/9
Successful matched pairs:        8
Empirical compute reduction:     51.66%
Same-token backend-mix estimate: 14.81%
```

`XXX` is a versioned relative-compute unit, not money. Open
`.deploy/artifacts/policy-analysis.md` for the complete methodology, per-pair
results, route distribution, and limitations.

The tested priority-750 `code_agentic` overlay is under
`.deploy/router/decision-balance-code-agentic/`. See
`.deploy/artifacts/code-agentic-live-validation-20261025.md` for its live
MI300X review-panel and Fixer validation.

## Runtime commands

Inside the container:

```bash
workshop-status
workshop-reset
workshop-verify-image
workshop-verify-e2e
workshop-compare --repetitions 3
workshop-analyze-results SUMMARY.json \
  --json-output analysis.json \
  --markdown-output analysis.md
```

Deployment and coworker instructions are under `.deploy/`.

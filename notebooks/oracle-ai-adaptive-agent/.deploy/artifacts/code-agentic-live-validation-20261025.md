# Code-Agentic Live Validation

Validated October 25, 2026 on an 8 x AMD Instinct MI300X deployment.

## Route added

```text
800  recovery       -> GLM-5.3-Flash
750  code_agentic   -> Qwen3.8-Flash-Next
700  agentic        -> GLM-5.3-Flash
450  code           -> Qwen3.8-Flash-Next
100  fast           -> Qwen3.8-27B
```

`code_agentic` matches `task:code` plus declared tools or an active tool loop.

## Required route probes

| Case | Decision | Model |
| --- | --- | --- |
| Code with tools | `code_agentic` | Flash-Next |
| Generic agentic tools | `agentic` | GLM |
| Code without tools | `code` | Flash-Next |
| Correction/retry | `recovery` | GLM |

All four probes passed.

## Multi-agent review panel

| Metric | Original recipe | With `code_agentic` |
| --- | ---: | ---: |
| Calls | 21 | 23 |
| Flash-Next calls | 2 | 18 |
| GLM calls | 19 | 5 |
| Relative compute | 0.11377763 XXX | 0.06615557 XXX |
| Reduction | — | **41.86%** |

Performance, readability, and merged reports remained complete and accurate.
GLM continued to handle coordinator-style agentic work.

The sum of individual request latencies increased slightly, so this is a
compute/model-mix result rather than a universal latency improvement.

## Deterministic Fixer smoke

Both policies finished at `107 passed`, with tests unchanged and the correct
source-only patch.

| Metric | Auto | Direct GLM |
| --- | ---: | ---: |
| Relative compute | 0.04775879 XXX | 0.06613529 XXX |
| Workflow seconds | 113.268 | 122.976 |

Auto routes:

```text
5 code_agentic -> Flash-Next
5 recovery     -> GLM
1 fast         -> Qwen3.8-27B
```

Actual relative-compute reduction: **27.79%**.

`XXX` is a versioned relative-compute unit, not money. The panel result is one
observed workflow and the Fixer result is one matched deterministic pair.

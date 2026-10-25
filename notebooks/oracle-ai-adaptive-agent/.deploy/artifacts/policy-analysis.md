# OpenClaw: vLLM-SR Auto vs Direct GLM

## Executive result

| Metric | vLLM-SR auto | Direct GLM |
| --- | ---: | ---: |
| Functional successes | 9/9 | 8/9 |
| Success rate | 100.0% | 88.89% |
| Observed requests | 94 | 116 |
| Prompt tokens | 716255 | 842658 |
| Completion tokens | 36091 | 103166 |
| Reasoning tokens | 17916 | 85905 |
| Mean completed workflow | 89.9818 s | 160.2029 s |

Every functional success started at `5 failed, 102 passed`, ended at `107 passed`, left tests unchanged, and made only the accepted one-line source correction.

### Failure-inclusive observed compute

| Metric | vLLM-SR auto | Direct GLM |
| --- | ---: | ---: |
| Observed compute across all attempts | 0.40220074 XXX | 0.81954162 XXX |
| Compute per functional success | 0.04468897 XXX | 0.10244270 XXX |
| Cost coverage | 9/9 attempts | 9/9 attempts |

## Empirical matched-success comparison

- Successful matched pairs: `8`
- Auto observed compute: `0.35071344 XXX`
- Direct GLM observed compute: `0.72558628 XXX`
- Pooled auto savings: `51.66%`
- Mean time saved per matched workflow: `70.4442 s`
- Pooled latency reduction: `43.97%`

| Experiment | Pair | Auto XXX | Direct GLM XXX | Savings | Time saved |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0.05057262 | 0.09059997 | 44.18% | 78.908 s |
| 2 | 1 | 0.04385829 | 0.08711995 | 49.66% | 69.702 s |
| 2 | 3 | 0.05437960 | 0.08783700 | 38.09% | 56.209 s |
| 3 | 1 | 0.03490710 | 0.10404042 | 66.45% | 89.859 s |
| 3 | 2 | 0.03201011 | 0.09369828 | 65.84% | 60.634 s |
| 3 | 3 | 0.04172533 | 0.07471683 | 44.16% | 55.459 s |
| 3 | 4 | 0.04513690 | 0.10314678 | 56.24% | 95.364 s |
| 3 | 5 | 0.04812349 | 0.08442705 | 43.0% | 57.419 s |

The pooled result is a ratio of total compute. Across individual pairs, savings ranged from `38.09%` to `66.45%`, with a median of `46.92%`.

## Same-auto-token routing sensitivity

- Successful auto runs: `9`
- Auto selected-backend compute: `0.40220074 XXX`
- The same tokens priced entirely as GLM: `0.47214805 XXX`
- Gross backend-model-mix savings: `14.81%`

Counterfactual same-token repricing. It excludes router overhead and is not a direct-GLM execution.

### Why the empirical reduction is larger

Compared with direct GLM across all attempts, auto used `18.97%` fewer requests, `65.02%` fewer completion tokens, and `79.14%` fewer reasoning tokens. Therefore the empirical policy result captures both backend selection and different model/tool-loop trajectories; the same-token result isolates only the selected-backend rate mix.

## Auto route distribution

| Decision | Selected model | Calls | Share | Cost XXX | P90 latency |
| --- | --- | ---: | ---: | ---: | ---: |
| `agentic` | `zai/glm-5.3-flash` | 11 | 11.7% | 0.08052705 | 17.4817 s |
| `code` | `qwen/qwen3.8-flash-next` | 26 | 27.66% | 0.05023720 | 9.322 s |
| `fast` | `qwen/qwen3.8-27b` | 9 | 9.57% | 0.00295310 | 1.5653 s |
| `recovery` | `zai/glm-5.3-flash` | 48 | 51.06% | 0.26848339 | 3.7781 s |

### Routes by OpenClaw phase

```json
{
  "bug_reviewer": {
    "code \u2192 qwen/qwen3.8-flash-next": 9
  },
  "fixer": {
    "code \u2192 qwen/qwen3.8-flash-next": 8,
    "recovery \u2192 zai/glm-5.3-flash": 48,
    "agentic \u2192 zai/glm-5.3-flash": 1
  },
  "main": {
    "fast \u2192 qwen/qwen3.8-27b": 9
  },
  "test_reviewer": {
    "code \u2192 qwen/qwen3.8-flash-next": 9,
    "agentic \u2192 zai/glm-5.3-flash": 10
  }
}
```

## Harness correction

- Original strict-text successes: auto `9/9`, direct GLM `4/9`.
- Corrected functional successes: auto `9/9`, direct GLM `8/9`.
- Four direct-GLM runs used the equivalent minimal expression `round(correct / total_typed * 100, 1)`. They passed all 107 tests, left tests unchanged, and changed only the intended source line, so they are functional successes rather than model failures.
- The one retained direct-GLM failure was a real terminal malformed tool-call outcome. Its observed token cost is included.

## Reliability details

```json
{
  "paired_outcomes": {
    "both_functionally_passed": 8,
    "auto_passed_direct_failed": 1,
    "direct_passed_auto_failed": 0,
    "both_failed": 0
  },
  "auto_failures": {},
  "direct_glm_failures": {
    "malformed_tool_call": 1
  },
  "auto_cost_coverage": {
    "observed": 9,
    "missing": 0
  },
  "direct_glm_cost_coverage": {
    "observed": 9,
    "missing": 0
  }
}
```

## Interpretation

- The empirical matched comparison includes only pairs where both policies passed the same deterministic quality gate.
- Failure-inclusive cost per success is reported only when every attempt has recoverable route usage.
- `XXX` is a versioned relative-compute unit, not a dollar cost.
- Harness retries were zero; internal provider retries were not instrumented.
- This is a nine-pair workshop experiment on one deterministic debugging task, not a general model-quality benchmark.

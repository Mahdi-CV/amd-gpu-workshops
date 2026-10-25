# Verified Route Results

Date: October 25, 2026

Recipe: `decision-balance` `0.3.2`  
Requested model on every call: `vllm-sr/auto`

## Result

```text
Before: 5 failed, 102 passed
After:  107 passed
```

## Request-by-request routes

| Call | OpenClaw phase | Tools | Decision | Selected model | Reasoning | Prompt | Completion | Latency | Cost XXX |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Bug Reviewer | 0 | `code` | Qwen3.8-Flash-Next | on | 2,109 | 443 | 5.675s | 0.00130126 |
| 2 | Test Reviewer | 0 | `code` | Qwen3.8-Flash-Next | on | 2,171 | 1,802 | 17.745s | 0.00401801 |
| 3 | Fixer step 1 | 11 | `agentic` | GLM-5.3-Flash | on | 6,816 | 63 | 2.198s | 0.00323901 |
| 4 | Fixer step 2 | 11 | `agentic` | GLM-5.3-Flash | on | 7,192 | 51 | 2.327s | 0.00335037 |
| 5 | Fixer step 3 | 11 | `agentic` | GLM-5.3-Flash | on | 7,259 | 55 | 2.136s | 0.00339691 |
| 6 | Fixer step 4 | 11 | `agentic` | GLM-5.3-Flash | on | 7,908 | 27 | 1.648s | 0.00355743 |
| 7 | Fixer step 5 | 11 | `agentic` | GLM-5.3-Flash | on | 9,693 | 155 | 4.122s | 0.00489071 |
| 8 | Fixer step 6 | 11 | `agentic` | GLM-5.3-Flash | on | 9,841 | 55 | 2.335s | 0.00452008 |
| 9 | Fixer final | 11 | `agentic` | GLM-5.3-Flash | on | 9,922 | 140 | 3.840s | 0.00492507 |
| 10 | Main Reporter | 0 | `fast` | Qwen3.8-27B | off | 1,939 | 16 | 1.061s | 0.00020990 |

## Totals

```text
Calls:                         10
Qwen3.8-Flash-Next calls:       2
GLM-5.3-Flash calls:            7
Qwen3.8-27B calls:              1
Prompt tokens:             64,850
Completion tokens:          2,807
Reasoning tokens:           1,861
Summed request latency:     43.087s
Routed measured cost:       0.03340875 XXX
All-GLM same-token estimate:0.04042020 XXX
Estimated reduction:       17.35%
```

## Workshop claim

> The capable OpenClaw workflow still used GLM for every filesystem, editing,
> and test-execution step. vLLM Semantic Router used cheaper models only for
> focused no-tools review and the final brief report, reducing estimated
> relative compute by 17.35% while the deterministic test suite finished at
> 107/107 passing.

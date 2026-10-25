# Auto vs Direct GLM: Three-Pair Rehearsal

Date: October 25, 2026  
Seed: `20261025`  
Recipe rates: Decision Balance `0.3.2`

## Reliability

| Policy | Successful workflows | Attempts |
| --- | ---: | ---: |
| `vllm-sr/auto` | 3 | 3 |
| Direct GLM | 2 | 3 |

The failed direct-GLM run ended during the Fixer tool loop with:

```text
Provider returned an incomplete or malformed tool call
```

The failure was retained as an outcome; it was not silently retried or removed.

## Cost on completed matched pairs

Two pairs completed successfully under both policies.

```text
Auto actual cost:              0.09823789 XXX
Direct GLM actual cost:        0.17495695 XXX
Auto savings vs direct GLM:    43.85%
```

## Routing-only sensitivity

Applying GLM rates to the same tokens used by the two completed auto runs:

```text
Auto actual cost:              0.09823789 XXX
Auto tokens at GLM rates:      0.11503261 XXX
Routing-only savings:          14.60%
```

`XXX` is a relative compute unit, not money.

## Quality

Every completed workflow satisfied:

```text
Baseline:           5 failed, 102 passed
Final:              107 passed
Tests unchanged:    true
Exact source patch: true
```

The compact machine-readable result is
`auto-vs-glm-3pairs-20261025.json`. Raw per-agent outputs and OpenClaw state
remain on the controlled test server and are not committed.

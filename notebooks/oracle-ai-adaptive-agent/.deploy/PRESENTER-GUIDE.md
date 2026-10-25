# Presenter Guide

## Message

> We kept a capable OpenClaw team and a deterministic passing-test requirement.
> vLLM Semantic Router spent expensive inference only on the role that needed
> filesystem, editing, and execution tools.

## Layout

```text
left:   workshop.ipynb
right:  openclaw tui
side:   vLLM-SR Dashboard → Insights
```

## 25-minute run

| Segment | Minutes |
| --- | ---: |
| Readiness and two goals | 2 |
| Show the failing bug | 3 |
| Build the team | 5 |
| Four TUI turns and handoffs | 9 |
| Quality, routes, and matched comparison | 5 |
| Challenge | 1 |

## Presenter rules

- Run `workshop-status` before opening the notebook.
- Keep one Gateway and one TUI lifecycle.
- Run every phase-marker cell before sending its TUI prompt.
- Paste both real reviewer outputs into the handoff cells.
- Do not continue to Main unless `lab.verify_demo()` passes.
- Use `lab.route_report(source="live")` for the current run.
- Use `lab.policy_comparison()` for the precomputed matched policy evidence.
- Use rehearsal data only in the explicitly labeled fallback section.

## Expected routes

```text
bug_reviewer   code      Qwen3.8-Flash-Next
test_reviewer  code      Qwen3.8-Flash-Next
fixer          agentic   GLM-5.3-Flash
main           fast      Qwen3.8-27B, thinking off
```

Fixer continuations may use `recovery`; they should remain on GLM.

## Quality language

Say:

```text
Before: 5 failed, 102 passed
After:  107 passed
Tests unchanged: yes
Source-only patch: yes
```

Do not call the test result an LLM-judge score.

## Cost language

The notebook shows a versioned token-based relative-compute estimate. `XXX` is
not money.

Keep these two results separate:

1. **Empirical policy comparison:** matched `vllm-sr/auto` and direct-GLM
   executions that passed the same deterministic quality gate.
2. **Same-token sensitivity:** the successful auto calls repriced as though all
   of their tokens had used GLM. This isolates backend model mix, but excludes
   router overhead and is not another direct-GLM execution.

The direct-GLM comparison is produced by:

```bash
workshop-compare --repetitions 3
```

The sanitized report is produced by `workshop-analyze-results`. Do not present
same-token GLM repricing as an empirical direct-GLM run.

Current verified snapshot:

| Result | Value |
| --- | ---: |
| Auto functional success | 9/9 |
| Direct GLM functional success | 8/9 |
| Successful matched pairs | 8 |
| Empirical pooled compute reduction | 51.66% |
| Empirical pooled latency reduction | 43.97% |
| Same-auto-token backend-mix reduction | 14.81% |

The single direct-GLM failure was a terminal malformed tool call. The failed
attempt's observed compute is included in the failure-inclusive analysis.

## Dashboard

Keep the vLLM-SR Dashboard Insights view beside the notebook. During each TUI
turn, correlate the notebook phase marker with the dashboard decision and
selected model. The notebook route table is the durable record if the
dashboard time window moves during the presentation.

## Fallback

If live inference is unavailable:

1. show the actual readiness failure;
2. open the explicitly labeled Verified Rehearsal section;
3. keep the fixture and quality explanation live; and
4. do not imply the saved routes came from the current session.

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
| Quality, routes, and cost | 5 |
| Challenge | 1 |

## Presenter rules

- Run `workshop-status` before opening the notebook.
- Keep one Gateway and one TUI lifecycle.
- Run every phase-marker cell before sending its TUI prompt.
- Paste both real reviewer outputs into the handoff cells.
- Do not continue to Main unless `lab.verify_demo()` passes.
- Use `lab.route_report(source="live")` for the current run.
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
not money. The real direct-GLM comparison is produced by:

```bash
workshop-compare --repetitions 3
```

Do not present same-token GLM repricing as an empirical direct-GLM run.

## Fallback

If live inference is unavailable:

1. show the actual readiness failure;
2. open the explicitly labeled Verified Rehearsal section;
3. keep the fixture and quality explanation live; and
4. do not imply the saved routes came from the current session.

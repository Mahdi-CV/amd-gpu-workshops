# Presenter Guide: Build an OpenClaw Debugging Team

## The two workshop goals

1. Build and operate a visible OpenClaw multi-agent team.
2. Show that one `vllm-sr/auto` endpoint assigns different models to different
   roles while preserving a deterministic quality result.

Do not turn this into a routing benchmark lecture. OpenClaw is the application;
vLLM Semantic Router is the inference policy underneath it.

## Recommended layout

```text
left:   workshop.ipynb
right:  openclaw tui
side:   vLLM-SR Dashboard → Insights
```

## 30-minute run of show

| Segment | Minutes |
| --- | ---: |
| Two goals and recipe route map | 3 |
| Meet `main` and inspect workspace files | 5 |
| See the failing application tests | 4 |
| Add the three specialist agents | 7 |
| Run four interactive TUI turns | 7 |
| Reveal routes, cost, and passing tests | 4 |

## Before presenting

Use a fresh workshop state:

```bash
rm -rf /tmp/openclaw-vsr-simple-state
rm -rf /tmp/openclaw-vsr-simple-agents
rm -rf /tmp/openclaw-vsr-simple-demo
rm -rf notebooks/oracle-ai-adaptive-agent/.deploy/live
```

Set:

```bash
export OPENAI_BASE_URL="https://your-endpoint.example/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="vllm-sr/auto"
export VLLM_SR_DASHBOARD_URL="https://your-dashboard.example"
```

Verify the exact four prompts against the current endpoint before the room
opens. Expected routes for Decision Balance `0.3.2`:

```text
bug_reviewer   code      Qwen3.8-Flash-Next   medium
test_reviewer  code      Qwen3.8-Flash-Next   medium
fixer          agentic   GLM-5.3-Flash         high
main           fast      Qwen3.8-27B           off
```

Fixer continuations may appear as `recovery`; they still remain on GLM.

## Teaching OpenClaw

Slow down for:

- `openclaw agents add`;
- separate workspace directories;
- `AGENTS.md` role instructions;
- `/agent <id>` in the TUI; and
- the difference between no-tools reviewers and the tool-capable Fixer.

The human is deliberately the orchestrator in the main exercise. This keeps
every handoff visible and reliable.

Automatic `sessions_spawn` orchestration is the optional follow-up challenge.

## Teaching vLLM-SR

Explain why the route split is intentional:

- reviewers already have the small artifact, so tool schemas add no value;
- the Fixer must read, edit, and execute, so GLM handles agentic work;
- the final report is explicitly one sentence, so the fast lane is enough.

The application never names any physical model.

## Quality claim

Use only:

```text
Before: 5 failed, 102 passed
After:  107 passed
```

This is a deterministic pytest result. Do not describe it as an LLM-judge
score.

## Cost claim

The notebook reports:

- measured routed relative cost from endpoint headers; and
- a same-token all-GLM estimate.

Verified rehearsal:

```text
Routed measured:             0.03340875 XXX
All-GLM same-token estimate: 0.04042020 XXX
Estimated reduction:        17.35%
Quality gate:               107 passed
```

Say:

> The routed value is measured. The all-GLM value applies GLM's relative factor
> to the exact same token counts. `XXX` is a relative compute unit, not dollars.

## Reliability evidence

The October 24–25, 2026 controlled study produced:

- 81 naturally completed bug-fix runs;
- 81 successful fixes;
- 41/41 explicit-prompt successes; and
- 40/40 naturally completed original-notebook-prompt successes.

One additional run was deliberately terminated while packaging the remote
experiment and is not a model failure.

The study also showed why the workshop needed this redesign: a monolithic
tool-using bug fixer sent every call to GLM. Focused no-tools roles are what
create a meaningful Mixture-of-Models demonstration.

## Fallback

If a live route differs:

1. show the actual Dashboard decision;
2. explain which signal changed;
3. keep the deterministic pytest quality gate; and
4. use the saved rehearsal route table for the intended three-model split.

Do not hide a real routing result.

## Closing line

> We kept the capable OpenClaw team and the passing-test requirement. We let
> the router spend expensive inference only where the role needed it.

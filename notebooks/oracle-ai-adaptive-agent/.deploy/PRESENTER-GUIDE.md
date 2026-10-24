# Presenter Guide: Build the Review Team, Route the Work

## Split-screen layout

Left:

```text
workshop.ipynb
```

Right:

```text
vLLM-SR Dashboard → Insights
```

Keep the Dashboard filtered to the newest records.

## 30-minute run of show

| Segment | Minutes |
| --- | ---: |
| Two workshop goals | 2 |
| Public PR and OpenClaw team | 4 |
| `decision-balance` route map | 4 |
| Precomputed all-GLM card | 3 |
| Live routed panel | 10 |
| Dashboard route reveal | 4 |
| Cost comparison and close | 3 |

## Opening

Say:

> We will keep the OpenClaw team fixed. First I will show what it costs when
> every inference call uses the strongest model. Then we will run the same
> work through one virtual model and watch vLLM Semantic Router allocate model
> and reasoning effort per phase.

## Show the team

```text
repository triage
        |
        +--> correctness/security
        +--> reliability/performance
        +--> integration/control-flow
        |
exact API fact check
        |
final report
```

Explain:

- Triage has repository tools.
- Reviewers receive a frozen inline packet and are tool-free.
- Findings are deduplicated deterministically.
- The reporter produces a short author-facing summary.

## Show the baseline card

The desired final baseline is an actual precomputed run through:

```text
vllm-sr/all-glm
```

Until that is available, the notebook displays:

```text
token-equivalent all-GLM estimate: 0.04651 XXX
```

Say **estimate**, not measurement.

## Audience prediction

Ask the audience which phases need GLM:

| Phase | Prediction |
| --- | --- |
| Coordinator plan | ? |
| Repository triage | ? |
| Code review | ? |
| Exact API facts | ? |
| Final report | ? |

## Run live

Before opening Jupyter, configure:

```bash
export OPENAI_BASE_URL="https://your-endpoint.example/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="vllm-sr/auto"
export VLLM_SR_DASHBOARD_URL="https://your-dashboard.example"
```

Then run the endpoint configuration, proxy, setup, and panel cells in order.

While the panel runs, keep Dashboard Insights visible.

Point out each new record:

1. Requested model remains `vllm-sr/auto`.
2. Decision changes per phase.
3. Physical model changes.
4. Reasoning effort changes.
5. Relative cost accumulates.

Expected route reveal:

```text
Coordinator plan   fast      27B          off
Repository triage  agentic   GLM          high
Code reviewers     code      Flash-Next   medium
API fact check     facts     GLM          low
Final report       fast      27B          off
```

## Findings to highlight

The routed panel found:

- missing pagination for PR commits;
- missing pagination for reviews;
- duplicate review API calls;
- timestamp freshness instead of `commit_id` versus head SHA;
- missing automated coverage;
- PR-description/implementation mismatch;
- current comments minimized before the freshness early return.

The last item is the high-severity cross-function ordering issue.

## Cost reveal

Show:

```text
vllm-sr/auto measured:       0.02136 XXX
all-GLM token-equivalent:    0.04651 XXX
estimated reduction:         54.1%
```

Closing line:

> We did not remove agents, review stages, or capability. We changed only the
> inference policy underneath OpenClaw.

## Fallback

If live inference fails:

1. Open `.deploy/artifacts/workshop.executed.ipynb`.
2. Show `reviewbench-demo-summary.json`.
3. Show `reviewbench-cost.svg`.
4. Open the saved findings JSON.
5. Continue with the Dashboard screenshots or recorded route sequence.

# Build the Review Team, Route the Work

This workshop combines:

- OpenClaw multi-agent orchestration;
- a frozen public pull request;
- an OpenAI-compatible inference endpoint; and
- optional vLLM Semantic Router model/effort observability.

Open:

```text
workshop.ipynb
```

## Endpoint configuration

Set these before starting Jupyter:

```bash
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint.example/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="your-model-id"
```

For the full routing workshop, point them to a vLLM Semantic Router endpoint:

```bash
export OPENAI_MODEL="vllm-sr/auto"
export VLLM_SR_DASHBOARD_URL="https://your-dashboard.example"
```

The API key is never printed or written into the notebook.

## Workshop outcome

The notebook builds a review team with:

- a coordinator;
- correctness/security reviewer;
- reliability/performance reviewer; and
- integration/control-flow reviewer.

The team reviews a frozen public Go pull request. When connected to the
`decision-balance` recipe, different workflow phases route to:

- Qwen3.8-27B with thinking off;
- Qwen3.8-Flash-Next at medium effort; and
- GLM-5.3-Flash at low or high effort.

## Included measured result

```text
Measured routed cost:          0.02136 XXX
All-GLM token-equivalent:      0.04651 XXX
Estimated reduction:           54.1%
```

`XXX` is a relative GPU-cost unit, not dollars.

The all-GLM value is a same-token estimate until a static all-GLM endpoint is
run with the same OpenClaw workflow.

## Internal material

Internal setup scripts, measured artifacts, and the executed backup notebook
are stored under the hidden `.deploy/` directory.

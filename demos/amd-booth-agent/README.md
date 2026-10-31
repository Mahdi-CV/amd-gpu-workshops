# AMD Booth: OpenClaw + vLLM Semantic Router + Fireworks

An interactive booth demo that lets visitors give an OpenClaw agent a task
while one UI explains:

- which OpenClaw agent or subagent is working;
- which vLLM-SR decision matched;
- which model was selected;
- detected semantic and conversation signals;
- selected reasoning effort;
- token usage, latency, and estimated API spend;
- counterfactual cost if every call used premium Kimi K3;
- a secondary comparison against all GLM-5.3-Flash.

## Model pool

| Tier | Runtime | Model | Intended work |
| --- | --- | --- | --- |
| Local | AMD MI300X | Qwen3.8-27B FP8 | fast, standard, and vision requests |
| Cloud | Fireworks | GLM-5.3-Flash | code, tools, facts, and normal agentic work |
| Cloud | Fireworks | Kimi K3 | frontier reasoning, recovery, and long context |

The local model has no external API charge. The UI reports that separately
from hardware cost and uses Fireworks' published token rates for cloud calls.
It compares the routed task against both an all-Kimi premium baseline and an
all-GLM-5.3-Flash economy baseline.

An internal compatibility adapter removes Fireworks-only response metadata
before strict OpenAI response validation in vLLM-SR. It does not alter prompts,
model choices, reasoning content, tool calls, generated content, or usage.

## Deploy

```bash
cd demos/amd-booth-agent
cp .env.example .env
install -m 600 /path/to/fireworks_api_key secrets/fireworks_api_key
./deploy/deploy.sh
sudo ./deploy/install-caddy.sh
```

The image pins OpenClaw 2026.10.9 on its required Node 24.22.1 runtime. The
public UI is reverse-proxied through Caddy:

```text
https://agent.165.245.129.230.sslip.io
```

## Four-hour soak

The soak runner exercises the public HTTPS path with a sequential workload
matrix covering local answers, code repair, tools, browser research, artifacts,
subagents, review, and frontier reasoning. It saves every SSE event, run
snapshot, metric, and artifact incrementally.

```bash
./deploy/soak.py \
  --duration 4h \
  --origin https://agent.165.245.129.230.sslip.io \
  --output soak-results/booth-4h \
  --interval 5s

./deploy/analyze-soak.py soak-results/booth-4h \
  --write-json soak-results/booth-4h/summary.json
```

## Safety

- The Fireworks key is mounted only into the internal compatibility adapter.
- The web app permits one active booth run at a time.
- Prompts and run duration are bounded.
- OpenClaw runs inside an isolated container with no Docker socket or host SSH.
- Booth tasks use public web content and disposable run directories.

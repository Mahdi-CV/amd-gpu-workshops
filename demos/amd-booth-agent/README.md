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

## Deploy

```bash
cd /opt/amd-booth
cp .env.example .env
install -m 600 /path/to/fireworks_api_key secrets/fireworks_api_key
python3 router/render_config.py \
  --input router/decision-balance-base.yaml \
  --output data/router-config/config.yaml
docker compose build booth
docker compose up -d
```

The public UI is reverse-proxied through Caddy:

```text
https://agent.165.245.129.230.sslip.io
```

## Safety

- The Fireworks key is mounted only into the Router.
- The web app permits one active booth run at a time.
- Prompts and run duration are bounded.
- OpenClaw runs inside an isolated container with no Docker socket or host SSH.
- Booth tasks use public web content and disposable run directories.

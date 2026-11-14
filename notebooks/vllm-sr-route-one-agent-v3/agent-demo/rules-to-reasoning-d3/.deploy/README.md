# From Rules to Reasoning

This directory contains hidden deployment and presenter assets for:

```text
From Rules to Reasoning:
Build an Intelligent Model Router with D3 Lite
```

Participant notebooks:

```text
../../route-one-agent-across-two-models-v3.ipynb
  Production Microsoft/Azure Foundry environment

rules-to-reasoning-with-vllm-sr-local-gpu.ipynb
  Hosted AMD GPU environment with locally served task models
```

The participant starts with exact keyword routing, sees why it cannot
understand meaning, then introduces System One and Decision 3.0 D3 Lite.

Participant-facing operations are limited to:

```python
preview_route(prompt)
send_prompt(prompt)
apply_recipe(recipe)
```

There is no participant-facing helper class or generated full-configuration
sequence.

Deployment documentation:

```text
.deploy/foundry-cpu/README.md
```

Presenter material:

```text
.deploy/PRESENTER-GUIDE.md
.deploy/SOLUTION-KEY.md
.deploy/WORKSHOP-PLAN.md
```

Rebuild the notebook:

```bash
uv run --with nbformat python .deploy/bin/build-notebook.py
uv run --with nbformat python .deploy/bin/build-local-gpu-notebook.py
```

The first command writes the production notebook to the established root
deployment filename. The second writes the local-GPU variant in this folder.

Run acceptance inside the production image:

```bash
WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

Expected:

```text
PASS Launch Control -> ROUTE-CONTROL-GREEN
PASS baseline restored
```

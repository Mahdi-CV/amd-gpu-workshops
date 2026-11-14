---
title: From Rules to Reasoning
description: A keyword-first beginner workshop that grows one exact route into a tested semantic policy powered by Decision 3.0 D3 Lite.
---

# Workshop plan

## Audience

Developers and platform engineers who have not used vLLM Semantic Router.
They should understand basic HTTP and LLM inference. No prior routing, System
One, Dashboard, or D3 experience is required.

## Participant outcomes

Participants will:

1. call one OpenAI-compatible routed model;
2. build and inspect an exact keyword route;
3. explain signal, decision, priority, route, and task model;
4. recognize the limitation of exact matching;
5. create and calibrate a D3 Lite System One question;
6. combine semantic and deterministic policy;
7. resolve a three-way priority collision;
8. pass Launch Control; and
9. export a runnable Router starter.

## Learning progression

```text
1. Route an explicit request
2. Follow the request through the Router
3. Expose the exact rule's limitation
4. Route by meaning with D3 Lite
5. Test and customize the question
6. Combine rules with priority
7. Connect an application
8. Complete Launch Control
9. Export the Router
```

The workshop stays inside one engineering launch-assistant story. It never asks
participants to rebuild listener, provider, Dashboard, or runtime boilerplate.

## Participant API surface

Participants see one raw OpenAI-compatible request and then use only:

```python
preview_route(prompt)
send_prompt(prompt)
apply_recipe(recipe)
```

There is no participant-facing `WorkshopLab` class.

## Runtime roles

| Role | Name | Job |
| --- | --- | --- |
| Public entrypoint | `vllm-sr/auto` | Stable application model name |
| Routine task model | `routine-model` | Direct and concise work |
| Reasoning task model | `reasoning-model` | Diagnosis and tradeoffs |
| Decision model | `d3-lite` | Answer System One routing questions |

The task models are Azure Foundry deployments behind local relays. D3 Lite is
packaged into the CPU image and served locally on port `8100`.

## Starter policy

```text
[SECURITY-REVIEW]
-> security-review
-> reasoning-model

otherwise
-> routine-fallback
-> routine-model
```

The semantic policy appears only after the exact policy's limitation is
visible.

## Timing

The beginner path through Launch Control is approximately 100 minutes. A
75-minute delivery can reduce the Prompt Laboratory and make the narrower
question instructor-led.

## Acceptance criteria

Before release:

1. both Foundry relay lanes answer;
2. D3 Lite health is ready;
3. exact positive and negative controls pass;
4. broad semantic routine and reasoning controls pass;
5. the comparison-specific question passes positive and negative controls;
6. the guided private collision selects semantic then private-local;
7. all six Launch Control cases pass;
8. the notebook executes from a clean kernel with challenge placeholders;
9. Dashboard and management API show the same active configuration;
10. the exported package uses `vllm-sr/d3-lite`; and
11. the acceptance test restores the starter configuration.

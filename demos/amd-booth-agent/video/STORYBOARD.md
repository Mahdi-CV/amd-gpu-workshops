# AMD Booth Agent teaser storyboard

Format: 60.000 seconds, 1920×1080, 30 fps, silent-first. All essential meaning
is on screen. The optional voiceover is 136 words and can be recorded at a
measured booth-friendly pace.

| Time | Visual direction | On-screen copy | Optional voiceover |
| --- | --- | --- | --- |
| 00:00.000–00:03.000 | Immediate red-on-black kinetic hook. Three model nodes converge through one router. Exact AMD logo is visible from frame one. | **ONE MISSION.** / **THREE MODELS.** / **ROUTED LIVE.** | “One mission. Three models. Routed live.” |
| 00:03.000–00:08.000 | A mission card lands and the run control arms. Tags establish research, build, citations, and review without making a product-performance claim. | **LIVE DEMO MISSION** / **BUILD AN AMD ACCELERATOR MICROSITE** / Primary sources · Self-contained HTML · Citations · Review / **RUN AGENT →** | “Give OpenClaw a real task—like researching and building an AMD accelerator microsite.” |
| 00:08.000–00:14.000 | The OpenClaw coordinator fans the mission out to Researcher, Builder, and Reviewer. Connector lines illuminate as specialists activate. | **OPENCLAW DELEGATES.** / One mission becomes specialized work. / COORDINATOR → RESEARCHER · BUILDER · REVIEWER | “It delegates research, building, and review to specialist agents.” |
| 00:14.000–00:19.000 | First route: the coordinator’s planning call travels through one endpoint to local Qwen. | **COORDINATOR · PLAN** / **QWEN3.8-27B FP8** / Local · AMD MI300X / EVERYDAY REASONING · MEDIUM / Analysis task · Effort medium | “Every call hits one endpoint. Everyday reasoning goes to local Qwen on AMD Instinct.” |
| 00:19.000–00:24.000 | Second route: the researcher/tool loop selects GLM. Orange route energy and matched-signal chips make the reason visible. | **RESEARCHER · BROWSE PRIMARY SOURCES** / **GLM-5.3-FLASH** / Fireworks · Serverless / TOOL ORCHESTRATION · HIGH / Tools needed · Agentic task · Exact facts | “Tool and exact-fact work routes to GLM.” |
| 00:24.000–00:29.000 | Third route: review escalates to premium Kimi with the maximum requested reasoning effort. The full three-model pool remains visible. | **REVIEWER · FRONTIER REVIEW** / **KIMI K3** / Fireworks · Premium / FRONTIER REASONING · MAXIMUM / High difficulty · Effort maximum | “And frontier review routes to Kimi.” |
| 00:29.000–00:39.000 | A route-intelligence card expands. Task, conversation, and effort signals resolve into an explicit model selection and five-step reasoning-effort meter. Event cards accumulate alongside it. | **EVERY ROUTE EXPLAINS ITSELF.** / Selected model / Why this route / MATCHED SIGNALS / REQUESTED REASONING EFFORT / **VISIBLE IN REAL TIME** | “Matched signals and requested reasoning effort appear as the work happens, so every choice is visible.” |
| 00:39.000–00:47.000 | Two proportional spend bars count up. The routed bar stops at 10.4% of the all-Kimi same-token estimate. Scope note stays on screen throughout. | **EXAMPLE RUN · CLOUD API/TOKEN ESTIMATE** / Routed **$0.00731** / All-Kimi **$0.07050** / **89.6% EST. SAVINGS** / 8,000 prompt · 3,100 output / Same-token estimate. Excludes local AMD Instinct hardware, hosting, power & ops. Not a benchmark. | “For the same example token mix, routing estimates 89.6 percent lower cloud API spend than all Kimi. Local hardware and operating costs are excluded.” |
| 00:47.000–00:55.000 | One semantic-router endpoint fans out to a configurable pool containing a local model, a cloud model, and a specialist model. Three outcome cards establish the general value proposition without tying it to a specific accelerator or provider. | **RETAIN ACCURACY. SAVE COST.** / Retain accuracy targets / Save inference cost / Mix cloud + local models / Quality targets · Cost targets · Deployment choice | “Build a model pool around your workload. Escalate hard requests to capable models, keep routine work efficient, and combine cloud or local inference.” |
| 00:55.000–01:00.000 | Clean closing hold with the AMD lockup and a provider-neutral model-pool flow. The final message remains fully visible long enough to read from a booth aisle. | **BUILD YOUR OWN MIXTURE OF MODELS.** / One endpoint routing across cloud, specialized, and local models / **RETAIN ACCURACY · SAVE COST** / OpenClaw → vLLM Semantic Router → Your Model Pool | “Use one endpoint to route for quality, optimize cost, and mix the models that fit your deployment.” |

## Cost-estimate math used on screen

This is a deliberately labeled illustrative token mix, not measured benchmark
output:

| Routed calls | Prompt tokens | Output tokens | Configured API calculation | Estimate |
| --- | ---: | ---: | --- | ---: |
| Local Qwen, 2 calls | 1,800 | 700 | No external API token charge | $0.00000 |
| Fireworks GLM, 2 calls | 5,400 | 2,200 | $0.15/M prompt + $0.50/M output | $0.00191 |
| Fireworks Kimi, 1 call | 800 | 200 | $3.00/M prompt + $15.00/M output | $0.00540 |
| **Routed total** | **8,000** | **3,100** |  | **$0.00731** |
| **All-Kimi same-token estimate** | **8,000** | **3,100** | $3.00/M prompt + $15.00/M output | **$0.07050** |

Estimated savings: `1 - 0.00731 / 0.07050 = 89.6%`.

The teaser always keeps the scope statement visible with the numbers: cloud
API/token estimates only; local AMD Instinct hardware, hosting, power, and
operating costs are excluded.

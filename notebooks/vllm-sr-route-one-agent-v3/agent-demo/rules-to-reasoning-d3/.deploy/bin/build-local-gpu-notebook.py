#!/usr/bin/env python3
"""Build the local-GPU trial variant from the Foundry participant notebook."""

from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[2]
WORKSHOP_ROOT = ROOT.parents[1]
SOURCE = WORKSHOP_ROOT / "route-one-agent-across-two-models-v3.ipynb"
OUTPUT = ROOT / "rules-to-reasoning-with-vllm-sr-local-gpu.ipynb"


LOCAL_SETUP = r"""
## 0. Connect to the locally served task models

This machine serves both task models locally:

| Route | Local model | OpenAI-compatible endpoint |
| --- | --- | --- |
| Routine route | Gemma 4 12B GGUF | `http://127.0.0.1:8002` |
| Reasoning route | Qwen3 8B GGUF | `http://127.0.0.1:8001` |

Both model servers use the machine's AMD GPU. The Router calls them through
local OpenAI-compatible endpoints:

```text
Router → local endpoint → AMD GPU task model
```

D3 Lite runs separately on the CPU. It supplies routing evidence and does not
write the user-facing answer. The optional PII extension later discovers a
span-capable Vela deployment automatically and skips cleanly if one is not
available on this host.

### Verify the local environment

The task models, Router, D3 Lite, Dashboard, and JupyterLab should already be
running. Run the next cell to verify their connections.
""".strip()


LOCAL_RECOVERY = r"""
### Environment checkpoint

Continue when all six service lines begin with `✓` and both local model
connections report their expected model.

The application-facing model is:

```text
vllm-sr/auto
```

### If a local task model is missing

Open two Jupyter terminals and keep these commands running.

**Terminal 1 — Routine route**

```bash
/usr/local/bin/llama.cpp/build/bin/llama-server \
  -m /models/gemma4/gemma-4-12b-it-qat-q4_0.gguf \
  --host 0.0.0.0 --port 18002 \
  --alias routine-model \
  -ngl 999 --ctx-size 8192 --reasoning-budget 0
```

**Terminal 2 — Reasoning route**

```bash
/usr/local/bin/llama.cpp/build/bin/llama-server \
  -m /models/qwen3/qwen3-8b-q4_k_m.gguf \
  --host 0.0.0.0 --port 18001 \
  --alias reasoning-model \
  -ngl 999 --ctx-size 8192 --reasoning-budget 0
```

If the Router, D3 Lite, or Dashboard is missing, inspect:

```bash
tail -n 100 /workspace/logs/router.log
tail -n 100 /workspace/logs/d3-lite.log
tail -n 100 /workspace/logs/dashboard.log
```

Rerun the environment-check cell after the missing service becomes ready.
""".strip()


def replace_source(cell, source: str) -> None:
    cell.source = source


notebook = nbformat.read(SOURCE, as_version=4)

for cell in notebook.cells:
    source = cell.source

    source = source.replace(
        "Azure Foundry deployment",
        "local GPU model server",
    )
    source = source.replace(
        "| Route | local GPU model server |",
        "| Route | Local GPU model |",
    )
    source = source.replace(
        ">local GPU model server</text>",
        ">Local GPU model server</text>",
    )
    source = source.replace(
        "`FW-Qwen3.8-27B`",
        "Gemma 4 12B GGUF",
    )
    source = source.replace(
        "`FW-GLM-5.3-Flash`",
        "Qwen3 8B GGUF",
    )
    source = source.replace(
        "The application requested `vllm-sr/auto`. The Router selected the logical\n"
        "task-model route, and the local relay forwarded the request to the matching\n"
        "Azure Foundry deployment.",
        "The application requested `vllm-sr/auto`. The Router selected the logical\n"
        "task-model route and forwarded the request to the matching local GPU model.",
    )
    source = source.replace(
        "Section 6 uses `vela3-fast` because Vela can locate exact text spans.",
        "Section 6 uses `vela3-fast` when this host exposes a span-capable Vela deployment.",
    )
    source = source.replace(
        "This environment also includes the\n"
        "  span-capable <code>vela3-fast</code> model. The next cell finds its\n"
        "  deployment name automatically, adds it to a PII signal, activates the recipe,\n"
        "  and shows the spans Vela found.",
        "The next cell finds a span-capable Vela\n"
        "  deployment automatically, adds it to a PII signal, activates the recipe,\n"
        "  and shows the spans Vela found. If this host does not include Vela, the\n"
        "  optional cells skip cleanly.",
    )

    if source.startswith("## 0. Connect to the models on Azure Foundry"):
        source = LOCAL_SETUP
    elif source.startswith("### Environment checkpoint"):
        source = LOCAL_RECOVERY
    elif "ROUTINE_FOUNDRY_MODEL = os.getenv(" in source:
        source = source.replace(
            "ROUTINE_FOUNDRY_MODEL",
            "ROUTINE_LOCAL_MODEL",
        ).replace(
            "REASONING_FOUNDRY_MODEL",
            "REASONING_LOCAL_MODEL",
        ).replace(
            '"FW-Qwen3.8-27B"',
            '"routine-model"',
        ).replace(
            '"FW-GLM-5.3-Flash"',
            '"reasoning-model"',
        ).replace(
            '"Routine Foundry connection"',
            '"Routine local model"',
        ).replace(
            '"Reasoning Foundry connection"',
            '"Reasoning local model"',
        ).replace(
            'print("Configured task-model connections:")',
            'print("Configured local task-model connections:")',
        )

    replace_source(cell, source)

nbformat.write(notebook, OUTPUT)
print(f"Wrote {OUTPUT} ({len(notebook.cells)} cells)")

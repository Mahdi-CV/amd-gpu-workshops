
# AMD GPU Workshops

Welcome to the AMD GPU Workshops repository! This repository hosts multiple workshops and tutorials focused on deploying and utilizing powerful AI models leveraging AMD GPUs. Here you'll find comprehensive materials, including Jupyter notebooks, demonstration assets, and clear instructions to guide your learning and development experience.

## Workshops Available

| Workshop Title                                      | Description                                               | Notebook Link                             |
|-----------------------------------------------------|-----------------------------------------------------------|-------------------------------------------|
| **DeepSeek-R1 Deployment with AMD GPUs**            | Deploying DeepSeek-R1 using vLLM, Open WebUI, and CodeGPT | [deepseekr1_vllm.ipynb](notebooks/deepseekr1_vllm.ipynb) |
| **AI Agent with MCPs using vLLM, Pydantic AI**      | Build Airbnb finder agent usign vLLM, MCP, and Pydantic-AI | [build_agents.ipynb](notebooks/build_agents.ipynb) |

(More workshops will be added soon!)

## Repository Structure

```
.
└── notebooks
    ├── assets
    │   ├── codegpt.gif
    │   ├── dinner_webagent.gif
    │   ├── hf_webagent.gif
    │   ├── openwebui.gif
    │   ├── pacman.gif
    │   ├── snake.gif
    │   └── webui_example.gif
    └── deepseekr1_vllm.ipynb
    └── build_agents.ipynb
```

## Getting Started

### Prerequisites

- Access to AMD GPUs ([Developer access](https://www.amd.com/en/forms/registration/developer-cloud-application.html), [Enterprise partners](https://www.amd.com/en/developer/resources/rocm-hub/dev-ai.html))
- [Docker](https://docs.docker.com/get-docker/) installed and configured
- Python and necessary Python packages (details provided in each notebook)

### Quick Start

Clone this repository:

```bash
git clone git@github.com:Mahdi-CV/amd-gpu-workshops.git
cd notebooks
```

Select the workshop you'd like to explore and follow the instructions provided in the corresponding Jupyter notebook.

Use the provided GIF assets in the `assets` directory for visual guidance and examples.

## Contributing

We welcome contributions, suggestions, and issue reports! Please submit a pull request or create an issue to discuss improvements or report bugs.

---

Enjoy the workshops, and happy coding!

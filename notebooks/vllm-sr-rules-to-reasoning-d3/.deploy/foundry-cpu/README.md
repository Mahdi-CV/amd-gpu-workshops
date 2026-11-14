# Foundry CPU workshop image

This image runs:

- two Azure Foundry task-model relays on `8002` and `8001`;
- Decision 3.0 D3 Lite on CPU port `8100`;
- vLLM Semantic Router on `8898`;
- the management API on `8080`;
- Dashboard on `9000`; and
- JupyterLab on `8888`.

## VM deployment

`vm/setup.sh` uses the already-published
`mahatri/vllm-sr-agent-workshop:v5-foundry-cpu-d3` image as an immutable
runtime base. It bind-mounts this workshop's:

- notebook;
- keyword-first Router configuration;
- platform startup scripts; and
- acceptance test.

This lets the new workshop ship from the Git branch without overwriting the
existing Route One folder or requiring a new image publication.

## Optional dedicated image build

From `notebooks/vllm-sr-rules-to-reasoning-d3/`:

```bash
bash .deploy/foundry-cpu/fetch-d3-lite.sh

docker build \
  -f .deploy/foundry-cpu/Dockerfile \
  -t mahatri/vllm-sr-rules-to-reasoning-d3:v1 \
  .
```

The D3 Lite files are pinned and verified by
`fetch-d3-lite.sh`. The image does not download model files at runtime.

## Active configuration

Inside the container:

```text
/workspace/generated-config/router.yaml
```

On a VM installed by `vm/setup.sh`:

```text
$HOME/rules-to-reasoning-workshop/generated-config/router.yaml
```

The immutable starter template is:

```text
/opt/workshop/config/router.yaml
```

The notebook updates the active Router through:

```text
POST /api/v1/config/validate
PUT  /api/v1/config
```

Editing a YAML file alone does not prove the in-memory Router accepted it.

## Acceptance

Inside the running container:

```bash
WORKSHOP_E2E_CONFIRM_MUTATION=1 \
  python3 /opt/workshop/bin/verify-notebook-e2e.py
```

Expected:

```text
PASS Launch Control -> ROUTE-CONTROL-GREEN
PASS baseline restored
```

The acceptance test covers:

- exact keyword routing;
- broad D3 Lite semantic routing;
- a narrower custom question;
- private-policy priority; and
- all six Launch Control cases.

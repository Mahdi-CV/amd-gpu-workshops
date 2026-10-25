# Deploy the OpenClaw vLLM-SR workshop

This package runs one CPU-only workshop container. The image contains
OpenClaw `2026.10.4`, Node `24.16.0`, JupyterLab, the notebook, and the frozen
debugging fixture. At startup, the root entrypoint reads file-backed secrets,
starts the sanitized proxy on container loopback port `19090`, bootstraps
OpenClaw with the local placeholder key `proxy-local`, and then launches
Jupyter as the unprivileged `workshop` user.

Only Jupyter is published, and only on host loopback:

```text
127.0.0.1:8890 -> container 8888
```

The Gateway is controlled from the workshop runtime, not started as another
Compose service. No GPU device, Docker socket, SSH directory, or host home is
mounted.

## Prerequisites

- Linux with Docker Engine and Docker Compose v2.
- The repository checkout on the deployment host.
- The digest-pinned local base image:
  `rocm@sha256:81cb82398fd6f1c0d2fff67fd7629867814fdeca5f192119e41024a15eb5bd9d`.
- Valid endpoint credentials and a Jupyter token.

Confirm the base is present:

```bash
docker image inspect \
  'rocm@sha256:81cb82398fd6f1c0d2fff67fd7629867814fdeca5f192119e41024a15eb5bd9d' \
  >/dev/null
```

## Prepare the host

Create the persistent workspace:

```bash
sudo install -d -m 0750 -o 1000 -g 1000 \
  /srv/openclaw-vsr-workshop/workspace
```

Create the three root-owned secret files by following
[`secrets/README.md`](secrets/README.md). Then install the non-secret
configuration:

```bash
sudo install -m 0644 config/workshop.env.example \
  /etc/openclaw-vsr-workshop/workshop.env
sudoedit /etc/openclaw-vsr-workshop/workshop.env
```

Set `SOURCE_REVISION` in that file to the commit being built:

```bash
git rev-parse HEAD
```

Do not put API keys or the Jupyter token in the environment file.

## Build and start

From this `.deploy` directory:

```bash
docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  build

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  up -d

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  ps

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-status
```

Startup intentionally fails if a secret is missing, endpoint authentication
returns `401`/`403`, model discovery fails, the fixture is corrupt, or the
workspace is not writable.

## Open Jupyter

From a trusted workstation, tunnel the loopback-only port:

```bash
ssh -L 8890:127.0.0.1:8890 root@165.245.141.106
```

Open `http://127.0.0.1:8890/lab` and enter the token stored in
`/etc/openclaw-vsr-workshop/jupyter_token`.

## Operations

Run packaged commands through Compose:

```bash
# Readiness and version checks
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-status

# Restore the baseline fixture, agents, state, and sanitized route log
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-reset

# Inspect the immutable image/runtime contract
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-verify-image

# Three paired auto-versus-direct-GLM repetitions
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-compare \
    --repetitions 3 \
    --seed 20261025 \
    --output-dir /workspace/results/comparison-3pairs

# Verify an existing comparison summary
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-verify-e2e \
    /workspace/results/comparison-3pairs/summary.json
```

The persistent bind is `/srv/openclaw-vsr-workshop/workspace:/workspace`.
Results belong under `/workspace/results`. Gateway logs can contain model
output; treat them as sensitive and do not include them in a handoff without
review. Container logs rotate at 10 MiB with three files retained.

## Verify the CPU-only boundary

```bash
container_id="$(
  docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
    ps -q workshop
)"

docker inspect "$container_id" \
  --format '{{json .HostConfig.Devices}} {{json .HostConfig.DeviceRequests}}'

docker inspect "$container_id" \
  --format '{{json .HostConfig.PortBindings}}'

docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop sh -lc \
  'env | grep -E "^(CUDA|HIP|HSA|NVIDIA|ROCR|GPU_DEVICE_ORDINAL)" | sort'
```

Expected: no devices or GPU requests, one `127.0.0.1:8890` binding for port
`8888`, and every GPU visibility variable set to `-1`.

## Acceptance checks

A release is ready only when a clean workspace proves:

1. Compose reaches healthy state before the notebook is opened.
2. The frozen baseline is exactly `5 failed, 102 passed`.
3. The four-role flow finishes with exactly `107 passed`.
4. Every route has an explicit phase and stores no prompt, response, or key.
5. `workshop-reset` restores the failing baseline.
6. No secret appears in the image, Compose inspection, OpenClaw state,
   notebook output, route log, or comparison artifacts.
7. The generated notebook matches its builder check.

## Stop or remove

Stop the container without deleting the persistent workspace:

```bash
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env down
```

Do not use broad `docker system prune` or generic process-killing commands on
the shared host. Preserve `/srv/openclaw-vsr-workshop/workspace/results` when
cleaning run-specific state.

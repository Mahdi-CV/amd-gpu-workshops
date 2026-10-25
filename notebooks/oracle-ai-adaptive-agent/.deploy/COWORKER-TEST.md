# Coworker Test Guide

Date: October 25, 2026

Server:

```text
root@165.245.141.106
```

The workshop runs in a separate CPU-only container. Do not stop or modify the
existing `rocm` container on port 8888.

## 1. Verify the stack

```bash
ssh root@165.245.141.106
cd /srv/openclaw-vsr-workshop/src/.deploy

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  ps

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-status
```

Expected:

```text
✓ OpenClaw 2026.10.4
✓ vLLM-SR proxy
✓ OpenClaw base state
✓ debugging fixture
✓ writable workspace
○ Gateway: stopped
✓ GPU devices hidden
```

## 2. Open Jupyter

On the workstation:

```bash
ssh -L 8890:127.0.0.1:8890 root@165.245.141.106
```

Open:

```text
http://127.0.0.1:8890/lab
```

Use the Jupyter token supplied separately by the workshop owner.

Open `workshop.ipynb`.

## 3. Run the interactive workshop

Run cells in order.

Hard gates:

```text
Baseline: 5 failed, 102 passed
Final:    107 passed
Tests unchanged: true
Exact source-only patch: true
```

Before every TUI prompt, run its `lab.mark_phase(...)` cell.

Expected live routes:

| Phase | Decision | Model |
| --- | --- | --- |
| `bug_reviewer` | `code` | `qwen/qwen3.8-flash-next` |
| `test_reviewer` | `code` | `qwen/qwen3.8-flash-next` |
| `fixer` | `agentic` or `recovery` | `zai/glm-5.3-flash` |
| `main` | `fast` | `qwen/qwen3.8-27b` |

The reviewers and `main` may declare three minimal-profile tools. That is
normal. They should not actually invoke filesystem or execution tools.

## 4. Run the policy comparison

Inside the server container:

```bash
cd /srv/openclaw-vsr-workshop/src/.deploy

docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop \
  workshop-compare \
    --repetitions 3 \
    --seed 20261025 \
    --output-dir /workspace/results/coworker-comparison
```

Verify the generated summary:

```bash
docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop \
  workshop-verify-e2e \
    /workspace/results/coworker-comparison/summary.json
```

Both policies must complete all three runs with `107 passed`.

## 5. Return these artifacts

From:

```text
/srv/openclaw-vsr-workshop/workspace/results/coworker-comparison/
```

Return:

- `summary.json`
- `comparison.csv`
- `report.md`
- each arm's `routes.jsonl`
- pytest before/after outputs
- patch diffs
- agent stdout/stderr/JSON files
- a Dashboard Insights screenshot
- a TUI screenshot showing all four agent identities

Also return:

```bash
docker image inspect openclaw-vsr-workshop:local \
  --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'

sha256sum \
  /srv/openclaw-vsr-workshop/src/workshop.ipynb \
  /srv/openclaw-vsr-workshop/src/.deploy/artifacts/simple-route-results.json
```

Do not return:

- API keys;
- Jupyter tokens;
- OpenClaw state databases; or
- unrestricted environment dumps.

## 6. Reset for another tester

```bash
docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  exec workshop workshop-reset --full
```

To stop only the workshop stack:

```bash
docker compose \
  --env-file /etc/openclaw-vsr-workshop/workshop.env \
  down
```

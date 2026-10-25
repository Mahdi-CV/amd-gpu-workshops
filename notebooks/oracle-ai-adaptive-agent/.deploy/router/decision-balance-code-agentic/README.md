# Decision Balance code-agentic overlay

This overlay adds one Decision Balance route for multi-turn code review and
debugging agents:

```text
800  recovery       -> GLM-5.3-Flash, max
750  code_agentic   -> Qwen3.8-Flash-Next, medium
700  agentic        -> GLM-5.3-Flash, high
450  code           -> Qwen3.8-Flash-Next, medium
100  fast           -> Qwen3.8-27B, thinking off
```

It preserves GLM for:

- user corrections through the higher-priority `recovery` route;
- general, non-code tool orchestration through `agentic`;
- requests that do not produce a confident `task:code` decision.

It moves requests to Flash-Next only when both are true:

1. the decision model identifies `task:code`; and
2. the request declares tools or continues an active tool loop.

The overlay does not contain backend endpoints, credentials, global services,
or deployment-specific guard changes. `patch_config.py` inserts the decision
into an existing compatible Decision Balance config and preserves the rest of
that deployment.

## Prerequisites

- A Decision Balance `0.3.x` config containing `recovery` priority `800`,
  `agentic` priority `700`, and `code` priority `450`.
- Provider model `qwen/qwen3.8-flash-next`.
- Python 3 and PyYAML.
- `vllm-sr` for local validation.
- A management API token when hot-applying through `deploy.py`.

Keep API keys and management tokens in files or environment variables. Never
put them in the router config, command line, notebook, or Git history.

## 1. Generate a candidate config

```bash
python3 patch_config.py \
  --input /path/to/active/config.yaml \
  --output /tmp/config.code-agentic.yaml
```

The patcher is idempotent. If the exact decision already exists, it reports
`"changed": false`. It refuses:

- an incompatible Decision Balance priority layout;
- a conflicting priority `750`;
- a different existing `code_agentic` decision, unless explicitly reviewed
  and replaced with `--replace-existing`.

Review the only expected change:

```bash
diff -u \
  /path/to/active/config.yaml \
  /tmp/config.code-agentic.yaml
```

## 2. Validate locally

```bash
vllm-sr config validate \
  --offline \
  --config /tmp/config.code-agentic.yaml
```

## 3. Dry-run against a live Router

Tunnel or access the management endpoint from a trusted operator host. The
default below matches a locally exposed management API:

```bash
python3 deploy.py \
  --config /tmp/config.code-agentic.yaml \
  --endpoint http://127.0.0.1:18080 \
  --token-file /root/secrets/vsr-management-token \
  --receipt-dir /tmp/code-agentic-plan
```

Without `--apply`, the script only:

1. reads the current ETag;
2. validates the candidate through the live Router;
3. requests a replace plan;
4. saves redacted receipts.

## 4. Hot-apply after review

```bash
python3 deploy.py \
  --config /tmp/config.code-agentic.yaml \
  --endpoint http://127.0.0.1:18080 \
  --token-file /root/secrets/vsr-management-token \
  --receipt-dir /root/router-receipts/code-agentic-apply \
  --apply
```

The Router performs compare-and-swap with the planned ETag, validates again,
backs up the previous config, persists the replacement, and hot-activates it.
The script waits until the active config hash matches the candidate.

Do not restart vLLM backends for this routing-only change.

## 5. Verify the intended split

```bash
python3 probe.py \
  --base-url https://your-router.example/v1 \
  --api-key-file /root/secrets/router-api-key \
  --output /tmp/code-agentic-probes.json
```

The probe requires:

| Case | Expected decision | Expected model |
| --- | --- | --- |
| Code with tools | `code_agentic` | Flash-Next |
| Generic agentic tools | `agentic` | GLM |
| Code without tools | `code` | Flash-Next |
| Correction/retry | `recovery` | GLM |

## OpenClaw 2.0 panel compatibility

OpenClaw `2026.10.4+` needs spawn authority authored on the coordinator agent.
Use:

```bash
openclaw config set \
  agents.entries.main.subagents.allowAgents \
  '["performance","readability"]' \
  --strict-json

openclaw config set \
  agents.entries.main.tools.alsoAllow \
  '["sessions_spawn","sessions_yield","subagents"]' \
  --strict-json
```

The older global/default paths may validate but do not expose the higher-risk
`sessions_spawn` tool to `main`.

## Validated evidence

Live deployment on an 8 x MI300X node, October 25, 2026:

### Multi-agent review panel

| Metric | Original recipe | With `code_agentic` |
| --- | ---: | ---: |
| Calls | 21 | 23 |
| Flash-Next calls | 2 | 18 |
| GLM calls | 19 | 5 |
| Relative compute | 0.11377763 XXX | 0.06615557 XXX |
| Compute reduction | — | 41.86% |

Both specialist reports and the merged report remained complete. GLM continued
to handle coordinator-style agentic turns. The sum of individual request
latencies was not lower, so this result is a compute/model-mix claim rather
than a universal latency claim.

### Deterministic Fixer smoke

```text
Auto routes:
  5 code_agentic -> Flash-Next
  5 recovery     -> GLM
  1 fast         -> Qwen3.8-27B

Auto:       107 tests passed, 0.04775879 XXX
Direct GLM: 107 tests passed, 0.06613529 XXX
Reduction:  27.79%
```

See `../../artifacts/code-agentic-live-validation-20261025.*` for the compact
machine-readable and presenter-readable evidence.

## Rollback

Use the Router-managed previous config version:

```bash
token="$(cat /root/secrets/vsr-management-token)"
etag="$(
  curl -fsS -D - \
    -H "Authorization: Bearer $token" \
    http://127.0.0.1:18080/api/v1/config \
    -o /dev/null |
  awk 'tolower($1)=="etag:" {gsub("\r", "", $2); print $2}'
)"

curl -fsS \
  -X POST \
  -H "Authorization: Bearer $token" \
  -H "Content-Type: application/json" \
  -H "If-Match: $etag" \
  -d '{"config_version": 1}' \
  http://127.0.0.1:18080/api/v1/config/rollback
```

Use the actual previous version from `/api/v1/config/versions`; `1` is only the
validated Oracle demo example.

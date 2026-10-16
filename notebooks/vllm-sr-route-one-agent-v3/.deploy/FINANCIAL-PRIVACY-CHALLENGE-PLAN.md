# Financial Privacy Challenge Plan

Status: research complete, implementation paused

This document preserves the proposed redesign of the final workshop challenge.
Do not change the participant notebook from this plan until the other tutorial
issues have been reviewed.

## Goal

Replace the generic custom-keyword exercise with a realistic financial-data
challenge:

> Produce a quarter-end financial risk memo while preventing raw customer data
> from reaching a cloud-hosted model.

vLLM Semantic Router remains the router. The smaller model is the private,
locally hosted processing lane. The larger model represents a cloud or
externally hosted reasoning lane.

The workshop deployment will simulate the cloud boundary because both vLLM
models run in the participant container. The notebook must say this explicitly
and must not imply that the larger model is physically remote.

## Recommended design

Use a two-step application workflow:

```text
synthetic restricted financial records
                 |
                 v
             vllm-sr/auto
                 |
          privacy policy
                 |
       +---------+---------+
       |                   |
       v                   v
small local model    simulated cloud model
raw/private work     sanitized aggregate only
       |                   |
       +---------+---------+
                 |
                 v
        financial risk memo
```

The raw dataset must remain on the local route. A deterministic application
step produces a sanitized aggregate. Only that aggregate may be sent through
the cloud route for deeper synthesis.

This is preferable to:

- routing every financial request locally, which is safe but does not
  demonstrate controlled cloud use; or
- automatically chaining local sanitization and cloud reasoning inside the
  Router, which belongs in a later Workflow Mixture-of-Models workshop.

## Challenge story

The CFO needs a quarter-end exposure and risk memo.

The source ledger contains:

- customer identifiers;
- personal contact information;
- account and payment identifiers;
- balances and exposure amounts;
- delinquency and risk indicators; and
- internal analyst notes.

The participant may use the larger reasoning model, but that model must never
receive the raw ledger or its private fields.

The participant succeeds when:

1. raw financial records use the local model;
2. difficult analysis containing private data remains local;
3. a sanitized aggregate can use the simulated cloud model;
4. an ordinary public reasoning request can use the cloud model;
5. classifier uncertainty cannot silently open a cloud route;
6. private request and response bodies are not retained in Router Replay; and
7. the cloud-boundary audit reports zero private-data violations.

## Dataset

Create a small, repository-owned synthetic dataset instead of downloading a
large third-party corpus.

Proposed files:

```text
financial-challenge/
├── restricted-customer-exposure.csv
├── dataset-policy.json
└── README.md
```

Suggested CSV columns:

```text
customer_id
customer_name
email
phone
ssn
iban
account_id
region
product
exposure_usd
days_past_due
risk_band
internal_note
privacy_canary
```

Dataset requirements:

- 12 to 20 rows;
- entirely fictional values generated for the workshop;
- reserved email domains such as `example.test`;
- clearly synthetic personal and financial identifiers;
- enough numerical variation for a useful risk summary;
- a unique canary such as `PRIVATE-CANARY-7K2M`;
- an explicit `restricted` classification; and
- no real customer, employee, account, or payment data.

The public aggregate may contain only:

```text
region
total_exposure_usd
delinquent_exposure_usd
high_risk_account_count
product_concentration_percent
```

It must not contain row-level values, identifiers, notes, or the privacy
canary.

IBM AML-Data is a useful example of a synthetic financial transaction schema,
but even its small sets are too large for this workshop. The challenge should
use a tiny purpose-built dataset with a known expected result.

## Participant flow

### 1. Observe the unsafe baseline

Send a hard analysis request containing the synthetic restricted ledger before
the privacy policy is installed.

The existing complexity route should select the simulated cloud model. The
cloud audit should report a controlled synthetic-data violation:

```text
Privacy boundary test: FAILED
The simulated cloud endpoint received restricted content.
```

This is an intentional learning failure using synthetic data only.

### 2. Add privacy evidence

Participants add three complementary signals.

#### Restricted-data metadata

The application attaches:

```json
{
  "metadata": {
    "data_classification": "restricted"
  }
}
```

This is a deterministic application hint. It must not be presented as
authorization because request metadata is caller-controlled.

#### Restricted financial markers

Add a keyword signal for deterministic markers such as:

```text
CLASSIFICATION: RESTRICTED
customer_name
account_id
internal_note
privacy_canary
```

This protects confidential business information that may not qualify as PII.

#### PII detection

Add a PII signal with:

```yaml
name: financial-pii
threshold: 0.85
include_history: true
pii_types_allowed: []
```

The intended lesson is:

> PII detection is one source of evidence. It is not the entire privacy
> policy.

Balances, risk scores, forecasts, and internal notes can be confidential even
when they contain no personal identifier.

### 3. Create the private financial route

The private route should have:

```text
decision: private-financial-data
priority: 300
model: routine-model
```

It matches when any of these is true:

```text
restricted metadata
OR restricted financial marker
OR detected PII
```

The decision must use:

```yaml
rules:
  on_unknown: fail_request
```

An unavailable or incomplete privacy classifier must not create a clean result
that permits cloud routing.

### 4. Harden every cloud-capable route

Adding a high-priority local decision is not sufficient. The existing
reasoning route must be changed so the simulated cloud model is eligible only
when all of these are true:

```text
hard reasoning
AND public-summary classification
AND no restricted marker
AND no PII
```

The local model remains the fallback.

Expected priority order:

| Priority | Decision | Model |
| ---: | --- | --- |
| 300 | `private-financial-data` | `routine-model` |
| 200 | `cloud-financial-analysis` | `reasoning-model` |
| 100 | `routine-lane` | `routine-model` |

The central lesson is:

> Cloud use must be positively authorized. It must not occur merely because a
> privacy rule failed to match.

### 5. Limit storage and tools

The private route should:

- keep Router Replay enabled only if request and response body capture are
  disabled;
- emit `retention.drop: true`;
- use no tools or an explicit local-only tool allowlist; and
- continue using the local model when several decisions match.

Recommended replay override:

```yaml
plugins:
  - type: router_replay
    configuration:
      enabled: true
      capture_request_body: false
      capture_response_body: false
```

This preserves decision and signal evidence without storing the private body.

### 6. Produce a safe aggregate

Provide a visible, deterministic Python function that:

1. reads the CSV;
2. calculates the required totals;
3. removes all restricted columns;
4. checks for the privacy canary;
5. checks for prohibited field names and PII patterns; and
6. emits a compact public summary.

Do not ask an LLM alone to sanitize the data. Nondeterministic sanitization
would make the workshop unreliable and weaken the privacy claim.

The local model may still produce a private analyst view from the detailed
records. That response remains inside the local route.

### 7. Use the cloud route safely

Start a new conversation containing only the sanitized aggregate and attach:

```json
{
  "metadata": {
    "data_classification": "public-summary"
  }
}
```

Ask the larger model to compare concentration risks and write the final
executive memo.

Starting a new conversation matters. A conversation whose earlier turns
contain PII should remain on the local route when `include_history: true`.

## Cloud-boundary audit

Place a small audit proxy between the Router and the reasoning-model endpoint:

```text
Router -> cloud audit proxy -> reasoning model
```

The proxy should:

- count cloud-bound requests;
- detect the privacy canary;
- detect prohibited column names;
- detect configured PII patterns;
- reject a violating request before forwarding it;
- record only request hashes, timestamps, and detection results; and
- never persist the raw request body.

Participant-facing evidence should look like:

```text
Raw restricted request
  selected decision: private-financial-data
  selected model: routine-model
  cloud requests added: 0
  privacy violations: 0
  PASS

Sanitized summary
  selected decision: cloud-financial-analysis
  selected model: reasoning-model
  cloud requests added: 1
  privacy violations: 0
  PASS
```

This is stronger evidence than checking only the selected-model header.

## Important technical findings

The workshop currently pins Semantic Router revision:

```text
c1e00bb0fada18b891cbe20afb663b201cad0cb6
```

That revision supports:

- PII routing signals;
- `include_history: true`;
- classifier `on_error: block`;
- decision `rules.on_unknown: fail_request`;
- metadata signals;
- retention directives; and
- per-decision Router Replay capture controls.

The current workshop image does not explicitly preinstall the PII classifier.
The Router can download required models, but live workshop startup must not
depend on internet access.

Before enabling the challenge, the image must:

1. bake the pinned Vela PII model into the image or prewarmed model volume;
2. record its repository revision and artifact checksums;
3. configure the PII model to run on CPU;
4. verify that the Router starts with network access disabled; and
5. run a positive and negative PII diagnostic during image acceptance.

The pinned Vela PII model is:

```text
llm-semantic-router/Vela-1.0-Encoder-307M-PII
revision: 6d3300c4bd7975f30a664503f6c725cf1fbbad48
```

The built-in model covers 17 entity types and uses a 35-label BIO mapping.

Do not rely on keyword or embedding signals alone to protect prior turns.
Upstream issue #2880 tracks history handling for those signal families. The
challenge should use PII `include_history: true`, repeat deterministic
classification context on relevant calls, and begin the sanitized cloud step
as a new conversation.

## Acceptance matrix

| Test | Expected result |
| --- | --- |
| PII diagnostic with synthetic email, phone, SSN, and IBAN | PII detected |
| Clean public control | No PII detected |
| Raw restricted ledger | Local model |
| Hard restricted analysis | Local model despite complexity match |
| Restricted metadata without obvious PII | Local model |
| Prior user turn contains PII | Later turn remains local |
| Classifier result is unknown | Request fails rather than selecting cloud |
| Public hard reasoning | Simulated cloud model |
| Sanitized financial aggregate | Simulated cloud model |
| Raw canary at cloud audit proxy | Request rejected |
| Completed workflow | Zero cloud privacy violations |
| Private replay record | No request or response body |
| Reset | Baseline configuration restored |

## Workshop timing

Plan approximately 15 minutes:

| Activity | Minutes |
| --- | ---: |
| Story and controlled baseline failure | 2 |
| Add privacy signals | 4 |
| Add the local route and harden the cloud route | 4 |
| Deploy and run collision tests | 2 |
| Build the safe summary and complete the memo | 3 |

This should replace the current generic Section 10 challenge rather than be
added after it.

## Expected implementation surfaces

Likely additions:

```text
financial-challenge/restricted-customer-exposure.csv
financial-challenge/dataset-policy.json
financial-challenge/README.md
.deploy/bin/cloud-egress-audit.py
```

Likely updates:

```text
route-one-agent-across-two-models-v3.ipynb
workshop_lab.py
.deploy/config/router-demo.yaml
.deploy/bin/start-platform.sh
.deploy/bin/status.sh
.deploy/bin/reset.sh
.deploy/bin/verify-image.sh
.deploy/bin/verify-notebook-e2e.py
.deploy/Dockerfile
.deploy/PRESENTER-GUIDE.md
.deploy/SOLUTION-KEY.md
.deploy/README.md
```

## Implementation order

1. Prove the PII classifier works with the exact pinned Router and image.
2. Bake the pinned classifier artifact and verify offline startup.
3. Create the small synthetic dataset and deterministic sanitizer.
4. Add the cloud egress audit proxy and its health endpoint.
5. Prototype the final routing policy outside the notebook.
6. Add positive, negative, collision, history, replay, and egress tests.
7. Replace the generic challenge cells.
8. Update presenter guidance and the private solution key.
9. Build the image and run the complete notebook on MI300.

## Non-goals

This challenge must not claim:

- regulatory compliance;
- guaranteed detection of every sensitive value;
- that the larger model is physically remote in the workshop;
- that synthetic data is automatically anonymous;
- that metadata supplied by an untrusted caller grants cloud permission; or
- that routing alone replaces network isolation, encryption, access control,
  logging policy, or data-loss prevention.

## Research references

- vLLM Semantic Router Privacy-First recipe and probes
- vLLM Semantic Router PII signal documentation
- vLLM Semantic Router metadata and retention documentation
- vLLM Semantic Router issue #2880 on history-aware keyword and embedding signals
- Vela 1.0 Encoder 307M PII model card
- NIST Privacy Framework
- NIST guidance on synthetic data privacy risks
- OWASP guidance on sensitive information disclosure in LLM applications
- IBM AML-Data synthetic transaction corpus

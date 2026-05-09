# Quickstart: Policy-Loop Vertical Slice

**Branch**: `001-policy-loop-vertical-slice` | **Date**: 2026-05-09

This quickstart stands up the entire stack on a clean machine and walks through the end-to-end policy loop. Target wall time: under 10 minutes (per Spec SC-008).

## Prerequisites

- Docker Desktop 4.30+ or Docker Engine 25+ with Compose v2
- GNU Make 4.x
- Python 3.11.9 (only required if you want to run tests outside containers; the Compose stack does not need a host Python)
- Roughly 18 GB of free disk for the model weight cache and image layers
- For the GPU profile: a CUDA-capable GPU with at least 16 GB of memory and the NVIDIA Container Toolkit. The CPU-fallback profile requires no GPU.

## Clone and bootstrap

```bash
git clone https://github.com/<org>/collectmind.git
cd collectmind
git checkout 001-policy-loop-vertical-slice
cp .env.example .env
```

Edit `.env` to set, at minimum:

| Variable | Default | Purpose |
|---|---|---|
| `OAUTH2_ISSUER_URL` | `https://issuer.local/realms/collectmind` | OAuth2 issuer; the local Compose stack runs a small mock issuer that signs tokens for the seeded tenant. |
| `OAUTH2_AUDIENCE` | `collectmind-api` | Required `aud` claim. |
| `SLM_PROFILE` | `gpu` | Set to `cpu` to use llama.cpp + GGUF instead of vLLM. |
| `TIME_ACCELERATION_FACTOR` | `1.0` | Logical-time scaling per FR-009a. Tests run at `3600.0` so a one-hour window completes in a second. |

## One-command stack

```bash
make up           # docker compose up -d, with the SLM_PROFILE Compose profile
```

Wait for the stack to be ready:

```bash
make wait-ready   # blocks until /ready returns 200
```

The stack now exposes:

| Endpoint | Local URL | Purpose |
|---|---|---|
| Orchestration API | `http://localhost:8081/api/v1` | `POST /findings`, `POST /erasure-requests`, health |
| Query API | `http://localhost:8082/api/v1` | Policy, version history, outcome, audit queries |
| Grafana dashboard | `http://localhost:3000` | The "CollectMind end-to-end" dashboard (auto-provisioned) |
| Tempo (traces) | `http://localhost:3200` | OTLP receiver |
| Loki (logs) | `http://localhost:3100` | OTLP receiver |
| Prometheus | `http://localhost:9090` | Scrapes services and the SLM container |
| Mock OAuth2 issuer | `http://localhost:8088` | Issues short-lived JWTs for the seeded tenant |

## Smoke test the end-to-end path

```bash
# 1) Mint a JWT for the seeded tenant (feature-001-default).
TOKEN=$(curl -s -X POST http://localhost:8088/token \
  -d 'grant_type=client_credentials&client_id=feature-001-default&client_secret=local-dev-only' \
  | jq -r .access_token)

# 2) Publish a brake-wear diagnostic finding.
curl -s -X POST http://localhost:8081/api/v1/findings \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d @docs/examples/finding-brake-wear.json

# 3) Watch the dashboard at http://localhost:3000 (anonymous read enabled in dev).
#    The "Generation funnel" panel should populate within seconds.

# 4) Query the resulting policy and outcome.
FINDING_ID=$(jq -r .finding_id docs/examples/finding-brake-wear.json)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8082/api/v1/findings/$FINDING_ID/outcome" | jq
```

If the time-acceleration factor is set to a high value in `.env` for development convenience, the outcome record appears within a few seconds; otherwise it appears at the natural collection-window boundary.

## Run the tests

```bash
make test         # unit + contract + integration (real local stack incl. real SLM in CPU profile)
make test-unit    # unit only
make test-contract
make test-integration
make load-smoke   # PR-tier Locust against the deterministic-fingerprint stub
```

`make test` is the same target the PR-tier CI workflow runs (`.github/workflows/ci.yaml`).

## Run the workflow-dispatch tiers locally

These are gated to `workflow_dispatch` and the nightly schedule in CI, but you can run them locally:

```bash
make load-full    # Full Locust profile against the real SLM (workflow_dispatch tier)
make soak         # 24-hour Locust soak (nightly tier; expect a long run)
make eval         # SLM eval suite (RAGAS gates plus golden-example contract tests)
```

Each writes a structured report under `reports/`.

## Tear down

```bash
make down         # docker compose down
make clean        # also drops volumes (Postgres, Redis, Kafka data)
```

## Where to read next

- [`spec.md`](./spec.md): the requirements this feature delivers.
- [`plan.md`](./plan.md): the technology and structure decisions.
- [`research.md`](./research.md): per-decision rationale and alternatives.
- [`data-model.md`](./data-model.md): tables, fields, relationships, state transitions.
- [`contracts/`](./contracts/): OpenAPI 3.1 and AsyncAPI 3.0 contracts.
- `../../docs/adr/`: ADR-0001 through ADR-0005.
- `../../docs/runbook/`: one runbook page per alert and per known failure mode.
- `../../docs/security/threat-model.md`: feature-001 threat model.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `make up` exits with `cuda` driver error in the SLM container | GPU not available, CPU profile not selected | `SLM_PROFILE=cpu make up` |
| `/ready` reports `slm_weight_digest_mismatch` | Cached weights diverged from the manifest | `make clean-weights && make up` |
| `POST /findings` returns 401 with `code=AUTH_TENANT_MISSING` | The minted JWT does not carry a non-empty `tenant_id` claim | Check the mock issuer's seeded clients in `infra/compose/issuer-config.yaml` |
| Grafana dashboard shows no data | Prometheus has not finished its first scrape | Wait 15 seconds; if persistent, check `docker compose logs prometheus` |
| `make test-integration` times out on first run | SLM weight download in progress | Subsequent runs hit the host weight cache and complete in seconds |

A complete runbook lives at `docs/runbook/`.

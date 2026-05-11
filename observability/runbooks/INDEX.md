# CollectMind Runbooks

One page per alert and per known failure mode (Spec FR-022, Constitution Principle V). The CI guard at `scripts/check_runbook_completeness.py` (T113, planned in Phase 5) refuses to merge if any alert rule lacks a runbook entry.

## Failure-mode runbooks

| Page | Status | Description |
|---|---|---|
| [`slm-container-oom.md`](slm-container-oom.md) | (stub) | SLM container OOM-killed. |
| [`slm-weight-digest-mismatch.md`](slm-weight-digest-mismatch.md) | (stub) | SLM weight SHA-256 verification fails at start. |
| [`vllm-healthcheck-failure.md`](vllm-healthcheck-failure.md) | (stub) | vLLM `/health` failing. |
| [`cpu-fallback-activation.md`](cpu-fallback-activation.md) | (stub) | SLM is running on the CPU profile in a non-dev environment. |
| [`gpu-node-group-capacity-exhausted.md`](gpu-node-group-capacity-exhausted.md) | (stub) | ECS-on-EC2 ASG cannot scale up. |
| [`kafka-lag.md`](kafka-lag.md) | (stub) | Consumer group lag elevated. |
| [`postgres-pool-exhausted.md`](postgres-pool-exhausted.md) | (stub) | asyncpg pool saturated. |
| [`redis-evictions.md`](redis-evictions.md) | (stub) | hot-store evictions elevated. |
| [`dead-letter-non-empty.md`](dead-letter-non-empty.md) | (stub) | events routed to the dead-letter queue. |
| [`container-oom.md`](container-oom.md) | (stub) | generic container OOM. |
| [`oauth2-issuer-unavailable.md`](oauth2-issuer-unavailable.md) | (stub) | OAuth2 issuer or JWKS endpoint unreachable. |

## Alert runbooks (per binding SLO)

| Page | Status | Description |
|---|---|---|
| [`slo-001-latency.md`](slo-001-latency.md) | (stub) | SC-001 diagnostic-event-to-policy-deployed latency p95 breach. |
| [`slo-002-success-rate.md`](slo-002-success-rate.md) | (stub) | SC-002 sustained ingest success-rate breach. |
| [`slo-003-soak.md`](slo-003-soak.md) | (stub) | SC-003 soak memory growth or error-rate breach. |
| [`slo-004-query-latency.md`](slo-004-query-latency.md) | (stub) | SC-004 query p95 breach. |
| [`slo-005-recovery.md`](slo-005-recovery.md) | (stub) | SC-005 recovery-from-outage exceeded. |
| [`slo-006-dashboard-lag.md`](slo-006-dashboard-lag.md) | (stub) | SC-006 dashboard lag exceeded. |
| [`slo-010-outcome-write-delay.md`](slo-010-outcome-write-delay.md) | (stub) | SC-010 outcome write delay breach. |
| [`slo-012-availability.md`](slo-012-availability.md) | (stub) | SC-012 availability breach. |

## Phase 3 content delta

No per-page runbook content was added during Phase 3 (US1 implementation). Every entry above remains a stub. Per-page authoring lands in Phase 4 at T112 (alongside the alert-rule YAML at T111).

Phase 3 did produce one operational note worth recording without a dedicated alert: **Docker Desktop instability** surfaced once during the closure session. The recovery procedure (restart Docker Desktop, re-run `docker compose -f infra/compose/docker-compose.yaml up -d`, wait for `/ready`) is documented in `specs/001-policy-loop-vertical-slice/quickstart.md` under the troubleshooting table. When the per-failure-mode pages land in Phase 4, that procedure becomes its own runbook page (`docker-desktop-daemon-down.md`).

## Per-page contents (mandatory)

Each runbook page MUST contain: symptoms, dashboard link, mitigation steps, escalation, related ADRs, related FRs. The CI guard at T113 will refuse PRs whose alert rules reference a page without those sections.

## Entry point

This INDEX.md is the entry point reviewers and on-call engineers use. The per-page files land in Phase 4 at T112.

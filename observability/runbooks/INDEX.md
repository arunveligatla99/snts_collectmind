# CollectMind Runbooks

One page per alert and per known failure mode (Spec FR-022, Constitution Principle V). The CI guard at `scripts/check_runbook_completeness.py` (T113) refuses to merge if any alert rule in `observability/prometheus/rules.yaml` lacks a runbook entry under `observability/runbooks/` with the canonical section set.

## Failure-mode runbooks

| Page | Description |
|---|---|
| [`slm-container-oom.md`](slm-container-oom.md) | SLM container OOM-killed. |
| [`slm-weight-digest-mismatch.md`](slm-weight-digest-mismatch.md) | SLM weight SHA-256 verification fails at start. |
| [`vllm-healthcheck-failure.md`](vllm-healthcheck-failure.md) | vLLM `/health` failing. |
| [`cpu-fallback-activation.md`](cpu-fallback-activation.md) | SLM is running on the CPU profile in a non-dev environment. |
| [`gpu-node-group-capacity-exhausted.md`](gpu-node-group-capacity-exhausted.md) | ECS-on-EC2 ASG cannot scale up. |
| [`kafka-lag.md`](kafka-lag.md) | Consumer group lag elevated. |
| [`postgres-pool-exhausted.md`](postgres-pool-exhausted.md) | asyncpg pool saturated. |
| [`redis-evictions.md`](redis-evictions.md) | hot-store evictions elevated. |
| [`dead-letter-non-empty.md`](dead-letter-non-empty.md) | events routed to the dead-letter queue. |
| [`container-oom.md`](container-oom.md) | generic container OOM. |
| [`oauth2-issuer-unavailable.md`](oauth2-issuer-unavailable.md) | OAuth2 issuer or JWKS endpoint unreachable. |
| [`docker-desktop-daemon-down.md`](docker-desktop-daemon-down.md) | Local-dev Docker Desktop daemon unreachable. |

## Alert runbooks (per binding SLO)

Each page below is referenced by exactly one alert in `observability/prometheus/rules.yaml`.

| Page | Alert | Description |
|---|---|---|
| [`slo-001-latency.md`](slo-001-latency.md) | `E2ELatencyBreach` | SC-001 diagnostic-event-to-policy-deployed latency p95 breach. |
| [`slo-002-success-rate.md`](slo-002-success-rate.md) | `SustainedIngestSuccessRateBreach` | SC-002 sustained ingest success-rate breach. |
| [`slo-003-soak.md`](slo-003-soak.md) | `SoakErrorRateOrMemoryBreach` | SC-003 soak memory growth or error-rate breach. |
| [`slo-004-query-latency.md`](slo-004-query-latency.md) | `QueryLatencyBreach` | SC-004 query p95 breach. |
| [`slo-005-recovery.md`](slo-005-recovery.md) | `RecoveryFromOutageBreach` | SC-005 recovery-from-outage exceeded. |
| [`slo-006-dashboard-lag.md`](slo-006-dashboard-lag.md) | `DashboardLagBreach` | SC-006 dashboard lag exceeded. |
| [`slo-010-outcome-write-delay.md`](slo-010-outcome-write-delay.md) | `OutcomeWriteDelayBreach` | SC-010 outcome write delay breach. |
| [`slo-012-availability.md`](slo-012-availability.md) | `AvailabilityBreach` | SC-012 availability breach. |

## Per-page contents (mandatory)

Each runbook page MUST contain headings (any heading level): **Symptoms**, **Dashboard**, **Mitigation**, **Escalation**. The CI guard at `scripts/check_runbook_completeness.py` enforces this. **Related ADRs** and **Related FRs** sections are strongly recommended and present on every page below, but not CI-enforced (so a future alert can ship without inventing an ADR cross-reference).

## Entry point

This `INDEX.md` is the entry point reviewers and on-call engineers use. Per-page content authored in Phase 4 (T112).

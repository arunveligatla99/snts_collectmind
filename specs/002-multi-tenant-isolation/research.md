# Research Notes: Multi-Tenant Isolation

**Feature**: `002-multi-tenant-isolation`
**Date**: 2026-05-11
**Status**: Phase 0 — resolves all NEEDS CLARIFICATION items and the three load-bearing decisions called out at /speckit.plan kickoff.

The clarify session of 2026-05-11 resolved the three `[NEEDS CLARIFICATION]` markers from the draft spec (FR-005 hybrid RLS posture; FR-012 2x-SLO rate-limit defaults; FR-013 Postgres `tenant_config` table). This research file resolves the four remaining open questions surfaced by the plan kickoff:

1. Tenant-Vehicle Ownership store: mutability model.
2. Hot-store key migration mechanism.
3. Break-glass bypass surface: service-principal authentication.
4. Break-glass bypass surface: "this is a privileged op" signaling.

Each section follows the standard template:
- **Decision**: what was chosen.
- **Rationale**: why chosen.
- **Alternatives considered**: what else evaluated; why rejected.

A fifth section covers smaller technology-pattern decisions that feed into the implementation (token-bucket algorithm + storage; tenant_config reload mechanism; failure-open vs failure-closed posture; metric label conventions). These are not load-bearing on their own but are required to land the plan without ambiguity.

---

## 1. Tenant-Vehicle Ownership store: mutability model

**Decision**: **Mutable current row with an append-only history table.** `tenant_vehicles` carries exactly one row per `vehicle_id` recording the current owning tenant. Every change to `tenant_vehicles` (`INSERT` / `UPDATE` of `tenant_id`) fires a trigger that appends a row to `tenant_vehicles_history` recording the prior owner, the new owner, the operator subject that authorized the transfer, a reason code, and the transition timestamp. Both tables are RLS-protected: `tenant_vehicles` allows tenant-scoped `SELECT` for the row's current owner only and denies all mutations from non-service principals; `tenant_vehicles_history` allows tenant-scoped `SELECT` only for rows where the requesting tenant is either the prior or new owner (so a tenant can see when they acquired a vehicle and when they divested one, but cannot read transfers between two other tenants).

**Rationale**:

- **Operational reality is mutable**. Vehicle ownership changes are not an edge case in fleet platforms: fleet sales, OEM-to-dealer-to-customer handoffs, used-vehicle resale, leasing-company-to-fleet transfers, end-of-lease returns, accident-induced totaling, and inter-fleet swaps all happen routinely. An immutable model would require minting a new `vehicle_id` on every ownership change, which (a) breaks VIN-as-identifier semantics (the VIN is durable for the life of the vehicle), (b) breaks the join from telemetry (a vehicle's telemetry history would split across multiple synthetic IDs), and (c) breaks audit lineage on the policies that targeted the vehicle under its prior identity.
- **Audit cleanliness is preserved by the history table**, not by immutability of the current row. Principle XVII's "audit is a feature, not a log" requires the lineage to be **queryable**, not necessarily immutable in the current-state row. The history table provides full queryability: `SELECT * FROM tenant_vehicles_history WHERE vehicle_id = $1 ORDER BY transition_at` returns the complete chain of custody. Every row in `tenant_vehicles_history` is immutable (no `UPDATE`/`DELETE` allowed by trigger), so the audit property holds at the history layer where it matters.
- **Erasure compatibility**. The right-to-erasure dispatcher (feature 001 FR-020a) can redact a tenant's PII from `tenant_vehicles_history` rows where the tenant was the prior owner (e.g., the tenant subject column becomes `<redacted>`) while preserving the historical fact that a transfer occurred. The history table thus survives erasure with referential integrity intact, the same way `audit_events` does today.
- **Deployer hot-path performance is identical for either model**. The deployer reads exactly one row from `tenant_vehicles` per deployment (the current owner). Mutability or immutability of the *history* table is invisible to the deployer hot path. The mutable-current-row design wins on this axis trivially.
- **Triggers, not application code, enforce the history-write invariant.** A `BEFORE INSERT OR UPDATE OF tenant_id` trigger on `tenant_vehicles` inserts the history row in the same transaction. There is no code path in `src/collectmind/` that can write to `tenant_vehicles` without producing the history row; the invariant is at the DB layer.

**Alternatives considered**:

- **Strictly immutable assignments** (a vehicle is forever tied to its initial tenant; transfers require a new `vehicle_id`). Rejected: breaks VIN semantics, breaks telemetry-history continuity, and forces every consuming system (registry, deployer, query-api) to learn a "this VIN was previously known as that VIN" indirection. The audit property the immutable model offers (every assignment is a permanent record) is achievable via the history table without paying these costs.
- **Mutable current row WITHOUT history table** (overwrite-in-place). Rejected: violates Principle XVII queryability. A tenant would have no audit-trail visibility into when they acquired or divested a vehicle.
- **Event-sourced ownership** (the current owner is a fold over the event log; no current-state table). Rejected: forces every deployer call to read N rows where N is the number of historical transfers; turns a single-read hot path into a scan. The current-state row + history-table shape is the materialized projection of the event-sourced model and is faster for the hot path while preserving the audit property.

**Implementation surface** (recorded in [`data-model.md`](./data-model.md) §Tenant-Vehicles; ADR-0009):
- `tenant_vehicles`: `vehicle_id TEXT PRIMARY KEY`, `tenant_id TEXT NOT NULL`, `assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `assigned_by_subject TEXT NOT NULL`. RESTRICTIVE RLS keyed by `tenant_id = current_setting('app.tenant_id', true)`; service-principal-only writes.
- `tenant_vehicles_history`: `history_id BIGSERIAL PRIMARY KEY`, `vehicle_id TEXT NOT NULL`, `prev_tenant_id TEXT`, `new_tenant_id TEXT NOT NULL`, `operator_subject TEXT NOT NULL`, `reason_code TEXT NOT NULL`, `transition_at TIMESTAMPTZ NOT NULL DEFAULT now()`. RESTRICTIVE RLS keyed by `prev_tenant_id = current_setting('app.tenant_id', true) OR new_tenant_id = current_setting('app.tenant_id', true)`.
- New audit row kind `vehicle_assignment_change` written in the same transaction as the `tenant_vehicles` `INSERT`/`UPDATE` (third atomic-audit pattern, after `break_glass` and `tenant_config_change`).

---

## 2. Hot-store key migration mechanism

**Decision**: **Option C — TTL-driven natural rollover.** At deploy cutover, every writer immediately switches to the new tenant-scoped key shape `tenant_id:vehicle_id:signal_name`. Every reader checks the new key first; on cache miss the reader falls back to the legacy key `vehicle_id:signal_name` for the duration of the existing 24-hour TTL. Legacy keys expire naturally; after the TTL window the fallback-read path is removed in a follow-up commit gated on a deployment health check.

**Rationale**:

- **Feature-001 SC-002 sustained ingest is 1000 events/s/tenant**. The hot store is dominated by writes (telemetry ingest writes per second match SC-002; reads happen at feedback-worker window-close events, which are episodic at single-digits-per-tenant-per-window cadence). Doubling writes (option B, dual-write) costs RAM + Redis CPU proportional to the sustained write rate; doubling reads (option C) costs only at episodic read events. The asymmetric load shape makes (C) clearly cheaper than (B).
- **One-shot Lua/scripted migration (option A) is catastrophic under sustained load**. The Redis SCAN cursor + per-key RENAME walk takes O(N) time and holds the keyspace under contention during the walk. Under SC-002's sustained 1000 events/s/tenant, the cache hits ~10⁵ keys per tenant in the warm working set; walking ~10⁵–10⁶ keys per migration run while the system is ingesting at full rate would impose latency spikes well beyond the SC-006 10ms p95 ceiling. Rejected.
- **The 24-hour TTL is already short relative to the rollout window**. Production rollouts deploy across regions over hours-to-days; the fallback-read window of 24 hours starting at deploy cutover is naturally covered by the rollout itself. Within the 24-hour window, every reader incurs at most one extra `GET` on a cache miss. After 24 hours, every legacy key has expired and the fallback path is provably unreachable.
- **Operational simplicity**. Option C has zero "migration code" in the operational sense — no script to schedule, no progress to monitor, no failure mode where the script crashes mid-walk and leaves a half-migrated keyspace. The only operational signal is: "after 24 hours from cutover, run a SCAN to assert no legacy-shape keys remain." That assertion is a one-time check, not a recurring obligation.
- **Failure-safe across cache restart**. Redis is a cache, so a restart at any point during the rollover loses transient state but does not break correctness. Both legacy and new-shape readers degrade to a cold-cache rehydrate from Postgres (which is the existing feature-001 behavior); no special-case handling required.

**Alternatives considered**:

- **Option A (one-shot scripted migration)**. Rejected per the SC-002 contention argument above. Even with `SCAN COUNT 100` chunking and rate-limiting the walk, the per-key `RENAME` operation under a high-traffic key invites the kind of latency tail that SC-006 forbids.
- **Option B (dual-write window)**. Rejected per the write-amplification argument above. Doubling write rate for a 24-hour window pushes Redis CPU + memory closer to capacity precisely when the system is mid-rollout and least tolerant of resource exhaustion. The operational cost of option B is also higher: writers need a feature-flag-style "dual-write mode" that adds a code path and a corresponding cleanup commit.
- **Eager full flush (drop the cache, let it rehydrate from Postgres)**. Considered as a fourth option. Rejected: defeats the purpose of the cache; Postgres would absorb the rehydration storm, costing more than the steady-state Redis load.

**Implementation surface** (recorded in ADR-0008 §Hot-store migration; reflected in `src/collectmind/cache/hot_store.py`):
- Writers: switch the key shape unconditionally at deploy time. No feature flag, no dual-write code path.
- Readers: `get(tenant_id, vehicle_id, signal_name)` reads the new-shape key first; on miss, reads the legacy key as fallback; returns the first hit. After the 24-hour rollover window, the fallback branch is removed (follow-up commit).
- SC-009 (≤ 60 s migration window against 10,000 keys) is satisfied trivially: there is no migration step; the rollover happens at deploy cutover with zero wall-clock cost.
- Test: `tests/integration/test_hot_store_key_rollover.py` asserts (i) writes after cutover land under the new shape; (ii) reads find new-shape values; (iii) reads fall back to legacy-shape values during the rollover window; (iv) reads return cache-miss after 24-hour TTL expires regardless of whether the legacy key existed.

---

## 3. Break-glass bypass primitive: service-principal authentication

**Decision**: **Option (i) — separate JWT issuer scoped to operator-principals**, distinct from the tenant JWT issuer. The operator-issuer signs JWTs whose `aud` claim is `collectmind-operator` (the tenant issuer signs JWTs whose `aud` is `collectmind-tenant`). The audience claim is verified by the same `PyJWT` + JWKS pipeline that already verifies tenant JWTs (feature 001's `src/collectmind/auth/jwt_verifier.py`), parameterized by which issuer's JWKS endpoint is consulted. The operator-issuer's JWKS endpoint is mounted into the Compose stack for local dev (a static signer container under a new Compose profile `operator-issuer`); in cloud the JWKS endpoint sits behind an internal-only ALB with IAM-scoped access.

**Rationale**:

- **Reuses existing authentication primitives**. The PyJWT + JWKS pipeline, the `Principal` extractor, the FastAPI `Depends()` wiring — all reused. No new auth machinery. The only new code is a parameterized `JWTVerifier(issuer_url, audience)` and a second instance bound to the operator-issuer. Cognitive load and audit surface stay small.
- **Local-dev story is intact**. The foundation smoke must exercise the bypass primitive without AWS in scope (per the plan kickoff requirement). The Compose profile `operator-issuer` provisions a static-signer Docker container with a local keypair; the orchestration-api reads its JWKS from `http://operator-issuer:8080/.well-known/jwks.json`. The same shape ships to cloud where the JWKS endpoint is an internal-only ALB.
- **Security blast radius is bounded by audience-claim enforcement**. A tenant JWT presented at the operator-only endpoint fails audience validation and returns 401 before the handler is reached. An operator JWT presented at a tenant endpoint fails the same way. The verification is a one-line `aud` claim check; the audit log records the failure with the offered audience so misuse is observable.
- **Key separation is real**. The operator-issuer's signing key never appears in the tenant-issuer's keystore. Compromise of either issuer is contained: tenant-key compromise allows forgery of tenant JWTs only (the existing risk surface, unchanged by this feature); operator-key compromise allows forgery of operator JWTs only (a new risk, but well-bounded — break-glass invocations are atomically audited per FR-005b, so a forged operator JWT would still leave a queryable trail).

**Alternatives considered**:

- **Option (ii) — AWS IAM role + SigV4 on an internal-only API endpoint**. Strong in cloud (IAM is the canonical AWS authorization primitive), but breaks the local-dev story: the foundation smoke would need LocalStack or `aws-sdk` stubs to exercise the bypass, adding dependency surface and complexity. Also asymmetric with the rest of the application (all other authenticated endpoints use JWT); the discontinuity invites operator confusion about which boundary applies where. Rejected for local-dev incompatibility and architectural asymmetry.
- **Option (iii) — mTLS with a separate certificate authority**. Strong in principle (mutual authentication at the transport layer), but operationally heavy: cert issuance + rotation tooling per operator-principal, separate Docker setup for client-cert injection, no support story for browser-based operators (a future operator-UI would need a separate authentication path). Rejected for operational cost and the lack of a clear win over JWT for this use case.

**Implementation surface** (recorded in ADR-0007 §Decision; reflected in `src/collectmind/auth/operator_principal.py`):
- `JWTVerifier` made parameterized over issuer URL + audience.
- New verifier instance configured from `OPERATOR_ISSUER_URL`, `OPERATOR_ISSUER_AUDIENCE` env vars.
- New FastAPI dependency `authenticated_operator_principal` extracts the operator subject + claims, refuses any JWT whose audience is not `collectmind-operator`.
- Compose profile `operator-issuer` ships a tiny static-signer image (Python + `python-jose` + a static keypair mounted from `infra/compose/operator-issuer/`) on port 8080 serving `/.well-known/jwks.json`.

---

## 4. Break-glass bypass primitive: "this is a privileged op" signaling

**Decision**: **Option (i) — separate API endpoint** `POST /api/v1/audit/break-glass/query` mounted on a distinct FastAPI router (`src/collectmind/audit_admin/api.py`) that does not share any code path with the regular audit-query endpoint at `GET /api/v1/audit/{cid}`. The break-glass endpoint's dependency chain is `authenticated_operator_principal` (option-3 above); the regular endpoint's dependency chain remains `authenticated_principal`. The two handlers cannot collapse onto a shared function: they have different request shapes, different response shapes, different DB-access primitives (the break-glass handler bypasses RLS via a service-principal connection; the regular handler runs under the requesting tenant's RLS context), and different audit-row writers.

**Rationale**:

- **Failure mode is build-time-impossible, not runtime-guarded**. A header-flipping option (`X-Break-Glass-Reason`) or a query-parameter option (`?break_glass=true&reason=...`) would put the bypass and the regular path on the same handler function with a runtime branch; a typo, a misordered conditional, or a future refactor could route a regular query through the bypass path. By segregating into different routers, different handler functions, and different DB primitives, the failure mode collapses to "did this PR add the right router import?" — a question answered at code-review time, not at runtime.
- **OpenAPI surface segregation is testable**. The break-glass endpoint lives in `contracts/openapi/audit-admin.v1.yaml` — a separate document from the regular query API. The two contracts are exercised by two different schemathesis test files. A PR that accidentally exposes the bypass on the regular query API would fail the regular query API's contract test on the response-shape mismatch. The contract is the guard.
- **Authentication boundary is explicit**. The break-glass router's `app.include_router(audit_admin_router, dependencies=[Depends(authenticated_operator_principal)])` declares the operator-JWT requirement at the router level; FastAPI prevents the router from being reached without the operator audience claim. The regular router's `Depends(authenticated_principal)` declares the tenant-JWT requirement. The two dependency chains have no overlap.
- **Operational visibility**. The break-glass endpoint emits the `collectmind_break_glass_total{operator_subject,reason}` metric on every invocation; the regular audit-query endpoint never increments that counter. Dashboards and alerts at the metric layer have a clean signal of break-glass volume vs regular-query volume, which would be impossible if both handlers shared the same code path.

**Alternatives considered**:

- **Option (ii) — header (`X-Break-Glass-Reason: <code>`) on the regular endpoint**. Rejected per the build-time-impossibility argument above. The same code path with a runtime branch is exactly the failure mode FR-005c's scope-boundary clause is meant to prevent.
- **Option (iii) — explicit query parameter (`?break_glass=true&reason=<code>`)**. Rejected for the same reason. Additionally, a query parameter is the easiest of the three to inject accidentally via templated URLs or copy-paste.
- **A separate microservice for the break-glass surface**. Considered as a fourth option (extreme segregation: a different OS process listening on a different port). Rejected as over-engineering for feature 002. The router-level segregation gives the build-time guarantee without paying for cross-process communication, separate deployment, separate observability surface. If the operator-facing UI in a future feature warrants a separate service, that's a future ADR; for the primitive in this feature, the router-level boundary is enough.

**Implementation surface** (recorded in ADR-0007 §Surface; reflected in `src/collectmind/audit_admin/api.py`):
- `POST /api/v1/audit/break-glass/query` — request body carries `tenant_scope`, `correlation_id`, `reason_code` (enum from a documented list); response body carries the matching `audit_events` rows for the named tenant scope.
- Handler chain: `authenticated_operator_principal` → bypass DB connection (service-principal credentials, no `SET LOCAL app.tenant_id`) → SELECT from `audit_events WHERE tenant_id = $tenant_scope AND correlation_id = $cid` → write `kind=break_glass` audit row in the same transaction as the SELECT (FR-005b) → return rows to the caller.
- Transaction boundary: the audit-row write commits before the response body returns to the network. If the audit-row write fails the transaction aborts and the SELECT result is discarded (the caller sees a 500; the audit log records the abort attempt).

---

## 5. Smaller technology-pattern decisions

### 5a. Token-bucket algorithm + storage

**Decision**: Redis-backed counter with a single Lua script that performs check-and-deduct atomically. Each `(tenant_id, endpoint)` pair gets a key `ratelimit:{tenant_id}:{endpoint}` storing `{tokens, last_refill_at}`. The Lua script reads, refills based on elapsed time × rate, deducts one token, writes back, returns the decision (allow/reject) + remaining tokens. One Redis round trip per request. Bucket parameters (rate, burst) read from the `tenant_config` cache; defaults from FR-012.

**Rationale**: standard pattern, well-understood, atomic without external locking. Lua avoids race conditions between concurrent requests for the same tenant. Postgres-backed counters were considered and rejected (write amplification on every request would overwhelm Postgres at SC-002 rates).

### 5b. tenant_config cache reload mechanism

**Decision**: in-process LRU cache (size: 1024 tenant rows) with a 5-second TTL. A background asyncio task subscribes to Postgres `LISTEN tenant_config_changed`; the migration includes a trigger that emits `NOTIFY tenant_config_changed, '<tenant_id>'` after every `INSERT`/`UPDATE`/`DELETE` on `tenant_config`. On NOTIFY the cache invalidates the named tenant's entry. The 5-second TTL is the worst-case staleness even if NOTIFY is lost.

**Rationale**: NOTIFY-driven invalidation gives sub-second responsiveness for config changes (operator changes a tenant's override, the next request from that tenant uses the new limit). The TTL is the safety net for NOTIFY-pipeline failures (asyncpg reconnect, Postgres-side `pg_listen` backlog overflow). The combination is the standard "push + pull fallback" pattern.

### 5c. Failure-open vs failure-closed posture for rate limiting

**Decision**: **failure-closed**. If the Redis Lua script fails or times out (1-second hard deadline), the middleware responds with `503 Service Unavailable` carrying a `Retry-After: 1` header, *not* an allow. Counter on `collectmind_ratelimit_redis_unavailable_total{endpoint}` increments; alert fires on sustained Redis unavailability.

**Rationale**: rate limiting is a security primitive that defends shared infrastructure from one tenant abusing capacity. Failing open under Redis outage would let a noisy tenant escape detection at exactly the moment the operator most needs the gate to hold. Postgres + the rest of the pipeline would absorb the noisy tenant's full request rate during the Redis outage, which violates US2's "single noisy tenant cannot degrade other tenants" property. A 503 is loud and visible; a silent-allow is invisible.

### 5d. Metric label conventions

**Decision**: every new metric carries the `tenant_id` label *only* when (a) the tenant identifier is derived from a verified JWT, AND (b) emitting the label cannot widen a side-channel for cross-tenant existence checks. The `collectmind_cross_tenant_access_attempt_total{endpoint}` metric explicitly does NOT carry the targeted tenant identifier (only the requesting tenant + the endpoint), to honor FR-009's "MUST never include a different tenant's identifier in any metric label value." The break-glass metric carries `operator_subject` (the operator principal) but not the tenant scope queried (the scope is in the audit row; the metric is for volume only).

**Rationale**: metric labels are a visible side channel; PII and tenant-identifier discipline at the label layer must match the discipline at the log layer. Cardinality discipline is a secondary concern (high-cardinality `tenant_id` labels are OK if Prometheus is sized for it; the orchestration-api's `/metrics` endpoint serves ~10⁴ tenants × ~10 endpoints = 10⁵ series, well inside a single Prometheus instance's capacity).

---

## Summary

All four open questions are resolved. The three new ADRs that ship alongside this plan record the load-bearing decisions:

- **ADR-0007** records §3 + §4 (break-glass authentication + signaling) and §1's RLS hardening (PERMISSIVE → RESTRICTIVE forward; RESTRICTIVE → PERMISSIVE backward) + the connection-pool transaction-boundary contract for re-establishing the GUC on every transaction.
- **ADR-0008** records §2 (hot-store migration mechanism) + §5a–§5d (token-bucket, tenant_config cache, failure-closed posture, metric labels).
- **ADR-0009** records §1 (tenant-vehicle ownership store: mutable current row + append-only history) and its data-model + RLS surface.

No remaining NEEDS CLARIFICATION items.

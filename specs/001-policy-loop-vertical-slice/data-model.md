# Data Model: Policy-Loop Vertical Slice

**Branch**: `001-policy-loop-vertical-slice` | **Date**: 2026-05-09

This document captures the entities the system persists, their fields, validation rules, relationships, and state transitions. The model is single-tenant in feature 001 with the multi-tenant key shape preserved (per Spec Clarifications Q1). Storage is PostgreSQL 16 with the TimescaleDB extension; Redis carries hot-path data only and is not modeled here as a system of record.

## Conventions

- Identifiers use ULIDs unless otherwise stated. ULIDs are k-sortable and safe for indexing.
- All timestamps are stored in UTC at microsecond precision (`TIMESTAMPTZ`).
- All monetary, latency, and threshold values are stored in their canonical SI units (no per-row overrides).
- Tenant scoping is composite-key at the table level even though feature 001 has a single tenant.
- Immutable tables are enforced by absence of `UPDATE` privileges on the application role and by triggers that reject `UPDATE` and `DELETE` outside the erasure path.

## Entities

### `tenants`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `tenant_id` | `TEXT` | PK, non-empty | OAuth2 client subject. |
| `display_name` | `TEXT` | non-empty | For dashboards only. |
| `oauth2_issuer` | `TEXT` | URL, non-empty | Authoritative issuer for this tenant's tokens. |
| `oauth2_audience` | `TEXT` | non-empty | Required `aud` claim value. |
| `created_at` | `TIMESTAMPTZ` | default `now()` | |
| `status` | `TEXT` | enum `active|suspended` | Suspension blocks ingest. |

In feature 001 a single row is seeded with `tenant_id = 'feature-001-default'`.

### `diagnostic_findings`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id`, non-empty | From validated JWT claim. |
| `finding_id` | `TEXT` | non-empty | Supplied by upstream source. |
| `schema_version` | `TEXT` | semver-like, non-empty | Inbound event's declared schema version. Major must be the supported major. |
| `anomaly_type` | `TEXT` | non-empty | Enumeration; in feature 001 only `brake_wear_early_stage` is accepted. |
| `hypothesis_class` | `TEXT` | non-empty | One of the supported classes. |
| `hypothesis_statement` | `TEXT` | non-empty, ≤ 4096 chars | Plain-language hypothesis being tested. |
| `candidate_signals` | `JSONB` | array of VSS signal names, non-empty | Validated against `config/vss/v6.0/signals.yaml`. |
| `vehicle_scope` | `JSONB` | array of vehicle IDs, non-empty | |
| `upstream_confidence` | `NUMERIC(4,3)` | range `[0.000, 1.000]` | From upstream source. |
| `received_at` | `TIMESTAMPTZ` | default `now()` | Server-assigned. |
| `received_payload_sha256` | `BYTEA` | length 32 | For idempotency tie-breaks. |

**Primary key**: `(tenant_id, finding_id)`. Idempotent on this composite key per FR-012.

**Indexes**: `(tenant_id, received_at DESC)` for the operator query interface; `(hypothesis_class, anomaly_type)` for filtered lookups.

### `vehicle_groups`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `group_id` | `TEXT` | non-empty | |
| `vehicle_ids` | `JSONB` | array of vehicle IDs, non-empty | |
| `created_at` | `TIMESTAMPTZ` | default `now()` | |

**Primary key**: `(tenant_id, group_id)`.

### `collection_policies`

Immutable. Each row is a specific policy version.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `policy_id` | `TEXT` | non-empty | Identifier of the policy across versions. |
| `version` | `TEXT` | semver, non-empty | Increments on regeneration of the same logical policy. |
| `signal_spec` | `JSONB` | non-empty, schema-validated | Each entry: `{ vss_name, sample_rate_hz, priority }`. All `vss_name` values pass VSS v6.0 validation. |
| `trigger_conditions` | `JSONB` | array, schema-validated | Each entry: `{ kind, params }` where kind ∈ `{threshold, time_window, geofence, scheduled}`. |
| `collection_window_hours_logical` | `INTEGER` | `> 0` and `≤ 168` | Per FR-009a. |
| `vehicle_scope` | `JSONB` | array of vehicle IDs, non-empty | |
| `hypothesis_statement` | `TEXT` | non-empty | Carried from the originating finding. |
| `data_governance_flags` | `JSONB` | object | At minimum `{ pii_consent: bool, has_pii_signal: bool }`. |
| `confidence_threshold` | `NUMERIC(4,3)` | range `[0.000, 1.000]` | |
| `generated_from_session_id` | `TEXT` | non-empty | `PolicyGenerationSession` ID for lineage. |
| `originating_finding` | `JSONB` | `{ tenant_id, finding_id }` composite reference | Lineage to the inbound finding. |
| `prompt_template_version` | `TEXT` | semver, non-empty | Active prompt version when generated. |
| `slm_repo` | `TEXT` | non-empty | E.g. `Qwen/Qwen2.5-7B-Instruct`. |
| `slm_revision_sha` | `TEXT` | length 40, non-empty | Hugging Face revision SHA. |
| `slm_runtime` | `TEXT` | enum `vllm|llama_cpp|stub` | Records which client produced the policy. |
| `slm_runtime_version` | `TEXT` | non-empty | E.g. `v0.20.1` or `b9090`. |
| `slm_quantization` | `TEXT` | enum `bf16|gguf-q4_k_m|none` | |
| `slm_decoding_seed` | `BIGINT` | | |
| `payload_signature` | `BYTEA` | non-empty | Detached signature over the canonical payload (R-018). |
| `signature_key_id` | `TEXT` | non-empty | KMS key ID or local-key fingerprint. |
| `created_at` | `TIMESTAMPTZ` | default `now()` | |

**Primary key**: `(tenant_id, policy_id, version)`. Immutable: triggers reject `UPDATE`. `DELETE` allowed only via the erasure dispatcher.

**Indexes**: `(tenant_id, policy_id, created_at DESC)`; GIN on `signal_spec` and `trigger_conditions` for query operators.

### `deployment_targets`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `deployment_id` | `TEXT` | PK, ULID | |
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `policy_id` | `TEXT` | FK with `version` → `collection_policies` | |
| `version` | `TEXT` | as above | |
| `environment` | `TEXT` | enum `dev|staging|prod` | |
| `vehicle_scope` | `JSONB` | array of vehicle IDs | Snapshot at deployment time. |
| `status` | `TEXT` | enum `requested|accepted|rejected|expired` | |
| `downstream_response` | `JSONB` | nullable | From the simulator (or, later, real Collector AI). |
| `requested_at` | `TIMESTAMPTZ` | default `now()` | |
| `accepted_at` | `TIMESTAMPTZ` | nullable | |
| `expires_at` | `TIMESTAMPTZ` | non-null after `accepted_at` is set | Logical-time expiry. |

**Indexes**: `(tenant_id, policy_id, version)`, `(status, expires_at)` for the feedback-loop scheduler.

### `policy_outcomes`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `outcome_id` | `TEXT` | PK, ULID | |
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `originating_finding` | `JSONB` | `{ tenant_id, finding_id }` | Lineage. |
| `policy_id` | `TEXT` | FK with `version` → `collection_policies` | |
| `version` | `TEXT` | as above | |
| `hypothesis_state` | `TEXT` | enum `confirmed|ruled_out|no_data` | Per FR-009. |
| `evaluated_at` | `TIMESTAMPTZ` | default `now()` | |
| `evidence_summary` | `JSONB` | object | Per-signal summary that drove the verdict; sized to keep PII-strip rule trivial. |
| `signals_collected_count` | `INTEGER` | `≥ 0` | |
| `data_quality_score` | `NUMERIC(4,3)` | range `[0.000, 1.000]` | |

**Indexes**: `(tenant_id, originating_finding)`, `(tenant_id, hypothesis_state, evaluated_at DESC)`.

### `audit_events`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `event_id` | `TEXT` | PK, ULID | |
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `kind` | `TEXT` | enum `accepted|rejected|generated|validated|deployed|outcome|erasure` | |
| `originating_finding` | `JSONB` | `{ tenant_id, finding_id }` | Always present when applicable. |
| `policy_ref` | `JSONB` | `{ tenant_id, policy_id, version }` nullable | |
| `deployment_ref` | `JSONB` | `{ deployment_id }` nullable | |
| `outcome_ref` | `JSONB` | `{ outcome_id }` nullable | |
| `slm_repo` | `TEXT` | nullable | Filled for `generated` events. |
| `slm_revision_sha` | `TEXT` | nullable | |
| `slm_runtime` | `TEXT` | nullable | |
| `slm_runtime_version` | `TEXT` | nullable | |
| `slm_quantization` | `TEXT` | nullable | |
| `slm_decoding_seed` | `BIGINT` | nullable | |
| `prompt_template_version` | `TEXT` | nullable | |
| `inbound_schema_version` | `TEXT` | nullable | Per FR-013. |
| `time_acceleration_factor` | `NUMERIC(10,3)` | nullable | Per FR-009a; recorded so audit consumers can distinguish CI from production. |
| `principal_subject` | `TEXT` | non-empty | JWT `sub` claim. |
| `correlation_id` | `TEXT` | non-empty | Same identifier surfaced in dashboard and structured logs. |
| `occurred_at` | `TIMESTAMPTZ` | default `now()` | |

Immutable: triggers reject `UPDATE` and `DELETE`. Erasure path writes a redaction event rather than deleting.

**Indexes**: `(tenant_id, originating_finding)`, `(tenant_id, kind, occurred_at DESC)`, `(correlation_id)`.

### `telemetry_observations` (TimescaleDB hypertable)

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `tenant_id` | `TEXT` | non-empty | |
| `vehicle_id` | `TEXT` | non-empty | |
| `signal_name` | `TEXT` | non-empty, VSS-validated | |
| `value` | `DOUBLE PRECISION` | | |
| `observed_at` | `TIMESTAMPTZ` | non-null | Hypertable partition column. |
| `policy_ref` | `JSONB` | `{ tenant_id, policy_id, version }` nullable | |
| `source` | `TEXT` | enum `simulator|real` | In feature 001 always `simulator`. |

**Hypertable**: `observed_at`, chunked daily. Retention policy: drop chunks older than 90 days (configurable per tenant in feature 002).

**Indexes**: `(tenant_id, vehicle_id, observed_at DESC)`, `(tenant_id, signal_name, observed_at DESC)`.

### `erasure_requests`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `request_id` | `TEXT` | PK, ULID | |
| `tenant_id` | `TEXT` | FK → `tenants.tenant_id` | |
| `subject_kind` | `TEXT` | enum `vehicle|finding|principal` | |
| `subject_identifier` | `TEXT` | non-empty | The vehicle ID, finding ID, or principal subject to erase. |
| `requested_by` | `TEXT` | non-empty | JWT `sub` of requester. |
| `requested_at` | `TIMESTAMPTZ` | default `now()` | |
| `target_completion_at` | `TIMESTAMPTZ` | non-null | `requested_at + 30 days` by default. |
| `status` | `TEXT` | enum `requested|in_progress|completed|partial` | |
| `per_store_status` | `JSONB` | `{ registry: ..., telemetry: ..., audit: ... }` | Each store reports its own outcome. |
| `mode` | `TEXT` | enum `erased|redacted` | Per R-017 distinction. |
| `completed_at` | `TIMESTAMPTZ` | nullable | |

## Relationships

```text
tenants 1 ── ∞ diagnostic_findings
         1 ── ∞ vehicle_groups
         1 ── ∞ collection_policies (by tenant_id, policy_id, version)
                                 │
                                 ▼
                        deployment_targets ── ∞ ─▶ vehicle_scope (snapshot)
                                 │
                                 ▼
                        policy_outcomes ── 1 ── 1 originating diagnostic_findings

audit_events references findings, policies, deployments, outcomes (all nullable)
telemetry_observations references collection_policies (nullable; rows produced by the simulator)
erasure_requests references tenants and any subject across the model
```

## Validation rules

1. Every `signal_name` in `diagnostic_findings.candidate_signals`, `collection_policies.signal_spec`, and `telemetry_observations.signal_name` MUST be present in the loaded VSS v6.0 vocabulary at write time. Validation failures route to the dead-letter queue (per FR-006).
2. `collection_window_hours_logical` MUST satisfy `0 < value ≤ 168` (per FR-009a).
3. `data_governance_flags.has_pii_signal == true` requires `data_governance_flags.pii_consent == true`. Otherwise the policy is rejected at validator time.
4. `schema_version` MUST be present on every inbound finding. The major component MUST equal the supported major; minor and patch additive fields are tolerated and ignored (per FR-003a).
5. The deployer rejects any policy whose `payload_signature` does not verify against `signature_key_id` (per R-018).
6. The Policy Generator's `slm_quantization` and `slm_runtime` fields MUST agree: `bf16` requires `vllm`; `gguf-q4_k_m` requires `llama_cpp`; `none` is reserved for the deterministic stub (`stub`).
7. Audit events for `kind == 'generated'` MUST populate every `slm_*` field, the `prompt_template_version`, and the `slm_decoding_seed` (per FR-017a).

## State transitions

### Diagnostic finding lifecycle

```text
Received ──auth ok──▶ Accepted ──schema ok──▶ Enqueued ──graph runs──▶ {Generated → Validated → Deployed} or Rejected
Rejected paths emit an audit_event with kind='rejected' and a structured error code.
```

### Policy version lifecycle

```text
Pending Generation ──generated──▶ Generated
Generated ──validator passes──▶ Validated
Generated ──validator fails──▶ Generated' (retry from generator with errors injected, bounded retry budget)
Validated ──deployer accepts──▶ Deployed (deployment_targets row written)
Deployed ──window opens──▶ Active
Active ──window closes──▶ Closed (feedback worker writes policy_outcomes row)
Any state ──validator-budget exhaustion or deployer permanent failure──▶ Dead-Lettered (audit_event records cause)
```

### Outcome lifecycle

```text
Pending ──feedback evaluation──▶ Confirmed | Ruled Out | No Data
```

### Erasure lifecycle

```text
Requested ──dispatcher picks up──▶ In Progress
In Progress ──per-store callbacks──▶ Completed | Partial
Partial ──ops review──▶ Completed (manual close after remediation) or escalated
```

## Multi-tenant evolution note

Feature 002 will tighten Postgres row-level security from permissive to restrictive and prefix Redis keys with the tenant. No table schema changes are required; the composite-key shape used here is the same in feature 002. This is the primary reason feature 001 carries `tenant_id` everywhere despite being single-tenant.

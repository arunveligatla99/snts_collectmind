# Quickstart: Multi-Tenant Isolation Foundation Smoke

**Feature**: `002-multi-tenant-isolation`
**Date**: 2026-05-11
**Companion to**: [`specs/001-policy-loop-vertical-slice/quickstart.md`](../001-policy-loop-vertical-slice/quickstart.md)

This quickstart extends the feature-001 foundation smoke with the multi-tenant isolation surface introduced by feature 002. It is runnable on a clean clone in under 10 minutes on the warm Compose stack (SC-008 budget retained). Run it after the feature-001 smoke is green; the steps below assume the stack is up and the feature-001 happy path passes.

## Prerequisites

Same as feature 001 (Docker Desktop or a working Docker daemon; Python 3.11.9 in a venv; `make` available). Additionally:

- The `operator-issuer` Compose profile must be brought up alongside the default profile: `docker compose --profile operator-issuer -f infra/compose/docker-compose.yaml up -d`. This boots a small static-signer container on `http://operator-issuer:8080` whose JWKS endpoint is consumed by the orchestration-api's operator-principal verifier.
- Two tenant JWTs are needed. Generate them with the documented helper at `scripts/dev_issue_jwt.py`:
  ```
  python scripts/dev_issue_jwt.py --tenant tenant-a > /tmp/tenant-a.jwt
  python scripts/dev_issue_jwt.py --tenant tenant-b > /tmp/tenant-b.jwt
  python scripts/dev_issue_jwt.py --operator alice --audience collectmind-operator > /tmp/op-alice.jwt
  ```
  The script signs with the local issuer keys; not for production use.

## Step 1 — Provision the two tenants and assign a vehicle each

```
# Service-principal write: enroll tenants A and B in the `tenants` directory.
psql "$POSTGRES_URL" -c "INSERT INTO tenants(tenant_id, created_at) VALUES ('tenant-a', now()), ('tenant-b', now());"

# Service-principal write: assign one vehicle to each tenant.
psql "$POSTGRES_URL" -c "
  INSERT INTO tenant_vehicles(vehicle_id, tenant_id, assigned_at, assigned_by_subject, reason_code)
  VALUES ('VIN-AAAA-0001', 'tenant-a', now(), 'service-principal://quickstart', 'initial_provisioning'),
         ('VIN-BBBB-0001', 'tenant-b', now(), 'service-principal://quickstart', 'initial_provisioning');
"
```

**Expect**: Two rows in `tenant_vehicles`. Two rows in `tenant_vehicles_history` (one per initial provisioning, written by the `tenant_vehicles_history_trigger`). Two `kind=vehicle_assignment_change` rows in `audit_events` (one per insert, written by the `tenant_vehicles_audit_trigger`).

## Step 2 — Publish a finding under tenant A and run the feature-001 loop

```
curl -fsS -X POST http://localhost:8081/api/v1/findings \
  -H "Authorization: Bearer $(cat /tmp/tenant-a.jwt)" \
  -H "Content-Type: application/json" \
  --data @specs/001-policy-loop-vertical-slice/fixtures/finding-brake-wear-tenant-a.json
```

**Expect**: 202 Accepted. Per the existing feature-001 flow, the finding produces a policy (generated → validated → deployed) and an outcome after the simulated collection window closes.

## Step 3 — Verify cross-tenant access returns 404 (FR-006, SC-001)

```
# Pull the policy_id from tenant-a's audit chain.
POLICY_ID=$(curl -fsS http://localhost:8081/api/v1/audit/<correlation_id> \
  -H "Authorization: Bearer $(cat /tmp/tenant-a.jwt)" \
  | jq -r '.events[] | select(.kind=="generated") | .extras.policy_ref.policy_id')

# Tenant B attempts to read tenant A's policy — must return 404 (not 403, not 401).
curl -isS http://localhost:8081/api/v1/policies/$POLICY_ID \
  -H "Authorization: Bearer $(cat /tmp/tenant-b.jwt)" \
  | head -n 1
# Expect: HTTP/1.1 404 Not Found
```

**Expect**: 404 Not Found. The response body MUST NOT include tenant A's identifier, the policy's content, or any other side-channel leak. The `collectmind_cross_tenant_access_attempt_total{endpoint="/api/v1/policies/{policy_id}"}` metric increments.

## Step 4 — Verify the RLS layer fails closed under a wrong context (US1 AS-3)

```
# Open a psql session under a non-service-principal role with the tenant context set to B.
psql "$POSTGRES_URL_TENANT_ROLE" <<'SQL'
  SET LOCAL app.tenant_id = 'tenant-b';
  SELECT count(*) FROM collection_policies WHERE policy_id = '<tenant A's policy_id>';
SQL
# Expect: count = 0 (RLS RESTRICTIVE policy returns zero rows even though the row exists).

# Same query with the context unset.
psql "$POSTGRES_URL_TENANT_ROLE" <<'SQL'
  RESET app.tenant_id;
  SELECT count(*) FROM collection_policies;
SQL
# Expect: count = 0 (missing-context defense).
```

**Expect**: Both queries return zero rows. The DB layer is the authoritative isolation boundary; even a hypothetical bug in the application handler that forgot to set the GUC would fail closed.

## Step 5 — Verify the rate-limit middleware (US2)

```
# Read tenant A's effective rate-limit config (default per FR-012).
curl -fsS http://localhost:8081/api/v1/tenant-config/self \
  -H "Authorization: Bearer $(cat /tmp/tenant-a.jwt)" | jq .
# Expect: source: "default", inbound: {sustained_rps: 2000, burst_capacity: 4000}, query: {sustained_rps: 200, burst_capacity: 400}

# Lower tenant A's inbound rate to a smoke-friendly value (service-principal write).
psql "$POSTGRES_URL" <<'SQL'
  INSERT INTO tenant_config(tenant_id, inbound_sustained_rps, inbound_burst_capacity,
                            query_sustained_rps, query_burst_capacity, updated_by_subject)
  VALUES ('tenant-a', 5, 5, 200, 400, 'service-principal://quickstart');
SQL

# Wait for LISTEN/NOTIFY-driven cache invalidation (~ 1 s; TTL fallback covers anything longer).
sleep 2

# Burst 20 requests at ~ 50 r/s against tenant A's inbound endpoint.
for i in $(seq 1 20); do
  curl -isS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8081/api/v1/findings \
    -H "Authorization: Bearer $(cat /tmp/tenant-a.jwt)" \
    -H "Content-Type: application/json" \
    --data @specs/001-policy-loop-vertical-slice/fixtures/finding-brake-wear-tenant-a.json &
done
wait
# Expect: A mix of 202 and 429; the 429 responses carry a `Retry-After` header.
```

**Expect**: At least 80% of over-budget requests receive 429 with `Retry-After` (SC-003 floor). Tenant B's parallel traffic (if any) is unaffected (SC-004).

## Step 6 — Verify the deployment-client tenant scope check (US4)

```
# Synthesize a policy whose declared tenant is A but whose target vehicle is owned by B.
# This is a malicious-construct test; the foundation smoke uses a service-principal
# helper to fabricate the in-flight state at the deployer node.
python scripts/dev_inject_mismatched_deployment.py \
  --tenant tenant-a \
  --vehicle VIN-BBBB-0001  \
  --policy-id POL-MISMATCH-1

# Expect: the deployer-node test harness logs a Fatal error class, no outbound
# call is made to the simulator, an audit row of kind=deployment_rejected is
# written, and Prometheus `collectmind_deployment_rejected_total` increments.
psql "$POSTGRES_URL" -c "SELECT count(*) FROM audit_events WHERE kind='deployment_rejected';"
# Expect: count = 1
```

**Expect**: The deployer refuses the deployment. The audit row carries the policy's declared tenant, the vehicle's owning tenant (operator-readable only; the tenant-A principal never sees this field via the regular API), and the originating finding's correlation_id.

## Step 7 — Invoke the break-glass primitive (US1-adjacent; FR-005a)

```
# As operator Alice (operator JWT, audience=collectmind-operator), query tenant A's audit chain.
curl -fsS -X POST http://localhost:8081/api/v1/audit/break-glass/query \
  -H "Authorization: Bearer $(cat /tmp/op-alice.jwt)" \
  -H "Content-Type: application/json" \
  --data '{
    "tenant_scope":  "tenant-a",
    "correlation_id": "<the finding correlation_id from Step 2>",
    "reason_code":   "support_escalation"
  }' | jq .
# Expect: the four-kind audit chain (generated/validated/deployed/outcome) for tenant A,
# even though Alice is operating outside any tenant context.
```

**Expect**: The bypass returns the requested audit events. A `kind=break_glass` row is written to `audit_events` in the same transaction as the SELECT, carrying:
- `operator_principal_subject`: `alice`
- `tenant_scope`: `tenant-a`
- `reason_code`: `support_escalation`
- `correlation_id`: the operator-supplied correlation id (echoed from the request, used for incident-response chaining).

Verify the audit row landed:
```
psql "$POSTGRES_URL" -c "
  SELECT kind, extras->>'operator_principal_subject', extras->>'reason_code'
  FROM audit_events
  WHERE kind = 'break_glass'
  ORDER BY occurred_at DESC LIMIT 1;
"
# Expect: break_glass | alice | support_escalation
```

Negative path: a tenant JWT presented at the break-glass endpoint must fail authentication.
```
curl -isS -X POST http://localhost:8081/api/v1/audit/break-glass/query \
  -H "Authorization: Bearer $(cat /tmp/tenant-a.jwt)" \
  -H "Content-Type: application/json" \
  --data '{"tenant_scope":"tenant-a","correlation_id":"x","reason_code":"support_escalation"}' \
  | head -n 1
# Expect: HTTP/1.1 401 Unauthorized
```

## Step 8 — Verify hot-store key tenancy (US3)

```
# Use the hot-store CLI to read tenant A's and tenant B's value for the same vehicle id under the new key shape.
# (The vehicle IDs in the foundation smoke are distinct, so this step exercises the key shape rather than the collision case;
# the integration test `tests/integration/test_hot_store_key_rollover.py` covers the collision case.)

redis-cli -h localhost -p 6379 KEYS 'tenant-a:*' | head -n 5
redis-cli -h localhost -p 6379 KEYS 'tenant-b:*' | head -n 5
# Expect: keys carry the tenant prefix. No keys of shape `<vehicle_id>:<signal_name>` (legacy) should be observable
# after the 24-hour TTL rollover window. During the rollover window legacy keys may coexist; the integration test
# asserts both branches of the read path.
```

## Cleanup

```
docker compose --profile operator-issuer -f infra/compose/docker-compose.yaml down
```

## Expected wall-clock

End-to-end on a warm Compose stack: under 5 minutes for steps 1-8. The SC-008 600-second budget from feature 001 covers the foundation smoke; this quickstart sits well inside it.

## SLO-anchor for the smoke

| Step | Spec anchor | Assertion |
|---|---|---|
| 3   | SC-001 / FR-006 | Cross-tenant read returns 404. |
| 4   | SC-002 / FR-002 / FR-003 | DB session under wrong-context returns 0 rows. |
| 5   | SC-003 / SC-004 / FR-010 / FR-011 / FR-013 | Burst above limit returns 429 + Retry-After; tenant B unaffected. |
| 6   | SC-012 / FR-021 / FR-022 / FR-023 | Cross-tenant deployment fatally rejected + audited. |
| 7   | SC-013 / FR-005a / FR-005b | Break-glass returns events + atomic audit row. |
| 8   | FR-018 / FR-020 | Hot-store keys carry tenant prefix. |

Steps that fail this quickstart MUST block feature-002 closure. The integration-tier tests under `tests/integration/test_*.py` are the CI-side equivalents and are gated on every PR per `.github/workflows/ci.yaml`.

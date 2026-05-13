# Deployment refused — tenant-vehicle mismatch

Alert: `DeploymentTenantMismatch`. Constitution Principle X binding contract (per-tenant data isolation at the deployment client); Spec FR-021 / FR-022 / FR-023 / FR-024; ADR-0009 Part 6.

The deployer node refused an outbound deployment because at least one target vehicle in the policy did not belong to the policy's declared tenant. The Fatal `TenantVehicleMismatch` short-circuited the deployer's existing Recoverable retry posture; no outbound call was made; an immutable `kind=deployment_rejected` audit row landed before the Fatal propagated.

## Symptoms

- One or more `DeploymentTenantMismatch` alerts firing with `severity=page`, `slo=SC-012`, and a `tenant_id` label identifying the rejecting (requesting) tenant.
- `audit_events` carrying rows of `kind=deployment_rejected` with the FR-023 minimum field set (`policy_ref`, `target_vehicle_id`, `policy_declared_tenant_id`, `vehicle_owning_tenant_id`); operator-readable via the break-glass audit-admin surface (FR-005a).
- Operator dashboard "Deployment-rejected count per reason" panel (Phase 13 T281) shows a non-zero rate.
- No corresponding outbound deploy in the downstream Collector AI logs for the affected `correlation_id` (the Fatal fires before the outbound call by design).
- The requesting tenant's surface sees a 500-equivalent on the policy-loop path; the policy was generated and validated but not deployed.

## Dashboard

- Grafana → CollectMind End-to-End → "Deployment-rejected count per reason" panel (Phase 13 T281; Phase 12 ships the metric, Phase 13 ships the panel JSON).
- Correlate with the audit chain at `GET /api/v1/audit/{correlation_id}` for the rejecting tenant — the `generated` and `validated` rows precede the `deployment_rejected` row.
- For cross-tenant root-cause investigation, use the operator-only break-glass audit-admin surface (`POST /api/v1/audit/break-glass/query` with `reason_code=incident_response`) to read the rows of the `vehicle_owning_tenant_id` tenant and confirm the ownership state at the time of rejection.

## Mitigation

1. **Confirm ownership state**. The most common cause is a stale ownership cache after a vehicle transfer. Query `tenant_vehicles` for the affected `target_vehicle_id` and verify the current owner matches the `vehicle_owning_tenant_id` in the audit row. If the cache has been invalidated correctly, the row matches.
2. **If the ownership transition is in flight**: wait for the cache TTL (1 h per ADR-0009 Part 4) or invoke the service-principal invalidation primitive against `OwnershipCache.invalidate(vehicle_id)` for the affected vehicle ids.
3. **If the policy's declared tenant is wrong** (operator entered the wrong VIN in a manual policy injection; corrupted in-flight policy state): the policy is the defect — it MUST be regenerated against the correct vehicle scope. The original Fatal is the right outcome; do not retry the existing policy.
4. **If a vehicle was assigned to the wrong tenant** (operator workflow defect): use the service-principal write path on `tenant_vehicles` to correct the assignment. The atomic `tenant_vehicles_audit_trigger` writes a `kind=vehicle_assignment_change` audit row capturing the corrective transition.
5. **If the audit-row write failed inside the Fatal handler**: the deployer-node wrapper at `src/collectmind/deployer/node.py:deploy_with_tenant_scope_check` re-raises the audit-write failure in place of the original Fatal. Both failures land on the traceback; investigate the audit-write failure (likely a Postgres outage or a migration in flight) before retrying.

## Escalation

- 1 rejection: log + record. If isolated, the root cause is almost always a wrong VIN in a manual policy injection; coordinate with the requesting tenant.
- ≥ 5 rejections within 15 minutes for the same `(tenant_id, target_vehicle_id)`: a vehicle transfer race or a cache-coherence defect. Page the platform on-call; pull the `tenant_vehicles_history` rows for that vehicle to reconstruct the ownership timeline.
- ≥ 5 rejections within 15 minutes across multiple tenants: a systemic defect (ownership store corruption, cache poisoning, or a deployer regression). Declare an incident, freeze new deployments at the orchestration-api ingress, and root-cause before un-freezing.
- ≥ 1 rejection where the audit row failed to land: a Principle XVII regression. Treat as P0 — the deployer's atomic-audit contract is the operator's only durable signal that a Fatal rejection happened.

## Related ADRs

- [ADR-0007](../../docs/adr/0007-rls-restrictive-and-break-glass.md) — break-glass audit-admin surface used by operators to read across tenant boundaries during this incident class.
- [ADR-0009](../../docs/adr/0009-tenant-vehicle-ownership-store.md) — tenant-vehicle ownership store; Part 6 specifies the deployer hot-path validation and the FR-023 audit-row minimum field set.

## Related FRs

- FR-021 — deployer-node first-gate tenant-scope check.
- FR-022 — Fatal class supersedes Recoverable retry.
- FR-023 — `kind=deployment_rejected` audit row minimum field set.
- FR-024 — page-tier alert + runbook (this page).
- SC-012 — alert routing budget (≤ 60 s).

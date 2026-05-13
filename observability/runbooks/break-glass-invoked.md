# Break-glass operator bypass invoked

Alert: `BreakGlassInvoked`. SC-013 single-invocation page. Constitution Principle XVII (Audit Is a Feature, Not a Log); ADR-0007 Part 5; Spec FR-005a / FR-005b / FR-005c.

Fires the moment an operator invokes the `POST /api/v1/audit/break-glass/query` primitive. Every break-glass call is a cross-tenant audit read under elevated audit and the operational pattern is "page on every event, not on rate." Burst-pattern paging is a separate alert (`BreakGlassBurstInvocation`).

## Symptoms

- `BreakGlassInvoked` alert firing with `severity=page`, `slo=SC-013`, and a `summary` naming the break-glass primitive.
- An `audit_events` row of `kind=break_glass` landed in the same DB transaction as the bypassed audit-query SELECT (per FR-005b atomic-audit).
- The row carries the FR-005b minimum field set: operator principal subject, target tenant scope, reason code, correlation id.
- Operator dashboard "Break-glass volume per operator subject" panel (Phase 13 T281) shows the increment within the dashboard-lag budget (SC-006).

## Dashboard

- Grafana → CollectMind End-to-End → "Break-glass volume per operator subject" panel (T281).
- Drill into the audit chain at `GET /api/v1/audit/{correlation_id}` from a service-principal context (the break-glass-row is RLS-scoped to the elevated principal that wrote it).
- Cross-reference the `audit_events.originating_finding` JSON for the reason code; the documented enumeration is `support_escalation`, `incident_response`, `legal_hold`, `regulatory_request` (extend via ADR amendment if a new code is needed).

## Mitigation

1. **Identify the invocation**: query `audit_events WHERE kind='break_glass' ORDER BY occurred_at DESC LIMIT 5` and confirm the operator subject + reason code match the operator's named ticket or incident. The audit row is the system of record.
2. **Confirm reason-code legitimacy**: cross-reference the `reason_code` against the documented operational scenario. `support_escalation` for a customer ticket; `incident_response` for a Sev-1 in flight; `legal_hold` for a regulator-driven retention; `regulatory_request` for compliance retrieval. Anything else: investigate.
3. **Verify the audit row is queryable from the operator-readable audit-admin surface**: `GET /api/v1/audit/admin/break-glass-history` (operator JWT required). The row MUST be visible; if it is not, FR-005b's atomic-audit property has regressed — that's a P0 incident.
4. **No remediation needed if the invocation is legitimate**: the alert exists to ensure visibility, not to gate the operator workflow. Page-tier severity exists so the operator's invocation is acknowledged in the operational record.
5. **If the invocation is unexpected** (no matching ticket, no incident, no legal directive): treat as a possible operator-key compromise. Escalate immediately per the escalation tier below.

## Escalation

- 1 invocation with a clear matching ticket: log + record. No further action.
- 1 invocation without a matching ticket: page the security on-call. Investigate whether the operator-credential was used as expected.
- 2+ invocations within 1 hour from the same operator without matching tickets: trigger the operator-credential rotation runbook AND review the affected tenants' audit chains for unauthorized reads.
- Any invocation against tenants the operator is not authorized to administer: P0 — operator-key compromise probable; rotate immediately + freeze the affected operator subject in the issuer; declare an incident.

If the `BreakGlassBurstInvocation` critical alert fires alongside this page alert, the burst alert takes operational precedence — the same operator generating > 15 invocations in 5 minutes is by definition the abuse pattern this alert is meant to surface.

## Related ADRs

- [ADR-0007](../../docs/adr/0007-rls-restrictive-and-break-glass.md) Part 5 — break-glass primitive + atomic-audit pattern.

## Related FRs

- FR-005a — service-principal bypass primitive scope.
- FR-005b — atomic-audit row's minimum field set.
- FR-005c — scope boundary (the operator-facing surface is a separate feature; this alert covers the primitive).
- SC-013 — 100% of invocations produce a `kind=break_glass` audit row.

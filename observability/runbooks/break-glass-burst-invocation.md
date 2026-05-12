# Break-glass burst invocation pattern

Alert: `BreakGlassBurstInvocation`. SC-013 burst critical. Constitution Principle IX (Security as a First-Class Requirement); ADR-0007 Part 5; Spec FR-005a / FR-005b.

Distinct from `BreakGlassInvoked` (page on every invocation): this alert fires when a SINGLE operator subject sustains > 0.05 invocations per second over a 5-minute window (≈ 15 invocations in 5 minutes). That rate is well above any legitimate single-incident workflow; it is the abuse pattern the alert is built to surface.

## Symptoms

- `BreakGlassBurstInvocation` alert firing with `severity=critical`, `slo=SC-013`, and `operator_subject` label naming the operator generating the burst.
- The corresponding `BreakGlassInvoked` page alert has fired repeatedly in the last 5 minutes (each invocation pages individually; the burst alert is the aggregate).
- `audit_events WHERE kind='break_glass' AND principal_subject='{{ $labels.operator_subject }}' AND occurred_at > now() - interval '5 minutes'` returns more than 15 rows.
- Operator dashboard "Break-glass volume per operator subject" panel (T281) shows a clear rate spike for the named operator.

## Dashboard

- Grafana → CollectMind End-to-End → "Break-glass volume per operator subject" panel — the operator's per-second invocation rate over the last 30 minutes.
- Audit-admin query: `SELECT correlation_id, originating_finding->>'tenant_scope', originating_finding->>'reason_code', occurred_at FROM audit_events WHERE kind='break_glass' AND principal_subject = $1 AND occurred_at > now() - interval '15 minutes' ORDER BY occurred_at DESC` — produces the full burst timeline.
- Cross-reference with the operator's issuer log to confirm credential origin (genuine operator key vs. compromised credential vs. replayed JWT).

## Mitigation

1. **Freeze the operator's credential immediately**. Treat as a potential operator-key compromise until ruled out. Revoke the operator JWT at the issuer (`POST /admin/operators/{operator_subject}/revoke` if available) or rotate the operator's signing key per `docs/runbook/operator-credential-rotation.md` if not.
2. **Quarantine the audit trail for forensic review**. The burst of `kind=break_glass` rows is the forensic record. Do NOT delete or modify; per Principle XVII these rows are immutable by the audit trigger anyway, but ensure ops doesn't issue a corrective `DELETE` against `audit_events` thinking it's noise.
3. **Identify which tenants were read**. Aggregate the `originating_finding->>'tenant_scope'` across the burst window. If the affected tenants include any that the operator is not authorized to administer per the operator role assignment, the compromise is confirmed.
4. **Audit the upstream causes**. Compare the burst pattern to known operational workflows: a legal-hold retrieval against a multi-tenant fleet legitimately reads many tenants in sequence; a support-tool gone wrong (loop, retry storm, infinite recursion) reads many tenants accidentally. The reason codes carried on the audit rows narrow the diagnosis.
5. **If compromise is confirmed**: declare an incident, rotate every operator credential issued from the same trust root, and notify the affected tenants per the data-incident notification policy.
6. **If a loop/retry storm in operator tooling is confirmed**: file a bug against the operator tool; the alert was correct to fire; no further security action is required beyond rate-limiting the tool internally.

## Escalation

- Burst fires + operator denies the activity: P0 — operator-key compromise. Rotate, freeze, notify, incident commander.
- Burst fires + operator confirms ongoing legitimate workflow (e.g., active legal-hold retrieval): document the workflow in the runbook addendum; the alert was correctly tuned but the operator's tooling should rate-limit itself to stay below the threshold.
- Burst fires + audit row count is wildly higher than dashboard count: a metric-emission regression. Treat as P1 — the metric MUST track the audit row 1:1 per Principle V; investigate the increment path in `audit_admin/api.py`.
- `BreakGlassBurstInvocation` fires with no corresponding `BreakGlassInvoked` history: a metric-emission regression in the opposite direction; the per-invocation page didn't fire but the rate did. P1.

## Related ADRs

- [ADR-0007](../../docs/adr/0007-rls-restrictive-and-break-glass.md) Part 5 — break-glass primitive + atomic-audit.

## Related FRs

- FR-005a — operator-principal authentication + reason-code enumeration.
- FR-005b — atomic-audit row minimum field set; the burst alert depends on this contract holding.
- SC-013 — 100% of invocations produce a `kind=break_glass` audit row.

# Observability Requirements Quality Checklist: Policy-Loop Vertical Slice

**Purpose**: Validate the quality of observability-related requirements in the spec before planning. Items test the requirements themselves rather than implementation behavior.
**Created**: 2026-05-09
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [ ] CHK001 Are structured logs required for every accepted, rejected, generated, validated, deployed, and outcome operation, and is the operation list exhaustive for the pipeline? [Completeness, Spec §FR-013]
- [ ] CHK002 Is the metric set enumerated at a level a dashboard reviewer can implement against, including ingest rate, generation funnel, validation pass rate, time-to-deploy distribution, hypothesis confirmation rate, dead-letter count, and authentication-failure count? [Completeness, Spec §FR-014]
- [ ] CHK003 Is a single operator dashboard required, and is the metric set it must surface explicitly tied to FR-014? [Completeness, Spec §FR-015]
- [ ] CHK004 Is an alert required for every service-level objective breach, with each alert linked to a runbook entry? [Completeness, Spec §FR-016]
- [ ] CHK005 Is a runbook entry required for every alert the system can raise? [Completeness, Spec §FR-022]

## Requirement Clarity

- [ ] CHK006 Is "structured logs" defined precisely enough (format, required fields) that a reviewer can verify FR-013 compliance? [Clarity, Spec §FR-013]
- [ ] CHK007 Is the correlation identifier required by FR-013 specified as the same identifier visible in the dashboard (US2 acceptance scenario 3)? [Clarity, Spec §FR-013, §US2]
- [ ] CHK008 Are the outcome states (`confirmed`, `ruled out`, `no data`) reflected in the metric set as distinct counters or labels, or only implicit in `hypothesis_confirmation_rate`? [Clarity, Spec §FR-009, §FR-014]
- [ ] CHK009 Is the dashboard-lag bound expressed as a measurable threshold (10 seconds) and tied to a specific event ("event acceptance")? [Clarity, Spec §FR-015, §SC-006]
- [ ] CHK010 Is the meaning of "service-level objective" in FR-016 defined by the SC-### identifiers in Success Criteria, so an alert maps unambiguously to the breach it represents? [Clarity, Spec §FR-016, §Success Criteria]

## Requirement Consistency

- [ ] CHK011 Are the metrics in FR-014 a superset of the panels required by FR-015 and the alerts required by FR-016, with no metric named in one but missing from another? [Consistency, Spec §FR-014, §FR-015, §FR-016]
- [ ] CHK012 Is the PII-exclusion clause in FR-017 consistent with the no-PII-in-logs criterion in SC-007? [Consistency, Spec §FR-017, §SC-007]
- [ ] CHK013 Are the PR-tier vs workflow-dispatch-tier distinctions used in SC-002, SC-003, and SC-009 reflected in the metrics that the dashboard surfaces, so the dashboard does not conflate the two tiers' latencies? [Consistency, Gap]

## Acceptance Criteria Quality

- [ ] CHK014 Is the dashboard-lag criterion (SC-006) measurable by an automated check that can run in continuous integration? [Measurability, Spec §SC-006]
- [ ] CHK015 Is the SC-007 PII-exclusion criterion measurable by an automated check that runs on every build, and is "personal data" defined? [Measurability, Spec §SC-007]
- [ ] CHK016 Are the metric names listed in FR-014 stable enough to serve as the contract for the dashboard, or are they descriptive labels that the plan is free to rename? [Clarity, Ambiguity, Spec §FR-014]

## Coverage and Edge Cases

- [ ] CHK017 Is the empty-state dashboard behavior addressed at the spec level (all panels render, all values report zero, no panel shows an error)? [Coverage, Edge Case, Spec §Edge Cases]
- [ ] CHK018 Is the recovery-from-outage observability behavior specified (queued events visible, drain time visible)? [Coverage, Spec §US2 acceptance scenario 4, §SC-005]
- [ ] CHK019 Are the audit-record fields produced by the feedback-loop component (FR-009) enumerated at the spec level, or are they only mentioned at the constitutional level? [Coverage, Gap, Spec §FR-009, Constitution Principle XVII]

## Dependencies and Assumptions

- [ ] CHK020 Is the time-acceleration factor (FR-009a) recorded in metrics or audit records so a reader can distinguish a CI run from a production run? [Gap, Spec §FR-009a]
- [ ] CHK021 Is trace propagation required across service boundaries at the spec level, or only at the constitutional level? [Gap, Constitution Principle V]
- [ ] CHK022 Is the inbound `schema_version` value included in structured logs and audit records so a reviewer can correlate a malformed event with the schema it claims? [Gap, Spec §FR-003a]

## Traceability

- [ ] CHK023 Does every metric named in FR-014 appear at least once in either FR-015 (dashboard) or FR-016 (alert), so no metric is collected without a consumer? [Traceability, Spec §FR-014]
- [ ] CHK024 Does every SC-### with a measured runtime quantity (SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-010, SC-012) map to at least one metric in FR-014? [Traceability, Spec §Success Criteria]

## Notes

- Items marked `[Gap]` should be resolved in spec text or explicitly deferred via Assumptions before `/speckit-plan`.
- Items referencing the constitution imply the spec must either restate the rule as a feature-001 requirement or explicitly inherit the constitutional constraint.

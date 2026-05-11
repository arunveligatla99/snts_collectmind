# Testing Requirements Quality Checklist: Policy-Loop Vertical Slice

**Purpose**: Validate the quality of testing-related requirements in the spec before planning. Items test the requirements themselves rather than implementation behavior or test coverage.
**Created**: 2026-05-09
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [ ] CHK001 Are the test tiers (unit, contract, integration, load) enumerated at the spec level, with each tier's purpose distinguished? [Completeness, Spec §FR-021]
- [ ] CHK002 Is each user story associated with at least one tier of automated coverage (unit, contract, integration, or load)? [Completeness, Spec §US1, §US2, §US3]
- [ ] CHK003 Are the acceptance scenarios in US1, US2, and US3 written at a level that lets a reader derive concrete tests without inventing requirements? [Completeness, Spec §User Scenarios]
- [ ] CHK004 Are the edge cases (eight bullets) phrased with explicit expected outcomes that a test can assert against, not narrative description? [Completeness, Spec §Edge Cases]
- [ ] CHK005 Is the runbook-per-alert requirement (FR-022) paired with a testing requirement that asserts every alert is runbook-linked? [Completeness, Spec §FR-022, Gap]

## Requirement Clarity

- [ ] CHK006 Is the boundary between "PR-tier" pipeline (SC-009) and "workflow-dispatch tier" (SC-002, SC-003) defined unambiguously, including which tests run where? [Clarity, Spec §SC-002, §SC-003, §SC-009]
- [ ] CHK007 Is the meaning of "load test that asserts the service-level objectives" in FR-021 specific enough that a reviewer can identify which SC-### is asserted by which tier? [Clarity, Spec §FR-021, §Success Criteria]
- [ ] CHK008 Is the time-acceleration factor (FR-009a) named as the mechanism that lets feedback-loop tests run within CI wall-clock budgets? [Clarity, Spec §FR-009a]
- [ ] CHK009 Is the contract-test scope distinct from the integration-test scope, so a reviewer can place a new test in the right tier? [Clarity, Spec §FR-021, Ambiguity]
- [ ] CHK010 Is "real local stack" in FR-021 defined precisely (every component running, no in-memory shims for stores or transports)? [Clarity, Spec §FR-021]

## Requirement Consistency

- [ ] CHK011 Is the workflow-dispatch parenthetical added to SC-002 and SC-003 consistent with the workflow-dispatch carveout added to SC-009? [Consistency, Spec §SC-002, §SC-003, §SC-009]
- [ ] CHK012 Are the idempotency assertions in FR-012 (composite-key idempotency) and the Edge Cases bullet (duplicate publication produces single records) consistent? [Consistency, Spec §FR-012, §Edge Cases]
- [ ] CHK013 Is the schema-versioning behavior in FR-003a stated consistently with the inbound rejection behavior in FR-003 (different rejection class for different cause)? [Consistency, Spec §FR-003, §FR-003a]

## Acceptance Criteria Quality

- [ ] CHK014 Is FR-021's claim that tests "exercise every functional requirement" measurable by a traceability matrix that maps each FR to at least one test? [Measurability, Traceability, Spec §FR-021]
- [ ] CHK015 Is the PR-pipeline 20-minute target in SC-009 measurable from continuous-integration timing data without manual calculation? [Measurability, Spec §SC-009]
- [ ] CHK016 Are the load-test SC pass criteria (SC-002, SC-003) expressed as numeric thresholds a Locust scenario or equivalent can assert? [Measurability, Spec §SC-002, §SC-003]
- [ ] CHK017 Is the recovery-from-outage criterion (SC-005) testable in continuous integration via a controllable internal-dependency outage, or is it a production-only criterion? [Measurability, Coverage, Spec §SC-005]

## Coverage and Edge Cases

- [ ] CHK018 Are the three outcome states (`confirmed`, `ruled out`, `no data`) each covered by an acceptance scenario or edge-case bullet? [Coverage, Spec §FR-009, §US1, §Edge Cases]
- [ ] CHK019 Is the "structured not-found response" requirement (FR-011) covered by an acceptance scenario or by an explicit testing requirement? [Coverage, Spec §FR-011, Gap]
- [ ] CHK020 Is the "authentication failure produces no payload inspection" edge case testable as a unit-tier or contract-tier requirement, not only an integration-tier requirement? [Coverage, Spec §Edge Cases]
- [ ] CHK021 Is the "schema-versioning unknown major rejection" path covered by a testable requirement, distinct from a generic "schema validation failure" path? [Coverage, Spec §FR-003a, Gap]
- [ ] CHK022 Are tenant-claim absence and tenant-claim emptiness covered as separately testable rejection requirements, or conflated? [Coverage, Spec §FR-002]

## Dependencies and Assumptions

- [ ] CHK023 Is the deterministic-fingerprint stub (Constitution Principle XIV, ADR-0004) referenced in the spec as the mechanism that lets PR-tier load run without invoking the model? [Assumption, Gap, Spec §SC-009]
- [ ] CHK024 Is the contract-test corpus referenced in SC-011 specified at the spec level as a versioned artifact, or only implied? [Assumption, Spec §SC-011, Gap]

## Traceability

- [ ] CHK025 Does every functional requirement (FR-001 through FR-022, FR-003a, FR-009a) carry an identifier that a test can cite? [Traceability, Spec §Requirements]
- [ ] CHK026 Does every success criterion (SC-001 through SC-012) map to at least one test tier in FR-021, so no SC-### is asserted only manually? [Traceability, Spec §Success Criteria, §FR-021]

## Notes

- Items marked `[Gap]` should be resolved in spec text or explicitly deferred via Assumptions before `/speckit-plan`.
- Items marked `[Traceability]` will inform whether the V-Model extension's traceability matrix can be generated mechanically from the spec or requires manual mapping.

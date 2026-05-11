# Security Requirements Quality Checklist: Policy-Loop Vertical Slice

**Purpose**: Validate the quality of security-related requirements in the spec before planning. Items test the requirements themselves (completeness, clarity, consistency, measurability) rather than implementation behavior.
**Created**: 2026-05-09
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [ ] CHK001 Are authentication requirements specified for every external endpoint, and is the exemption set (health, readiness) explicitly enumerated? [Completeness, Spec §FR-018]
- [ ] CHK002 Is the authentication scheme named (OAuth2 client-credentials, JWT bearer) at a level a security reviewer can evaluate? [Completeness, Spec §FR-002, Clarifications Q2]
- [ ] CHK003 Are the JWT claims that govern authorization enumerated, and is the `tenant_id` claim documented as mandatory and non-empty? [Completeness, Spec §FR-002]
- [ ] CHK004 Are personal-data handling defaults specified for signals classified as PII-adjacent? [Completeness, Spec §Assumptions]
- [ ] CHK005 Are supply-chain requirements (SBOM emission, dependency pinning, vulnerability scanning) specified per build? [Completeness, Spec §FR-020]

## Requirement Clarity

- [ ] CHK006 Is "secret material" defined precisely enough that an automated check can validate FR-019 without false positives? [Clarity, Spec §FR-019, SC-007]
- [ ] CHK007 Is the rejection behavior on missing or empty `tenant_id` claim distinguished from rejection on invalid signature? [Clarity, Spec §FR-002]
- [ ] CHK008 Is the structured-error shape for authentication failure specified well enough that a contract test can assert it? [Clarity, Gap]
- [ ] CHK009 Is the threshold "critical or high" for vulnerability scanning defined against a named severity scale (e.g., CVSS)? [Clarity, Spec §FR-020]

## Requirement Consistency

- [ ] CHK010 Do the authentication requirements in FR-002 (inbound events) and FR-018 (every external endpoint) describe the same scheme without contradiction? [Consistency, Spec §FR-002, §FR-018]
- [ ] CHK011 Is the per-tenant identity model used in the composite finding key (Q1) consistent with the JWT-claim model used to authenticate the inbound event (Q2)? [Consistency, Clarifications Q1/Q2]
- [ ] CHK012 Are the spec's PII handling defaults consistent with the constitutional retention defaults (90-day raw signals, indefinite registry rows) referenced in the parent constitution? [Consistency, Spec §Assumptions, Constitution Principle X]

## Acceptance Criteria Quality

- [ ] CHK013 Is "no personal data appears in any log line, trace span, or metric label" measurable by an automated check on every build? [Measurability, Spec §SC-007]
- [ ] CHK014 Is the secret-in-repository prohibition associated with a specific build-time gate that fails the pull request? [Measurability, Spec §FR-019]
- [ ] CHK015 Is the SBOM artifact's required content set (Python dependencies, container layers, model weights) specified at the spec level? [Measurability, Spec §FR-020]

## Coverage and Edge Cases

- [ ] CHK016 Are token replay, token expiry, and key-rotation requirements addressed at the spec level, or are they intentionally deferred to the plan with a documented marker? [Coverage, Gap]
- [ ] CHK017 Is the "authentication failure produces no payload inspection" edge case stated as a requirement, not just an edge-case bullet? [Coverage, Spec §Edge Cases]
- [ ] CHK018 Is rate limiting per tenant addressed in the spec, or explicitly deferred? The spec is currently silent. [Gap, Coverage]
- [ ] CHK019 Are right-to-erasure (GDPR/CCPA) paths documented as requirements in this feature, or explicitly deferred? The spec does not state a requirement; the parent constitution does. [Gap, Spec §Assumptions, Constitution Principle X]
- [ ] CHK020 Are policy-payload code-signing requirements addressed at the spec level, or explicitly deferred to a downstream feature? [Gap]

## Dependencies and Assumptions

- [ ] CHK021 Is the OAuth2 issuer and JWKS endpoint identified as a runtime dependency whose availability affects FR-002, with the dependency documented? [Assumption, Dependency]
- [ ] CHK022 Is the canonical PII signal list identified as a versioned artifact with a change-control story, or only mentioned in passing? [Assumption, Gap]

## Threat Model and Traceability

- [ ] CHK023 Is the threat model for the inbound event interface documented, and are the requirements traceable to specific threats (e.g., spoofed tenant claim, replayed event, malformed payload)? [Traceability, Gap]
- [ ] CHK024 Does each security-relevant requirement carry an identifier that can be cited in a security-review approval (FR-002, FR-017, FR-018, FR-019, FR-020, SC-007)? [Traceability, Spec §Requirements]

## Notes

- Items marked `[Gap]` indicate requirement-quality issues that should be resolved either in spec text or by an explicit "deferred to feature NNN" marker in Assumptions before `/speckit-plan`.
- Items referencing constitutional principles imply that the spec must either restate the rule as a feature-001 requirement or explicitly note that the constitution governs and the spec inherits the constraint.

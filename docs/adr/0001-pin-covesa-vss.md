# ADR-0001: Pin COVESA VSS to v6.0

- Status: Accepted
- Date: 2026-05-09
- Deciders: Arun Veligatla (project author)
- Constitutional principle: X (Vehicle Telemetry Data Handling)

## Context

Constitutional Principle X names COVESA VSS (Vehicle Signal Specification) as the canonical signal vocabulary for CollectMind. The Policy Validator rejects any policy whose signal names are not valid VSS at the pinned version. For that gate to be deterministic, reproducible across machines, and auditable in policy registry rows, the VSS version must be fixed by an ADR before any spec, plan, or implementation references it.

VSS is maintained by COVESA at <https://github.com/COVESA/vehicle_signal_specification>. The project ships releases as Git tags on `master`, with each release publishing transformed artifacts (`vss.csv`, `vss.json`, `vss.yaml`, `vss.idl`, `vss.fidl`, `vss.graphql`, plus `quantities.yaml` and `units.yaml`) as release assets and a tarball of the source tree. Tags can in principle be moved; commit SHAs cannot, so the pin records both.

Sonatus's Foundation product uses VSS as its in-vehicle signal abstraction (per the architecture document Sonatus_Architecture_Diagrams.docx, Section 5). Pinning to a current stable release of the same standard demonstrates deliberate alignment, not coincidence.

## Decision

Pin COVESA VSS to **v6.0**.

- Tag: `v6.0`
- Commit SHA: `20c609bf95c73b51d483fb8f81a099d1d5b73066`
- Release URL: <https://github.com/COVESA/vehicle_signal_specification/releases/tag/v6.0>
- Published: 2026-01-16
- Status at pin time: not a prerelease; latest stable as of constitution sign-off (2026-05-09).

Operational rules that follow from the pin:

1. The Policy Validator loads its signal vocabulary from `vss.yaml` produced by checking out the repository at commit `20c609bf95c73b51d483fb8f81a099d1d5b73066` and running the COVESA tooling, or by downloading the corresponding release asset. The chosen path is recorded in the plan; both must produce byte-identical results.
2. The downloaded artifact is verified by SHA-256 against a checksum manifest committed to `config/vss/v6.0/manifest.sha256` at feature 001 implementation time. A checksum mismatch fails the build, mirroring the model-weights supply-chain controls in Principle IX.
3. The pinned tag and commit SHA are recorded in every audit record produced by the Policy Validator (alongside the SLM revision SHA mandated by Principle XVII), so that historical policy validations can be reproduced even after this ADR is superseded.
4. Non-VSS signal names in a generated policy are rejected with a structured `ValidationError` that names each invalid signal and, where a single-edit-distance VSS alternative exists, suggests it. The lookup table is built from the v6.0 catalog only.
5. PII-adjacent VSS branches (per Principle X: precise geolocation, driver biometrics, personal usage patterns) are derived from the v6.0 tree and recorded in `config/vss/v6.0/pii_signals.yaml` as a versioned artifact subject to its own change-control review.

## Consequences

### Positive

- Validator behavior is deterministic and reproducible. The same input policy validates identically on any machine and at any future date.
- Audit records remain interpretable for the lifetime of the policy registry, because the validating vocabulary is fixed by SHA.
- The pin demonstrates discipline expected at portfolio quality: a real version, a real commit, a real provenance check.
- Aligns with Sonatus Foundation's published VSS abstraction; the v6.0 release is recent enough (2026-01-16) to be credible alignment rather than legacy match.

### Negative

- VSS releases land on a roughly biannual cadence. Post-v6.0 features (signals, units, structural revisions) require a new ADR that supersedes this one and a deliberate validator upgrade. Drift is not free.
- Any specification or external partner expecting a different VSS minor version (e.g., a real Sonatus integration that has standardized on v5.1) would force a rebase. Mitigation: the validator can in principle support multiple pinned vocabularies behind a tenant-scoped configuration; that capability is deferred and is not introduced by this ADR.

### Neutral

- The repository commits the VSS-derived lookup tables (or the manifest plus a build script) under `config/vss/v6.0/` rather than carrying the upstream tarball verbatim. Either choice is compatible with this ADR, and the plan picks one with rationale.
- Re-pinning to a newer VSS release is a constitutional-amendment-adjacent change: it does not amend any principle text, but it does change the gate the validator enforces. A superseding ADR is the correct vehicle.

## Alternatives considered

### Track `master`

Rejected. A moving target makes the validator gate non-deterministic, breaks reproducibility of historical audit records, and contradicts Principle II (no mocked or shifting subsystems where a real, pinned one is feasible).

### Pin to v5.1 (released 2025-07-29)

Rejected. v5.1 is superseded by v6.0 in stable; pinning to a non-current stable release without a concrete blocker introduces gratuitous lag and weakens the alignment-with-current-state argument. No CollectMind requirement depends on v5.1-specific behavior.

### Pin to v6.0rc1 (released 2025-12-18)

Rejected. Prerelease tags are not stable by COVESA's own labeling. Principle II's "real subsystems" stance applies to standards too: the released, non-prerelease tag is the right pin.

### Pin to a specific commit on `master` after v6.0

Rejected. Post-release commits on `master` are not an officially numbered VSS version. Audit records would have to cite a bare SHA with no human-readable version label, weakening Principle XVII's defensibility-to-OEMs argument.

## References

- COVESA Vehicle Signal Specification repository: <https://github.com/COVESA/vehicle_signal_specification>
- v6.0 release page: <https://github.com/COVESA/vehicle_signal_specification/releases/tag/v6.0>
- COVESA VSS documentation: <https://covesa.github.io/vehicle_signal_specification/>
- Constitution Principle X (Vehicle Telemetry Data Handling) at `.specify/memory/constitution.md`
- Sonatus Foundation Data Services VSS abstraction (per `Sonatus_Architecture_Diagrams.docx`, Section 5)

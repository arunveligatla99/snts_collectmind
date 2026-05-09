# Architecture Decision Records

This directory holds the ADRs that govern CollectMind. ADRs are written in MADR format, numbered sequentially, and never edited after acceptance. Superseding decisions create a new ADR that links back to the one being replaced.

## When each ADR is drafted relative to the spec-kit phases

| ADR | Topic | Drafted | Reason |
|---|---|---|---|
| [ADR-0001](0001-pin-covesa-vss.md) | COVESA VSS version pin | During `/speckit-constitution` finalization | The constitution requires VSS as the canonical signal vocabulary; the version must be fixed before any spec or plan references it. |
| ADR-0002 | Default Small Language Model (model name, revision SHA, license, runtime, quantization, eval-suite baseline, upgrade and rollback procedure) | Between `/speckit-constitution` and `/speckit-plan` | Answers Decision D3. The plan's MODEL LAYER section assumes the choice has been made. |
| ADR-0003 | Constrained-decoding library (outlines vs instructor vs equivalent) | Between `/speckit-constitution` and `/speckit-plan` | Answers Decision D4. The plan's MODEL LAYER section names the library. |
| ADR-0004 | Deterministic-fingerprint Policy Generator stub for smoke and load tests | As part of `/speckit-plan` output | The stub is a CI-design decision that depends on the test topology defined by the plan. |
| ADR-0005 | SLM hosting topology on AWS (ECS on EC2 with g5/g6 vs EKS with a GPU node group) | As part of `/speckit-plan` output | Infrastructure decision that depends on the plan's compute module. |

## Rules

- An ADR is required for every non-obvious decision and for every deviation from a constitutional principle.
- Constitutional Principles IV, VII, IX, X, XI, XIII, and XIV cannot be deviated from; changes there require a constitution amendment in a PR, not an ADR.
- New ADRs are numbered sequentially. Superseded ADRs stay in the directory; the new ADR records the link to the one it replaces.
- The constitution's Documentation Standards subsection points at this file. Update both this file and the constitution if the table above changes.

## MADR template

Each ADR follows this structure. Copy [`0001-pin-covesa-vss.md`](0001-pin-covesa-vss.md) as the canonical example.

```
# ADR-NNNN: Short title

- Status: {Proposed | Accepted | Deprecated | Superseded by ADR-XXXX}
- Date: YYYY-MM-DD
- Deciders: {names or roles}
- Constitutional principle: {principle that motivates the decision, if any}

## Context

What problem are we solving? What constraints apply?

## Decision

What did we choose? Be specific: versions, SHAs, URLs.

## Consequences

### Positive
### Negative
### Neutral

## Alternatives considered

What else was on the table, and why was it rejected?

## References
```

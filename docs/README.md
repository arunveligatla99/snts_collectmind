# /docs index

Cross-references for the CollectMind documentation set. T138 polish artifact.

## Top of stack (read first)

- [`/CLAUDE.md`](../CLAUDE.md) — session primer; principles; mandatory pre-read.
- [`PROJECT_STATE.md`](PROJECT_STATE.md) — current phase, commit SHAs, deferred items, test bar.
- [`DECISIONS.md`](DECISIONS.md) — append-only dated log of process and pattern decisions.

## Architecture Decision Records

ADR drafting cadence and table of contents at [`adr/README.md`](adr/README.md).

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](adr/0001-pin-covesa-vss.md) | COVESA VSS v6.0 pin | Accepted |
| [ADR-0002](adr/0002-default-slm-qwen2-5-7b-instruct.md) | Default SLM — Qwen2.5-7B-Instruct | Proposed (eval baseline gated to GPU runner, T137) |
| [ADR-0003](adr/0003-constrained-decoding-library.md) | Constrained-decoding library — outlines | Accepted |
| [ADR-0004](adr/0004-fingerprint-stub.md) | Deterministic-fingerprint Policy Generator stub | Accepted |
| [ADR-0005](adr/0005-slm-hosting-topology.md) | SLM hosting topology on AWS | Accepted |
| [ADR-0006](adr/0006-dev-default-policy-client.md) | Dev-only `DevDefaultPolicyClient` | Accepted |

## Spec-kit feature 001

The active feature lives at [`/specs/001-policy-loop-vertical-slice/`](../specs/001-policy-loop-vertical-slice/).

| Artifact | Path |
|---|---|
| Specification | [`spec.md`](../specs/001-policy-loop-vertical-slice/spec.md) |
| Implementation plan | [`plan.md`](../specs/001-policy-loop-vertical-slice/plan.md) |
| Research notes | [`research.md`](../specs/001-policy-loop-vertical-slice/research.md) |
| Data model | [`data-model.md`](../specs/001-policy-loop-vertical-slice/data-model.md) |
| Contracts (OpenAPI 3.1 + AsyncAPI 3.0) | [`contracts/`](../specs/001-policy-loop-vertical-slice/contracts/) |
| Quickstart | [`quickstart.md`](../specs/001-policy-loop-vertical-slice/quickstart.md) |
| Tasks | [`tasks.md`](../specs/001-policy-loop-vertical-slice/tasks.md) |
| Checklists | [`checklists/`](../specs/001-policy-loop-vertical-slice/checklists/) |

## Security

- [`security/threat-model.md`](security/threat-model.md) — STRIDE + LINDDUN coverage; six threats (3 spec + 3 R-019) mapped to FRs + verifying tests.

## Operational

- [`/observability/runbooks/INDEX.md`](../observability/runbooks/INDEX.md) — alert + failure-mode runbook index.
- [`/observability/prometheus/rules.yaml`](../observability/prometheus/rules.yaml) — Prometheus alert rules (one per binding SLO).
- [`/observability/grafana/dashboards/collectmind-end-to-end.json`](../observability/grafana/dashboards/collectmind-end-to-end.json) — auto-provisioned operator dashboard.

## API reference

- [`api/openapi.yaml`](api/openapi.yaml) — generated dump of the FastAPI app's OpenAPI 3.1 surface. CI gate (T132) diffs against this file on every PR.

## Examples

- [`examples/finding-brake-wear.json`](examples/finding-brake-wear.json) — example diagnostic finding payload referenced by the quickstart.

## Readiness

- [`runbook/feature-001-readiness-review.md`](runbook/feature-001-readiness-review.md) — closure review of feature 001 against the seven NON-NEGOTIABLE constitutional principles (T141).

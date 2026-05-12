"""T281 red-phase test: Phase 13 Grafana dashboard panel additions (feature 002 US-cross).

Pins three contracts that the Phase 13 T281 dashboard extension MUST satisfy:

    1. Three NEW Prometheus metric series are declared in
       ``src/collectmind/observability/metrics.py``:
         - ``collectmind_break_glass_invocation_total`` (labels: ``operator_subject``,
           ``tenant_scope``, ``reason_code``) — drives the BreakGlassInvoked alert
           AND the "break-glass volume per operator" dashboard panel.
         - ``collectmind_deployment_rejected_total`` (labels: ``policy_declared_tenant_id``,
           ``vehicle_owning_tenant_id``, ``reason``) — drives the DeploymentTenantMismatch
           alert AND the "deployment-rejected count per reason" dashboard panel.
         - ``collectmind_cross_tenant_access_attempt_total`` (labels: ``endpoint``,
           ``decision``) — drives the "cross-tenant access-attempt rate per endpoint"
           dashboard panel. (No alert required at Phase 13; FR-009 ensures the metric
           is PII-clean.)
    2. The shipped dashboard JSON
       (``observability/grafana/dashboards/collectmind-end-to-end.json``) references each
       of the three NEW metric series above PLUS the existing
       ``collectmind_ratelimit_decision_total`` (rate-limit decision split per tenant).
    3. ``dashboard_provisioner.validate_dashboard`` returns no errors against the
       shipped dashboard JSON — every metric referenced in a panel is declared in
       ``metrics.py``.

Together these pin the T105-style bidirectional metric-declaration discipline from
Phase 4 against the Phase 13 panel additions. Red-phase signal: the three new metric
series are not yet declared AND the dashboard JSON does not yet reference them.

Anchors: Principle V / FR-014 / FR-024 / SC-012 / SC-013 / SC-014 / Principle IV.
"""

from __future__ import annotations

import json
from pathlib import Path

from collectmind.observability import dashboard_provisioner as dp

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = (
    REPO_ROOT / "observability" / "grafana" / "dashboards" / "collectmind-end-to-end.json"
)


# Phase 13 T281 metric-declaration contract. Each entry is the BASE series name; the
# dashboard_provisioner's declared_metric_names() returns every derived suffix
# (``_total``, ``_bucket``, ``_count``, ``_sum``) automatically per Phase 4's discipline.
PHASE_13_REQUIRED_METRIC_BASES: tuple[str, ...] = (
    "collectmind_break_glass_invocation_total",
    "collectmind_deployment_rejected_total",
    "collectmind_cross_tenant_access_attempt_total",
)

# Phase 13 T281 dashboard-reference contract. Every base name below MUST appear in at
# least one panel ``expr`` in the shipped dashboard JSON. The rate-limit-decision metric
# already exists from Phase 10; Phase 13 surfaces it on the operator dashboard for the
# allow/reject split per tenant (the third of the four panels named by T281).
PHASE_13_DASHBOARD_METRIC_REFS: tuple[str, ...] = (
    "collectmind_break_glass_invocation_total",
    "collectmind_deployment_rejected_total",
    "collectmind_cross_tenant_access_attempt_total",
    "collectmind_ratelimit_decision_total",
)


def _load_dashboard_metric_refs() -> set[str]:
    """Walk every panel target in the shipped dashboard JSON and return the set of
    ``collectmind_``-prefixed metric tokens referenced across all ``expr`` fields."""
    doc = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    refs: set[str] = set()
    for panel in doc.get("panels", []):
        refs |= dp.referenced_metric_names(panel.get("targets", []))
    return refs


def test_phase_13_metrics_declared() -> None:
    """Each Phase 13 metric base MUST appear in ``declared_metric_names()`` so the
    bidirectional dashboard-to-metrics check sees them on the metrics side."""
    declared = dp.declared_metric_names()
    missing = [name for name in PHASE_13_REQUIRED_METRIC_BASES if name not in declared]
    assert not missing, (
        f"Phase 13 T281 has not declared metric(s) {missing} in "
        f"src/collectmind/observability/metrics.py. The metrics MUST be declared so the "
        f"bidirectional T105-style check finds them on the metrics side."
    )


def test_phase_13_dashboard_panels_reference_required_metrics() -> None:
    """Each Phase 13 metric base MUST be referenced by at least one panel ``expr``."""
    refs = _load_dashboard_metric_refs()
    missing = [name for name in PHASE_13_DASHBOARD_METRIC_REFS if name not in refs]
    assert not missing, (
        f"Phase 13 T281 has not landed: dashboard does not reference metric(s) {missing}. "
        f"Each Phase 13 panel MUST be wired to its metric (Principle V)."
    )


def test_phase_13_dashboard_validate_returns_no_drift() -> None:
    """The bidirectional T105-style check MUST return no errors after T281 lands.

    Every metric referenced by the dashboard MUST be declared in ``metrics.py``; an
    undeclared reference means the panel renders zero data in production. The check is
    the canonical Phase 4 dashboard-provisioner guard from feature 001."""
    errors = dp.validate_dashboard(DASHBOARD_PATH)
    assert not errors, (
        "dashboard_provisioner.validate_dashboard() returned errors:\n  - "
        + "\n  - ".join(errors)
    )

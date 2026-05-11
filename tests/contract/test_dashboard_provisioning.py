"""T105: Contract test for the auto-provisioned operator dashboard.

Asserts that `observability/grafana/dashboards/collectmind-end-to-end.json` is the
operator dashboard mandated by FR-014 and FR-015:

- JSON is well-formed.
- Refresh interval is at most 10 seconds (FR-015 / SC-006).
- Every panel's PromQL expression references at least one declared
  `collectmind_`-prefixed metric (positive: the dashboard is wired to the real
  metric names exported by `src/collectmind/observability/metrics.py`).
- No panel expression references an undeclared `collectmind_`-prefixed metric
  (negative: prevents silent metric-name drift between dashboard and code).
- The dashboard contains the panels mandated by FR-014 plus T110, identified by
  canonical title substring: ingest rate, generation funnel, validation pass
  rate, time-to-deploy (p50/p95/p99), hypothesis confirmation rate, dead-letter
  count, retry rate, authentication-failure rate, SLM generation latency, SLM
  constraint-violation rate, active SLM weight SHA, active SLM runtime image
  digest.

Per FR-021 (test-first per Principle IV) this test exists before T110 lands the
production dashboard JSON. Until T110 lands, the current placeholder dashboard
JSON fails this test because (a) its expressions use bare metric names without
the `collectmind_` namespace prefix that `metrics.py` declares, and (b) it omits
the retry-rate and runtime-image-digest panels.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DASHBOARD_PATH = (
    Path(__file__).resolve().parents[2] / "observability" / "grafana" / "dashboards" / "collectmind-end-to-end.json"
)

MAX_REFRESH_SECONDS = 10  # SC-006 / FR-015

# Canonical panel title substrings (case-insensitive). One entry per panel
# mandated by FR-014 + the T110 panel list. Substring match keeps the test
# robust to minor cosmetic title edits while still pinning the panel set.
REQUIRED_PANEL_TITLES: tuple[str, ...] = (
    "ingest rate",
    "generation funnel",
    "validation pass rate",
    "time-to-deploy",
    "hypothesis confirmation rate",
    "dead-letter count",
    "retry rate",
    "authentication-failure",
    "slm generation latency",
    "slm constraint-violation",
    "active slm weight sha",
    "active slm runtime image digest",
)


_METRIC_TOKEN = re.compile(r"\b[a-z][a-z0-9_]*\b")


def _parse_refresh_to_seconds(raw: object) -> int:
    """Parse a Grafana refresh string ('10s', '1m') into seconds.

    Returns a sentinel of 10**9 for unrecognized values so the assertion fails
    explicitly rather than silently passing on a malformed entry.
    """
    if not isinstance(raw, str):
        return 10**9
    match = re.fullmatch(r"(\d+)\s*([smh])", raw.strip())
    if not match:
        return 10**9
    value, unit = int(match.group(1)), match.group(2)
    multiplier = {"s": 1, "m": 60, "h": 3600}[unit]
    return value * multiplier


def _declared_metric_names() -> set[str]:
    """Return the set of fully qualified Prometheus metric names declared by
    `src/collectmind/observability/metrics.py`.

    `prometheus_client` strips the `_total` suffix from Counter names at
    registration time (so a Counter declared as ``foo_total`` exposes a series
    named ``foo_total`` but has ``_name = "foo"`` on the instance). To keep the
    contract robust to all three primitive kinds (Counter / Gauge / Histogram)
    the set includes every derived suffix Prometheus may emit: ``_total``,
    ``_created``, ``_bucket``, ``_sum``, ``_count``."""
    from collectmind.observability import metrics  # local import to avoid module-load coupling at collection

    declared: set[str] = set()
    for name in dir(metrics):
        attr = getattr(metrics, name)
        prom_name = getattr(attr, "_name", None)
        if not isinstance(prom_name, str) or not prom_name.startswith("collectmind_"):
            continue
        declared.add(prom_name)
        for suffix in ("_total", "_created", "_bucket", "_sum", "_count"):
            declared.add(f"{prom_name}{suffix}")
    return declared


def _expressions(doc: dict) -> list[tuple[int, str, str]]:
    """Yield (panel_id, panel_title, expr) tuples for every PromQL expression."""
    out: list[tuple[int, str, str]] = []
    for panel in doc.get("panels", []):
        panel_id = int(panel.get("id", -1))
        title = str(panel.get("title", ""))
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if isinstance(expr, str):
                out.append((panel_id, title, expr))
    return out


def _collectmind_tokens(expr: str) -> set[str]:
    return {tok for tok in _METRIC_TOKEN.findall(expr) if tok.startswith("collectmind_")}


@pytest.fixture(scope="module")
def dashboard_doc() -> dict:
    assert DASHBOARD_PATH.is_file(), f"dashboard JSON missing at {DASHBOARD_PATH}"
    return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))


def test_dashboard_json_is_well_formed(dashboard_doc: dict) -> None:
    assert isinstance(dashboard_doc.get("panels"), list)
    assert dashboard_doc["panels"], "dashboard must declare at least one panel"


def test_refresh_interval_meets_sc006(dashboard_doc: dict) -> None:
    refresh = dashboard_doc.get("refresh")
    seconds = _parse_refresh_to_seconds(refresh)
    assert seconds <= MAX_REFRESH_SECONDS, (
        f"refresh interval {refresh!r} ({seconds}s) exceeds SC-006 ceiling of {MAX_REFRESH_SECONDS}s (FR-015)"
    )


def test_every_expr_references_a_declared_metric(dashboard_doc: dict) -> None:
    """Positive: every panel target's PromQL must reference at least one
    fully qualified `collectmind_`-prefixed metric. A panel whose expression
    uses bare names (e.g. `diagnostic_findings_received_total` without the
    `collectmind_` prefix) silently scrapes nothing in production; this assertion
    catches that drift at PR time."""
    declared = _declared_metric_names()
    assert declared, "metrics.py declared no collectmind_-prefixed metrics"

    misses: list[str] = []
    for panel_id, title, expr in _expressions(dashboard_doc):
        refs = _collectmind_tokens(expr)
        if not refs:
            misses.append(f"panel {panel_id} ({title!r}) expr {expr!r} references no collectmind_ metric")
        else:
            undeclared = refs - declared
            if undeclared:
                misses.append(f"panel {panel_id} ({title!r}) references undeclared metric(s) {sorted(undeclared)}")
    assert not misses, "dashboard-metrics drift:\n  - " + "\n  - ".join(misses)


def test_dashboard_contains_required_panels(dashboard_doc: dict) -> None:
    """Asserts the panel set mandated by FR-014 and T110.

    Each entry in REQUIRED_PANEL_TITLES must match (case-insensitive substring)
    at least one panel title in the dashboard."""
    titles = [str(p.get("title", "")).lower() for p in dashboard_doc.get("panels", [])]
    missing: list[str] = []
    for required in REQUIRED_PANEL_TITLES:
        if not any(required in title for title in titles):
            missing.append(required)
    assert not missing, (
        f"dashboard missing required panel titles (FR-014 / T110): {missing}; dashboard panel titles present: {titles}"
    )


def test_time_to_deploy_panel_exposes_p50_p95_p99(dashboard_doc: dict) -> None:
    """The time-to-deploy panel MUST expose the three SC-001 quantile series
    (p50, p95, p99) so the on-call surface matches the SLO contract."""
    panel = next(
        (p for p in dashboard_doc.get("panels", []) if "time-to-deploy" in str(p.get("title", "")).lower()),
        None,
    )
    assert panel is not None, "time-to-deploy panel missing"
    exprs = " ".join(t.get("expr", "") for t in panel.get("targets", []))
    for quantile in ("0.5", "0.95", "0.99"):
        assert quantile in exprs, f"time-to-deploy panel missing quantile {quantile}"

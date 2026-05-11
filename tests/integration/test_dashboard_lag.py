"""T108: dashboard reflects pipeline state with at most 10s of lag from event
acceptance.

Asserts US2 Acceptance Scenario 1 / SC-006 / FR-015: after a finding is
accepted, the metrics that drive the operator dashboard reflect the event
within 10 seconds. The dashboard pulls from Prometheus, so the operative
bottleneck is the Prometheus scrape interval plus any in-process emission
delay. This test measures Prometheus-side visibility as a lower bound on the
dashboard's lag.

Mechanics:

1. Snapshot the current counter value (`collectmind_diagnostic_findings_received_total`)
   for the default tenant via the Prometheus instant-query API at `/api/v1/query`.
2. Publish one brake-wear finding through the orchestration API.
3. Poll the same query at a tight cadence until the counter increases by 1.
4. Assert the wall-clock delta from step 2 to the visible increase is at most
   `DASHBOARD_LAG_BUDGET_SECONDS` (SC-006: 10 s).

Additionally pins SC-006 for the SLM panels: after the policy is generated,
`collectmind_slm_runtime_image_digest_active` MUST be visible with the active
runtime label inside the same budget (so the on-call surface for "is the SLM
the model we think it is" is not stale).

Per FR-021 / Principle IV this test exists before T114 (metrics emission
additions) and the T110 dashboard panel set land, and before T115 may need to
tighten `infra/compose/prometheus.yml`'s 15 s scrape interval to meet the 10 s
ceiling. Until those land, the test fails: the ingest counter does not become
visible inside 10 s under a 15 s scrape interval. That is the red signal.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

from tests.conftest import (
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    MOCK_ISSUER_URL,
    ORCHESTRATION_BASE_URL,
    require_local_stack,
)


pytestmark = pytest.mark.integration


PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DASHBOARD_LAG_BUDGET_SECONDS = 10.0  # SC-006 / FR-015
POLL_INTERVAL_SECONDS = 0.5


def _require_prometheus() -> None:
    try:
        httpx.get(f"{PROMETHEUS_URL}/-/ready", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(f"Prometheus not reachable at {PROMETHEUS_URL}; bring the stack up")


def _mint() -> str:
    response = httpx.post(
        f"{MOCK_ISSUER_URL}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": DEFAULT_TENANT,
            "client_secret": DEFAULT_CLIENT_SECRET,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _instant_query(expr: str) -> float | None:
    """Run a Prometheus instant query and return the scalar value, or None if
    the result is empty."""
    response = httpx.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": expr},
        timeout=5.0,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "success":
        return None
    result = body.get("data", {}).get("result", [])
    if not result:
        return None
    # Take the first series and return its instant value.
    value = result[0].get("value")
    if not value or len(value) != 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _publish_finding(finding_id: str, token: str) -> httpx.Response:
    return httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": finding_id,
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursion correlation",
            "candidate_signals": [
                "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
                "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
            ],
            "vehicle_scope": ["VIN-D-LAG-1"],
            "upstream_confidence": 0.78,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def _wait_for_counter_increase(expr: str, baseline: float, budget_seconds: float) -> tuple[float, float]:
    """Poll `expr` until its scalar value strictly exceeds `baseline`.

    Returns (final_value, elapsed_seconds). Raises AssertionError on timeout.
    """
    start = time.monotonic()
    deadline = start + budget_seconds
    while time.monotonic() < deadline:
        value = _instant_query(expr)
        if value is not None and value > baseline:
            return value, time.monotonic() - start
        time.sleep(POLL_INTERVAL_SECONDS)
    final = _instant_query(expr)
    raise AssertionError(
        f"counter {expr!r} did not increase from baseline {baseline} within "
        f"{budget_seconds}s; last observed value: {final}"
    )


def test_ingest_counter_visible_within_sc006_budget() -> None:
    require_local_stack()
    _require_prometheus()
    token = _mint()
    finding_id = f"F-lag-{uuid.uuid4().hex[:8]}"

    expr = f'sum(collectmind_diagnostic_findings_received_total{{tenant_id="{DEFAULT_TENANT}"}})'
    baseline = _instant_query(expr) or 0.0

    response = _publish_finding(finding_id, token)
    assert response.status_code == 202, response.text

    final, elapsed = _wait_for_counter_increase(expr, baseline, DASHBOARD_LAG_BUDGET_SECONDS)
    assert elapsed <= DASHBOARD_LAG_BUDGET_SECONDS, (
        f"SC-006 breach: ingest counter took {elapsed:.2f}s to become visible "
        f"(budget {DASHBOARD_LAG_BUDGET_SECONDS}s); final value {final}"
    )


def test_slm_runtime_image_digest_visible_within_sc006_budget() -> None:
    """The dashboard's 'active SLM runtime image digest' panel reads from
    `collectmind_slm_runtime_image_digest_active`. After a finding triggers a
    policy generation, this gauge MUST carry a non-empty label set inside the
    SC-006 budget so the on-call sees the active runtime within the dashboard's
    refresh window. T114 wires the emission point."""
    require_local_stack()
    _require_prometheus()
    token = _mint()
    finding_id = f"F-lag-rt-{uuid.uuid4().hex[:8]}"

    response = _publish_finding(finding_id, token)
    assert response.status_code == 202, response.text

    expr = "sum(collectmind_slm_runtime_image_digest_active) by (digest, runtime)"
    deadline = time.monotonic() + DASHBOARD_LAG_BUDGET_SECONDS
    seen = False
    while time.monotonic() < deadline:
        payload = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": expr},
            timeout=5.0,
        ).json()
        result = payload.get("data", {}).get("result", [])
        if any(item.get("metric", {}).get("digest") for item in result):
            seen = True
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    assert seen, (
        f"SC-006 breach: runtime image digest gauge had no labeled samples within "
        f"{DASHBOARD_LAG_BUDGET_SECONDS}s of publishing finding {finding_id}"
    )

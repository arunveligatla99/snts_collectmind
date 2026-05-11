"""T107: SLO breach simulation triggers an alert whose webhook payload carries
the runbook URL.

Asserts US2 Acceptance Scenario 2 of `spec.md`: when an end-to-end latency
breach occurs, an alert fires within one minute, names the breached metric,
and links to the runbook page that describes the failure.

Implementation strategy:

1. Bring up Alertmanager + a local webhook receiver via `docker compose` (the
   T115 task adds both to the Compose stack and the receiver to
   `scripts/local_webhook.py`).
2. Post a synthetic alert directly to Alertmanager's `/api/v2/alerts` endpoint
   to deterministically drive the routing path without having to push a metric
   above an SLO threshold and wait for `evaluation_interval` * N rule scrapes.
   The shape of the alert is the same one Prometheus would post (`labels`
   include `alertname`, `severity`, an SC tag; `annotations` include
   `runbook_url` and `summary`), so the routing-through-webhook assertion is
   end-to-end accurate.
3. Poll the local webhook receiver's HTTP surface for the captured payload.
4. Assert the captured payload contains the alert with its `runbook_url`
   annotation intact.

Until T115 lands Alertmanager + local_webhook in Compose this test is skipped
when those endpoints are unreachable. That is the canonical red-phase signal.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration


ALERTMANAGER_URL = os.environ.get("ALERTMANAGER_URL", "http://localhost:9093")
LOCAL_WEBHOOK_URL = os.environ.get("LOCAL_WEBHOOK_URL", "http://localhost:9099")

ALERT_DEADLINE_SECONDS = 60.0  # US2 AS2: alert fires within one minute
POLL_INTERVAL_SECONDS = 1.0


def _require_alertmanager() -> None:
    try:
        httpx.get(f"{ALERTMANAGER_URL}/-/ready", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(
            f"Alertmanager not reachable at {ALERTMANAGER_URL}; T115 must add it to "
            f"infra/compose/docker-compose.yaml + infra/compose/alertmanager.yaml"
        )


def _require_local_webhook() -> None:
    try:
        httpx.get(f"{LOCAL_WEBHOOK_URL}/healthz", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(
            f"local webhook receiver not reachable at {LOCAL_WEBHOOK_URL}; T115 must "
            f"start scripts/local_webhook.py and expose /healthz + /captured"
        )


def _drain_captured() -> list[dict]:
    """Drain captured alerts from the local webhook. Returns the list of alert
    dicts the receiver has seen since its last drain."""
    response = httpx.delete(f"{LOCAL_WEBHOOK_URL}/captured", timeout=5.0)
    response.raise_for_status()
    return response.json()


def _post_synthetic_alert(*, alertname: str, slo_tag: str, runbook_url: str) -> None:
    """Post a synthetic alert to Alertmanager. Format matches Prometheus's own
    POST shape on `/api/v2/alerts` so the routing path is identical."""
    now = time.gmtime()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", now)
    payload = [
        {
            "labels": {
                "alertname": alertname,
                "severity": "page",
                "slo": slo_tag,
                "service": "collectmind",
                "test_marker": "t107",
            },
            "annotations": {
                "summary": f"synthetic {alertname} breach for T107",
                "description": f"SLO {slo_tag} breached (synthetic)",
                "runbook_url": runbook_url,
            },
            "startsAt": timestamp,
        }
    ]
    response = httpx.post(f"{ALERTMANAGER_URL}/api/v2/alerts", json=payload, timeout=10.0)
    response.raise_for_status()


def _wait_for_capture(alertname: str, deadline_seconds: float) -> dict:
    """Poll the webhook receiver until the named alert appears or the deadline
    elapses. Returns the first matching alert dict."""
    end = time.time() + deadline_seconds
    while time.time() < end:
        captured = _drain_captured()
        for envelope in captured:
            # Alertmanager webhook envelope contains a top-level "alerts" array.
            for alert in envelope.get("alerts", []):
                if alert.get("labels", {}).get("alertname") == alertname:
                    return alert
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"webhook did not receive alert {alertname!r} within {deadline_seconds}s (US2 AS2 deadline)")


def test_slo_breach_alert_reaches_webhook_with_runbook_url() -> None:
    _require_alertmanager()
    _require_local_webhook()

    # Drain anything left from a prior run so we measure only this run's alert.
    _drain_captured()

    alertname = f"E2ELatencyBreach-{uuid.uuid4().hex[:8]}"
    runbook_url = "http://runbooks.local/observability/runbooks/slo-001-latency.md"

    _post_synthetic_alert(alertname=alertname, slo_tag="SC-001", runbook_url=runbook_url)

    captured = _wait_for_capture(alertname, ALERT_DEADLINE_SECONDS)

    # US2 AS2: the alert names the breached metric (via the slo label) and links
    # to a runbook page (via the runbook_url annotation).
    assert captured["labels"]["slo"] == "SC-001"
    assert captured["annotations"]["runbook_url"] == runbook_url
    assert "summary" in captured["annotations"]
    assert captured["annotations"]["summary"]

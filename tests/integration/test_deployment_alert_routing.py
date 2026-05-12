"""T273: SC-012 deployment-tenant-mismatch alert routing integration test (Phase 12 US4).

Asserts the SC-012 contract: a page-tier alert for a Fatal tenant-vehicle deployment
mismatch reaches the local webhook receiver within 60 seconds and the captured payload
links to the deployment-tenant-mismatch runbook page.

Mechanism (mirrors the feature-001 T107 alert-routing harness): post a synthetic
``DeploymentTenantMismatch`` alert directly to Alertmanager's ``/api/v2/alerts``,
deterministically driving the routing path without depending on the Phase 13 rules.yaml
addition (T280) that fires this alert from a real metric scrape. SC-012's binding contract
is the wall-clock routing budget plus the runbook-URL annotation, not the rule's
existence; T279's verification gate cannot wait for Phase 13.

Red-phase signal: T278 (the ``deployment-tenant-mismatch.md`` runbook page) has not
landed. The final assertion (the runbook file MUST exist on disk per Principle VIII +
FR-024) fails with a clear "T278 has not landed" message. Once T278 ships the file, the
test passes against the existing Alertmanager + webhook receiver (already in Compose from
feature-001 T115).

Anchors: SC-012 / FR-024 / Principle V / Principle VIII / Principle IV.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

ALERTMANAGER_URL = os.environ.get("ALERTMANAGER_URL", "http://localhost:9093")
LOCAL_WEBHOOK_URL = os.environ.get("LOCAL_WEBHOOK_URL", "http://localhost:9099")

ALERT_DEADLINE_SECONDS = 60.0  # SC-012: alert routing within 60 s
POLL_INTERVAL_SECONDS = 1.0

# Repo-root anchored so the test resolves correctly regardless of pytest cwd.
RUNBOOK_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "observability"
    / "runbooks"
    / "deployment-tenant-mismatch.md"
)


def _require_alertmanager() -> None:
    try:
        httpx.get(f"{ALERTMANAGER_URL}/-/ready", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(
            f"Alertmanager not reachable at {ALERTMANAGER_URL}; "
            f"start `docker compose -f infra/compose/docker-compose.yaml up -d alertmanager`"
        )


def _require_local_webhook() -> None:
    try:
        httpx.get(f"{LOCAL_WEBHOOK_URL}/healthz", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(
            f"local webhook receiver not reachable at {LOCAL_WEBHOOK_URL}; "
            f"start `scripts/local_webhook.py` per feature-001 T115"
        )


def _drain_captured() -> list[dict[str, Any]]:
    response = httpx.delete(f"{LOCAL_WEBHOOK_URL}/captured", timeout=5.0)
    response.raise_for_status()
    return list(response.json())


def _post_synthetic_deployment_mismatch_alert(unique_tag: str, runbook_url: str) -> str:
    """Post a synthetic ``DeploymentTenantMismatch`` alert to Alertmanager.

    Shape matches Prometheus's own POST envelope on ``/api/v2/alerts`` so the routing path
    is identical to a real rule-firing path.
    """
    now = time.gmtime()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", now)
    alertname = f"DeploymentTenantMismatch-{unique_tag}"
    payload = [
        {
            "labels": {
                "alertname": alertname,
                "severity": "page",
                "slo": "SC-012",
                "service": "collectmind",
                "tenant_id": "tenant-a",
                "test_marker": "t273",
            },
            "annotations": {
                "summary": "deployment refused: policy.tenant_id != vehicle owning tenant",
                "description": (
                    "Fatal TenantVehicleMismatch raised at deployer node "
                    "(FR-022 / ADR-0009 Part 6)"
                ),
                "runbook_url": runbook_url,
            },
            "startsAt": timestamp,
        }
    ]
    response = httpx.post(
        f"{ALERTMANAGER_URL}/api/v2/alerts", json=payload, timeout=10.0
    )
    response.raise_for_status()
    return alertname


def _wait_for_capture(alertname: str, deadline_seconds: float) -> dict[str, Any]:
    end = time.time() + deadline_seconds
    while time.time() < end:
        for envelope in _drain_captured():
            for alert in envelope.get("alerts", []):
                if alert.get("labels", {}).get("alertname") == alertname:
                    return alert
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"webhook did not receive alert {alertname!r} within {deadline_seconds}s "
        f"(SC-012 deadline)"
    )


def test_deployment_tenant_mismatch_alert_reaches_webhook_with_runbook() -> None:
    """SC-012: page-tier alert routes to the webhook within 60 s with the runbook URL.

    Three load-bearing assertions:
      - the captured alert's severity is ``page`` (FR-024 / page-tier),
      - the captured alert's ``slo`` label is ``SC-012`` (SLO anchoring per Principle XI),
      - the captured alert's ``runbook_url`` annotation matches the posted value AND
        the runbook page exists on disk (the T278 red signal).
    """
    _require_alertmanager()
    _require_local_webhook()
    _drain_captured()  # discard stragglers from prior runs so we measure only this run

    unique_tag = uuid.uuid4().hex[:8]
    # The path is what Phase 12 documents in the orchestration-api's alert label.
    runbook_url = (
        "http://runbooks.local/observability/runbooks/deployment-tenant-mismatch.md"
    )
    alertname = _post_synthetic_deployment_mismatch_alert(unique_tag, runbook_url)

    captured = _wait_for_capture(alertname, ALERT_DEADLINE_SECONDS)

    # SC-012 / FR-024 contract carried by every fired alert.
    assert captured["labels"]["severity"] == "page", (
        f"FR-024 violation: alert severity not 'page'; got {captured['labels']!r}"
    )
    assert captured["labels"]["slo"] == "SC-012", (
        f"Principle XI violation: alert missing SC-012 SLO tag; "
        f"got {captured['labels']!r}"
    )
    assert captured["annotations"]["runbook_url"] == runbook_url, (
        f"FR-024 violation: runbook_url annotation not preserved through routing; "
        f"got {captured['annotations']!r}"
    )

    # T278: the runbook file MUST exist on disk. This is the canonical red signal until
    # Phase 12.b lands the runbook page (FR-024 / Principle VIII — "alert MUST link to a
    # runbook page that describes the cause and the response").
    assert RUNBOOK_PATH.is_file(), (
        f"T278 has not landed: runbook page missing at {RUNBOOK_PATH}. "
        f"Phase 12 cannot close without the runbook (FR-024 / Principle VIII)."
    )

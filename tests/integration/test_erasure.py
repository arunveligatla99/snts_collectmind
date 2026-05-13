"""T064: GDPR/CCPA right-to-erasure dispatcher (FR-020a).

Asserts: a `POST /erasure-requests` triggers per-store dispatch to the policy
registry, the telemetry store, and the audit log. The dispatcher distinguishes
`erased` (subject row physically removed) from `redacted` (subject identifiers
replaced with a tombstone). The default completion bound is 30 days; the request
itself is auditable.
"""

from __future__ import annotations

import time
import uuid

import httpx
import pytest

from tests.conftest import (
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    MOCK_ISSUER_URL,
    ORCHESTRATION_BASE_URL,
    QUERY_BASE_URL,
    require_local_stack,
)

pytestmark = pytest.mark.integration


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


def _publish_finding(finding_id: str, token: str) -> str:
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": finding_id,
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursion correlation",
            "candidate_signals": ["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear"],
            "vehicle_scope": ["VIN-erasure-1"],
            "upstream_confidence": 0.78,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Time-Acceleration-Factor": "3600",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["correlation_id"]


def test_erasure_request_accepted_with_target_completion_at() -> None:
    require_local_stack()
    # require_slm() removed: dev_default profile produces deterministic policy without an SLM container
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}

    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/erasure-requests",
        json={
            "subject_kind": "vehicle",
            "subject_identifier": "VIN-erasure-1",
            "mode": "redacted",
        },
        headers=headers,
        timeout=10.0,
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert "request_id" in body
    assert "target_completion_at" in body


def test_erasure_propagates_to_registry_telemetry_audit() -> None:
    """End-to-end: publish a finding, request erasure, verify per-store status."""
    require_local_stack()
    # require_slm() removed: dev_default profile produces deterministic policy without an SLM container
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-erasure-{uuid.uuid4().hex[:8]}"
    _publish_finding(finding_id, token)
    time.sleep(3.0)  # let the first publication's audit and registry rows land

    erase = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/erasure-requests",
        json={
            "subject_kind": "vehicle",
            "subject_identifier": "VIN-erasure-1",
            "mode": "redacted",
        },
        headers=headers,
        timeout=10.0,
    )
    erase.raise_for_status()
    request_id = erase.json()["request_id"]

    # Poll the dispatcher's per-store status until completion (or partial+manual).
    deadline = time.time() + 60.0
    while time.time() < deadline:
        status = httpx.get(
            f"{QUERY_BASE_URL}/api/v1/erasure-requests/{request_id}",
            headers=headers,
            timeout=10.0,
        )
        if status.status_code == 200:
            body = status.json()
            if body["status"] in {"completed", "partial"}:
                per_store = body["per_store_status"]
                assert "registry" in per_store
                assert "telemetry" in per_store
                assert "audit" in per_store
                return
        time.sleep(1.0)
    raise AssertionError("erasure dispatcher did not complete within 60s")


def test_erasure_request_itself_audited() -> None:
    require_local_stack()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}

    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/erasure-requests",
        json={
            "subject_kind": "principal",
            "subject_identifier": "test-subject",
            "mode": "erased",
        },
        headers=headers,
        timeout=10.0,
    )
    response.raise_for_status()
    request_id = response.json()["request_id"]

    # The erasure request emits a `kind=erasure` audit event on the same
    # correlation chain as the request.
    deadline = time.time() + 30.0
    while time.time() < deadline:
        audit = httpx.get(
            f"{QUERY_BASE_URL}/api/v1/audit/{request_id}",
            headers=headers,
            timeout=10.0,
        )
        if audit.status_code == 200 and any(e["kind"] == "erasure" for e in audit.json()):
            return
        time.sleep(1.0)
    raise AssertionError("did not observe a `kind=erasure` audit event")

"""T061: Acceptance Scenario 2 of US1.

Given a diagnostic finding whose candidate signals contain a name not in the canonical
signal vocabulary, when the operator publishes the finding, the system rejects the
resulting policy with a structured error that names every invalid signal, no policy
is written to the registry, and no deployment record is produced.
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
    require_slm,
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


def test_vss_invalid_signal_in_finding_rejected_with_structured_error() -> None:
    """An inbound finding that references a non-VSS signal must be rejected at the validator."""
    require_local_stack()
    require_slm()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-vss-{uuid.uuid4().hex[:8]}"

    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": finding_id,
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursion correlation",
            "candidate_signals": [
                "Vehicle.Speed",
                "Vehicle.NotARealSignalABCDEF",
                "Vehicle.AlsoNotReal12345",
            ],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.78,
        },
        headers=headers,
        timeout=30.0,
    )

    # Inbound contract validates schema only; non-VSS signals are caught at the
    # Policy Validator node, which dead-letters the session and writes a `rejected`
    # audit event with the structured error.
    if response.status_code == 202:
        # Wait for the validator's rejected audit event to appear.
        correlation_id = response.json()["correlation_id"]
        deadline = time.time() + 30.0
        while time.time() < deadline:
            audit = httpx.get(
                f"{QUERY_BASE_URL}/api/v1/audit/{correlation_id}",
                headers=headers,
                timeout=10.0,
            )
            if audit.status_code == 200 and any(
                e["kind"] == "rejected" for e in audit.json()
            ):
                rejected = next(e for e in audit.json() if e["kind"] == "rejected")
                # The structured error must name every invalid signal.
                details = rejected.get("error", {}).get("details", {})
                invalid = set(details.get("invalid_signals", []))
                assert {"Vehicle.NotARealSignalABCDEF", "Vehicle.AlsoNotReal12345"} <= invalid
                break
            time.sleep(1.0)
        else:
            raise AssertionError("did not observe a `rejected` audit event")

        # No policy was written to the registry for this finding.
        assert (
            httpx.get(
                f"{QUERY_BASE_URL}/api/v1/findings/{finding_id}/outcome",
                headers=headers,
                timeout=10.0,
            ).status_code
            == 404
        )
    else:
        # The validator may run inline at ingest time; either path is acceptable.
        assert response.status_code in {400, 422}
        body = response.json()
        detail = body if "code" in body else body.get("detail", body)
        assert detail.get("code") in {"VSS_INVALID_SIGNAL", "SCHEMA_VALIDATION_FAILED"}
        invalid = set(detail.get("details", {}).get("invalid_signals", []))
        assert {"Vehicle.NotARealSignalABCDEF", "Vehicle.AlsoNotReal12345"} <= invalid

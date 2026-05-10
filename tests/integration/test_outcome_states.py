"""T062: Acceptance Scenarios 3 and 4 of US1.

Given a deployed policy, when the simulated collection window expires, the outcome
record is written with state `confirmed` (Scenario 3), `ruled_out` (Scenario 4), or
`no_data` (edge case) depending on the synthetic post-collection telemetry.

The synthetic telemetry generator is parameterized via headers in this test so each
scenario is independently driven from the same orchestration API.
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


def _publish_with_simulator_directive(directive: str, finding_id: str, token: str) -> str:
    """Publish a finding with a header that pins the telemetry simulator outcome."""
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": finding_id,
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursion correlation",
            "candidate_signals": ["Vehicle.Chassis.Brake.PadWear"],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.78,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Telemetry-Simulator-Directive": directive,
            "X-Time-Acceleration-Factor": "3600",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["correlation_id"]


def _wait_for_outcome(finding_id: str, headers: dict[str, str]) -> dict:
    deadline = time.time() + 60.0
    while time.time() < deadline:
        response = httpx.get(
            f"{QUERY_BASE_URL}/api/v1/findings/{finding_id}/outcome",
            headers=headers,
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
        time.sleep(1.0)
    raise AssertionError(f"timeout waiting for outcome of {finding_id}")


@pytest.mark.parametrize(
    "directive,expected",
    [
        ("confirm", "confirmed"),
        ("rule_out", "ruled_out"),
        ("starve", "no_data"),
    ],
)
def test_outcome_state_per_directive(directive: str, expected: str) -> None:
    require_local_stack()
    require_slm()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-{directive}-{uuid.uuid4().hex[:8]}"
    _publish_with_simulator_directive(directive, finding_id, token)
    outcome = _wait_for_outcome(finding_id, headers)
    assert outcome["hypothesis_state"] == expected
    assert outcome["originating_finding"]["finding_id"] == finding_id
    if expected == "no_data":
        assert outcome["signals_collected_count"] == 0
    else:
        assert outcome["signals_collected_count"] > 0

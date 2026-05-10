"""T060: end-to-end finding -> policy -> deployment -> outcome.

Asserts US1 Acceptance Scenarios 1 and 5: a published brake-wear finding produces a
policy record, a deployment record, and (after the simulated collection window
closes) an outcome record linked by lineage to the originating finding.

Runs against the real local stack via testcontainers-python (or against `docker
compose` if already running). The SLM container is brought up in CPU profile here
to keep CI cost bounded per Constitution Principle XIV.

Until the LangGraph composition (T084) and the feedback worker (T093) land, this
test fails because the orchestration API does not yet have a `POST /findings`
handler that runs the graph end to end. That is the test's red phase.
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
                "Vehicle.Chassis.Brake.PadWear",
                "Vehicle.Powertrain.CombustionEngine.EngineOilTemperature",
            ],
            "vehicle_scope": ["VIN-1", "VIN-2", "VIN-3"],
            "upstream_confidence": 0.78,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def _wait_for(url: str, headers: dict[str, str], deadline_seconds: float = 60.0) -> dict:
    end = time.time() + deadline_seconds
    while time.time() < end:
        response = httpx.get(url, headers=headers, timeout=10.0)
        if response.status_code == 200:
            return response.json()
        time.sleep(1.0)
    raise AssertionError(f"timeout waiting for {url}")


def test_finding_to_outcome_end_to_end() -> None:
    require_local_stack()
    require_slm()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-e2e-{uuid.uuid4().hex[:8]}"

    accepted = _publish_finding(finding_id, token)
    assert accepted.status_code == 202, accepted.text
    receipt = accepted.json()
    assert receipt["finding_id"] == finding_id
    assert receipt["tenant_id"] == DEFAULT_TENANT
    correlation_id = receipt["correlation_id"]

    outcome = _wait_for(
        f"{QUERY_BASE_URL}/api/v1/findings/{finding_id}/outcome",
        headers,
        deadline_seconds=60.0,
    )
    assert outcome["originating_finding"]["finding_id"] == finding_id
    assert outcome["originating_finding"]["tenant_id"] == DEFAULT_TENANT
    assert outcome["hypothesis_state"] in {"confirmed", "ruled_out", "no_data"}

    audit = httpx.get(
        f"{QUERY_BASE_URL}/api/v1/audit/{correlation_id}",
        headers=headers,
        timeout=10.0,
    )
    assert audit.status_code == 200
    events = audit.json()
    kinds = [e["kind"] for e in events]
    assert "accepted" in kinds and "generated" in kinds and "validated" in kinds and "deployed" in kinds

    # FR-017a: drill into the `generated` audit event and assert the audit-record
    # minimum field set. The corresponding fields on the `deployed` event MUST link
    # to a deployment record so lineage is recoverable end-to-end.
    generated = next(e for e in events if e["kind"] == "generated")
    assert generated["slm_repo"] == "Qwen/Qwen2.5-7B-Instruct"
    sha = generated["slm_revision_sha"]
    assert isinstance(sha, str) and len(sha) == 40
    assert generated["prompt_template_version"], "prompt_template_version must be non-empty"
    assert isinstance(generated["slm_decoding_seed"], int)
    assert generated["policy_ref"] is not None
    assert {"tenant_id", "policy_id", "version"} <= set(generated["policy_ref"].keys())

    deployed = next(e for e in events if e["kind"] == "deployed")
    assert deployed["deployment_ref"] is not None
    assert "deployment_id" in deployed["deployment_ref"]


def test_query_active_policy_after_publication() -> None:
    """Acceptance Scenario 5: query returns active version, history, outcome."""
    require_local_stack()
    require_slm()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-q-{uuid.uuid4().hex[:8]}"
    _publish_finding(finding_id, token).raise_for_status()

    # The active policy for the vehicle group implied by the finding is reachable.
    active = _wait_for(
        f"{QUERY_BASE_URL}/api/v1/vehicle-groups/VIN-1/active-policy",
        headers,
        deadline_seconds=30.0,
    )
    assert active["originating_finding"]["finding_id"] == finding_id

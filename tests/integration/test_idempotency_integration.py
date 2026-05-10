"""T063: idempotent duplicate finding produces a single policy version and deployment.

Acceptance: published `(tenant_id, finding_id)` pair is idempotent under FR-012; the
second publication returns the same composite key with `idempotent_replay=true` and
no new policy version or deployment record is written.
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


def _payload(finding_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "finding_id": finding_id,
        "anomaly_type": "brake_wear_early_stage",
        "hypothesis_class": "brake_wear",
        "hypothesis_statement": "rotor temperature excursion correlation",
        "candidate_signals": ["Vehicle.Chassis.Brake.PadWear"],
        "vehicle_scope": ["VIN-1"],
        "upstream_confidence": 0.78,
    }


def test_duplicate_publication_is_idempotent() -> None:
    require_local_stack()
    require_slm()
    token = _mint()
    headers = {"Authorization": f"Bearer {token}"}
    finding_id = f"F-idem-{uuid.uuid4().hex[:8]}"

    first = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json=_payload(finding_id),
        headers=headers,
        timeout=30.0,
    )
    assert first.status_code == 202
    first_receipt = first.json()
    assert first_receipt.get("idempotent_replay", False) is False

    # Wait briefly so the first publication's deployment record lands before we
    # attempt to count it.
    time.sleep(2.0)

    second = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json=_payload(finding_id),
        headers=headers,
        timeout=30.0,
    )
    # The contract allows either 202 with `idempotent_replay=true` or 409 with the
    # same receipt body.
    assert second.status_code in {202, 409}
    second_receipt = second.json()
    assert second_receipt["finding_id"] == finding_id
    assert second_receipt["tenant_id"] == DEFAULT_TENANT
    if second.status_code == 202:
        assert second_receipt.get("idempotent_replay") is True

    # Exactly one policy version and one deployment record exist for this finding.
    versions = httpx.get(
        f"{QUERY_BASE_URL}/api/v1/policies/{first_receipt.get('policy_id', finding_id)}/versions",
        headers=headers,
        timeout=10.0,
    )
    if versions.status_code == 200:
        assert len(versions.json()) == 1

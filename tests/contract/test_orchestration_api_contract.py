"""T048: Contract test for orchestration-api.v1.yaml.

Asserts that the running orchestration API conforms to the OpenAPI 3.1 contract at
`contracts/openapi/orchestration-api.v1.yaml`. Uses schemathesis to drive request
generation against the contract; explicitly exercises the 202/400/401/409/422 paths.

Per FR-021 (test-first per Principle IV) this test exists before the `POST /findings`
handler (T094) and the idempotency check (T095) are implemented. Until those land,
the live API will return 404 and the schemathesis run will report contract drift
between the live API and the contract — which is the test's signal.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import schemathesis

from tests.conftest import DEFAULT_CLIENT_SECRET, DEFAULT_TENANT, MOCK_ISSUER_URL, ORCHESTRATION_BASE_URL

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "orchestration-api.v1.yaml"


def _mint_token() -> str:
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


schema = schemathesis.from_path(
    str(CONTRACT_PATH),
    base_url=f"{ORCHESTRATION_BASE_URL}/api/v1",
    force_schema_version="30",
)


@schema.parametrize(endpoint="/findings", method="POST")
def test_post_findings_conforms_to_contract(case: schemathesis.Case) -> None:
    """Generated POST /findings requests must produce contract-conformant responses."""
    case.headers = case.headers or {}
    case.headers["Authorization"] = f"Bearer {_mint_token()}"
    response = case.call()
    case.validate_response(response)


@schema.parametrize(endpoint="/health", method="GET")
def test_get_health_conforms(case: schemathesis.Case) -> None:
    response = case.call()
    case.validate_response(response)


@schema.parametrize(endpoint="/ready", method="GET")
def test_get_ready_conforms(case: schemathesis.Case) -> None:
    response = case.call()
    case.validate_response(response)


def test_post_findings_rejects_missing_token() -> None:
    """FR-002: inbound event without bearer token must be rejected with 401."""
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": "auth-test",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "test",
            "candidate_signals": ["Vehicle.Speed"],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.5,
        },
        timeout=10.0,
    )
    assert response.status_code == 401
    body = response.json()
    detail = body if "code" in body else body.get("detail", body)
    # Feature 002 added the rate-limit middleware ahead of the FastAPI auth dep
    # in the request chain; the middleware does its own minimal token check and
    # returns code="UNAUTHENTICATED" for a missing bearer (see
    # src/collectmind/ratelimit/middleware.py). The downstream auth dep returns
    # AUTH_INVALID_TOKEN / AUTH_TENANT_MISSING (errors.py). Accept any of the
    # three so the contract remains stable across the chain ordering.
    assert detail.get("code") in {"AUTH_INVALID_TOKEN", "AUTH_TENANT_MISSING", "UNAUTHENTICATED"}


def test_post_findings_rejects_unsupported_schema_major() -> None:
    """FR-003a: unsupported schema_version major must be rejected with 422."""
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "2.0.0",
            "finding_id": "schema-major-test",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "test",
            "candidate_signals": ["Vehicle.Speed"],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.5,
        },
        headers={"Authorization": f"Bearer {_mint_token()}"},
        timeout=10.0,
    )
    assert response.status_code == 422
    body = response.json()
    detail = body if "code" in body else body.get("detail", body)
    assert detail.get("code") == "SCHEMA_VERSION_UNSUPPORTED"


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_unauthenticated_endpoints_open(path: str) -> None:
    """FR-018: /health and /ready are explicitly exempt from authentication."""
    response = httpx.get(f"{ORCHESTRATION_BASE_URL}{path}", timeout=10.0)
    assert response.status_code in {200, 503}

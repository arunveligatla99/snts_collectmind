"""T049: Contract test for query-api.v1.yaml.

Asserts conformance for getPolicyById, listPolicyVersions, getActivePolicyForGroup,
getOutcomeForFinding, getAuditTrail. Exercises the 404 path explicitly.

Until T098 (`src/collectmind/query/api.py`) lands, these endpoints do not exist; the
schemathesis run reports drift, and the explicit 404 tests fail. That is the test's
red phase per Principle IV.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import schemathesis

from tests.conftest import QUERY_BASE_URL, MOCK_ISSUER_URL, DEFAULT_TENANT, DEFAULT_CLIENT_SECRET


CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "query-api.v1.yaml"
)


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


schema = schemathesis.from_path(str(CONTRACT_PATH), base_url=QUERY_BASE_URL)


@schema.parametrize()
def test_query_api_conforms_to_contract(case: schemathesis.Case) -> None:
    case.headers = case.headers or {}
    case.headers["Authorization"] = f"Bearer {_mint_token()}"
    response = case.call()
    case.validate_response(response)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/policies/does-not-exist",
        "/api/v1/policies/does-not-exist/versions",
        "/api/v1/vehicle-groups/does-not-exist/active-policy",
        "/api/v1/findings/does-not-exist/outcome",
        "/api/v1/audit/does-not-exist",
    ],
)
def test_unknown_identifier_returns_structured_not_found(path: str) -> None:
    """FR-011: unknown identifier returns structured `NOT_FOUND`, never empty success."""
    response = httpx.get(
        f"{QUERY_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {_mint_token()}"},
        timeout=10.0,
    )
    assert response.status_code == 404
    body = response.json()
    detail = body if "code" in body else body.get("detail", body)
    assert detail.get("code") == "NOT_FOUND"
    assert "identifier" in (detail.get("details") or {})


def test_query_endpoints_require_authentication() -> None:
    """FR-018: every query endpoint requires a JWT."""
    response = httpx.get(f"{QUERY_BASE_URL}/api/v1/policies/anything", timeout=10.0)
    assert response.status_code == 401

"""T223: ``GET /api/v1/tenant-config/self`` contract test.

Asserts FR-013 / FR-013a contract:
    - Tenant JWT returns the requesting tenant's effective rate-limit configuration
    - Source field is either ``default`` (no row in tenant_config) or ``override``
    - Tenant cannot read another tenant's row (response shape never carries another tenant's id)
    - Missing/invalid JWT → 401

Red phase: endpoint not registered until Phase 9.b T241. FastAPI returns 404.

Anchors: FR-013 / FR-013a / Principle IV.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    QUERY_BASE_URL,
    TENANT_A,
    mint_tenant_token,
    require_local_stack,
)

pytestmark = pytest.mark.contract

PATH = "/api/v1/tenant-config/self"


def test_tenant_jwt_returns_own_config() -> None:
    require_local_stack()
    token = mint_tenant_token(TENANT_A)
    response = httpx.get(
        f"{QUERY_BASE_URL}{PATH}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
    )
    assert response.status_code == 200, f"got {response.status_code} from {PATH}"
    payload = response.json()
    # Schema per query-api-v1.1.0.delta.yaml §TenantConfig.
    assert payload["tenant_id"] == TENANT_A
    assert payload["source"] in {"default", "override"}
    for bucket_key in ("inbound", "query"):
        assert bucket_key in payload
        bucket = payload[bucket_key]
        assert isinstance(bucket["sustained_rps"], int) and bucket["sustained_rps"] > 0
        assert isinstance(bucket["burst_capacity"], int)
        assert bucket["burst_capacity"] >= bucket["sustained_rps"]


def test_default_values_match_fr012_anchors() -> None:
    """When no override row exists, the response carries FR-012 default values."""
    require_local_stack()
    token = mint_tenant_token(TENANT_A)
    response = httpx.get(
        f"{QUERY_BASE_URL}{PATH}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
    )
    if response.status_code != 200:
        pytest.fail(f"endpoint returned {response.status_code}; cannot assert FR-012 defaults")
    payload = response.json()
    if payload.get("source") == "default":
        assert payload["inbound"]["sustained_rps"] == 2000, "FR-012 inbound sustained default"
        assert payload["inbound"]["burst_capacity"] == 4000, "FR-012 inbound burst default"
        assert payload["query"]["sustained_rps"] == 200, "FR-012 query sustained default"
        assert payload["query"]["burst_capacity"] == 400, "FR-012 query burst default"


def test_missing_token_returns_401() -> None:
    require_local_stack()
    response = httpx.get(f"{QUERY_BASE_URL}{PATH}", timeout=5.0)
    assert response.status_code == 401

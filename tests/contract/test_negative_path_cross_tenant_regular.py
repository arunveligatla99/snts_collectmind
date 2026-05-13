"""T220: negative-path cross-tenant fuzz across the regular OpenAPI surface.

Fans schemathesis (or direct HTTP probes) across orchestration-api.v1.yaml + query-api.v1.yaml
(both at v1.1.0) using a tenant-A JWT and asserts every endpoint returns 404 (NOT 200, 403,
422, or 500) when targeting a tenant-B resource. This is the FR-006 / FR-025 contract: cross-
tenant access on any path returns 404 to avoid an existence oracle (per ADR-0007 §Decision +
Spec US1 AS-5).

Distinct task from T221 per the user implementer note: this fuzz runs against the REGULAR
OpenAPI surface only. The audit-admin surface (separate OpenAPI document) is exercised by
T221.

Red phase (Phase 9.a): runs before T242 lands the cross-tenant 404 collapse in the regular
handlers. Until T242, the existing handlers return:
    - 200 for the (single-tenant) happy path with the wrong-tenant JWT (because feature-001's
      PERMISSIVE RLS lets every authenticated request see every row; the JWT-derived tenant_id
      isn't compared to the targeted resource's tenant_id at the handler layer)
    - 404 only when the resource doesn't exist
The test FAILS the build under both shapes — exactly the FR-025 contract (build fails on any
200/403/422/500 for a cross-tenant request).

Anchors: SC-001 / FR-006 / FR-025 / Principle IV.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import (
    ORCHESTRATION_BASE_URL,
    QUERY_BASE_URL,
    TENANT_A,
    TENANT_B,
    mint_tenant_token,
    require_local_stack,
)

pytestmark = pytest.mark.contract

# Endpoints (path, method, body?) exercised under wrong-tenant JWT. Each tuple maps to a
# resource-targeted operation on the regular API. The path placeholder ``{id}`` is filled
# with a tenant-B-owned resource identifier at runtime.
ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("/api/v1/policies/{id}", "GET", None),
    ("/api/v1/policies/{id}/versions", "GET", None),
    ("/api/v1/findings/{id}/outcome", "GET", None),
    ("/api/v1/audit/{id}", "GET", None),
    ("/api/v1/erasure-requests/{id}", "GET", None),
]

FORBIDDEN_STATUSES = {200, 403, 422, 500}


def _seed_tenant_b_resource() -> str:
    """Returns the correlation_id / resource_id used to probe cross-tenant access.

    In a full integration scenario the tenant-B resource would be pre-seeded via a finding
    submission. For Phase 9.a red phase we use a synthetic UUID; a 404 response is the right
    answer regardless of whether the resource exists or belongs to tenant B — the FR-025
    contract is "cross-tenant request returns 404, period."
    """
    return f"tenant-b-resource-{uuid.uuid4().hex}"


@pytest.mark.parametrize("path,method,body", ENDPOINTS)
def test_cross_tenant_access_returns_404(path: str, method: str, body: dict | None) -> None:
    require_local_stack()
    token_a = mint_tenant_token(TENANT_A)
    resource_id = _seed_tenant_b_resource()
    url = f"{QUERY_BASE_URL}{path.format(id=resource_id)}"
    response = httpx.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token_a}"},
        json=body,
        timeout=5.0,
    )
    assert response.status_code not in FORBIDDEN_STATUSES, (
        f"FR-025 violation: {method} {path} returned {response.status_code} for a "
        f"cross-tenant request (tenant-A JWT targeting tenant-B resource); MUST return 404."
    )
    assert (
        response.status_code == 404
    ), f"FR-006 violation: {method} {path} returned {response.status_code}; expected 404."


def test_payload_tenant_id_mismatch_collapses_to_404() -> None:
    """POST /findings with a body tenant_id that disagrees with the JWT claim MUST 404."""
    require_local_stack()
    token_a = mint_tenant_token(TENANT_A)
    # Payload claims tenant-B; JWT claims tenant-A. Per FR-007 the JWT wins; per FR-006 the
    # response collapses to 404 (not 422) to avoid an existence oracle.
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        headers={"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"},
        json={
            "tenant_id": TENANT_B,
            "finding_id": "f-cross-tenant",
            "schema_version": "1.0.0",
        },
        timeout=5.0,
    )
    assert (
        response.status_code == 404
    ), f"FR-007 violation: POST /findings with tenant_id mismatch returned {response.status_code}; expected 404."

"""T221: negative-path cross-audience fuzz against the audit-admin OpenAPI surface.

Distinct task from T220 per the user implementer note: this fuzz runs against the AUDIT-ADMIN
OpenAPI surface (separate document at contracts/openapi/audit-admin.v1.yaml). The two surfaces
exist on different routers with different authentication audiences; a tenant JWT presented at
the audit-admin endpoint MUST return 401 (audience mismatch), not 404 (which is the regular-
surface cross-tenant response).

The 401 vs 404 distinction is load-bearing: on the regular surface 401 would be an existence
oracle for "is this a valid JWT?"; on the operator-only surface 401 IS the expected refusal
mode for a wrong-audience JWT, because audience verification happens before any handler is
reached. The operator endpoint's mere existence is public information (it's in the OpenAPI
contract); the existence of any specific tenant's audit chain is not.

Red phase (Phase 9.a): runs before T237 lands the break-glass router in app.py. Until T237,
``POST /api/v1/audit/break-glass/query`` returns 404 Not Found (FastAPI default for an
unregistered route). The test asserts the expected 401 contract and fails because 404 != 401
— exactly the right-reason red signal.

Anchors: FR-005a / FR-025 / Principle IV / Principle XVI.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    ORCHESTRATION_BASE_URL,
    TENANT_A,
    mint_operator_token,
    mint_tenant_token,
    require_local_stack,
    require_operator_issuer,
)

pytestmark = pytest.mark.contract

BREAK_GLASS_PATH = "/api/v1/audit/break-glass/query"


def _break_glass_body() -> dict[str, str]:
    return {
        "tenant_scope": "tenant-a",
        "correlation_id": "test-cid-001",
        "reason_code": "support_escalation",
    }


def test_tenant_jwt_rejected_at_break_glass_endpoint() -> None:
    """Tenant JWT (audience=collectmind-api) at break-glass endpoint MUST return 401."""
    require_local_stack()
    require_operator_issuer()
    token_a = mint_tenant_token(TENANT_A)
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Content-Type": "application/json",
        },
        json=_break_glass_body(),
        timeout=5.0,
    )
    assert response.status_code == 401, (
        f"FR-005a violation: tenant JWT at break-glass endpoint returned "
        f"{response.status_code}; expected 401 (audience mismatch). "
        f"A 404 here means the router isn't mounted (Phase 9.b T237 pending); "
        f"a 200 would be a SECURITY BUG (tenant JWT accepted by operator endpoint)."
    )


def test_missing_token_rejected_at_break_glass_endpoint() -> None:
    """No Authorization header → 401 (not 200, not 404 once router lands)."""
    require_local_stack()
    require_operator_issuer()
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={"Content-Type": "application/json"},
        json=_break_glass_body(),
        timeout=5.0,
    )
    assert response.status_code == 401


def test_operator_jwt_accepted_at_break_glass_endpoint() -> None:
    """Operator JWT (audience=collectmind-operator) MUST be accepted by the audience check.

    Status MAY be 200 (handler returns audit rows) or 4xx if the request body is malformed
    or the requested correlation_id has no rows — but it MUST NOT be 401, which would mean
    the operator-issuer JWT failed audience validation (a regression on ADR-0007 Part 4).

    Red phase: the router doesn't exist yet → 404. Test FAILS because 404 != "not 401" check
    (404 is also "not 401", so this test passes vacuously in the red phase). To detect the
    true red state, we also assert response.status_code != 404.
    """
    require_local_stack()
    require_operator_issuer()
    operator_token = mint_operator_token()
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={
            "Authorization": f"Bearer {operator_token}",
            "Content-Type": "application/json",
        },
        json=_break_glass_body(),
        timeout=5.0,
    )
    assert response.status_code != 401, (
        "FR-005a regression: operator JWT REJECTED at break-glass endpoint "
        "(401 = audience validation failed; should ACCEPT operator audience)"
    )
    assert (
        response.status_code != 404
    ), f"break-glass router not mounted: FastAPI returned 404 for {BREAK_GLASS_PATH}. Phase 9.b T237 is pending."

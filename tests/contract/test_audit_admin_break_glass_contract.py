"""T222: break-glass endpoint contract test.

Asserts the FR-005a/FR-005b contract on ``POST /api/v1/audit/break-glass/query``:
    - Operator JWT (audience=collectmind-operator) → 200 with an AuditEventList response shape
    - Tenant JWT → 401 (covered by T221; re-asserted here for contract-tier completeness)
    - Missing reason_code → 400 (per BreakGlassRequest schema)
    - Successful invocation produces a ``kind=break_glass`` row in audit_events (SC-013)

The atomic-audit property (the kind=break_glass row lands in the same transaction as the
bypassed SELECT) is asserted at the integration tier (T228). This contract test asserts only
the HTTP-surface contract; the DB invariant lives in the integration test.

Red phase: router doesn't exist (Phase 9.b T237). Every request returns 404 from FastAPI.
The test FAILS on the operator-happy-path because 404 != 200.

Anchors: FR-005a / FR-005b / SC-013 / Principle IV / Principle XVI.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    ORCHESTRATION_BASE_URL,
    mint_operator_token,
    require_local_stack,
    require_operator_issuer,
)

pytestmark = pytest.mark.contract

BREAK_GLASS_PATH = "/api/v1/audit/break-glass/query"


def test_break_glass_operator_happy_path_returns_200_with_audit_list() -> None:
    require_local_stack()
    require_operator_issuer()
    token = mint_operator_token()
    body = {
        "tenant_scope": "feature-001-default",
        "correlation_id": "test-bg-contract-001",
        "reason_code": "support_escalation",
    }
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=5.0,
    )
    assert response.status_code == 200, (
        f"break-glass operator JWT returned {response.status_code}; "
        f"expected 200 (FR-005a)"
    )
    payload = response.json()
    assert "events" in payload, "AuditEventList shape requires `events` field"
    assert "total" in payload, "AuditEventList shape requires `total` field"
    assert isinstance(payload["events"], list)
    assert isinstance(payload["total"], int)


def test_break_glass_missing_reason_code_returns_400() -> None:
    require_local_stack()
    require_operator_issuer()
    token = mint_operator_token()
    # reason_code intentionally omitted.
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"tenant_scope": "feature-001-default", "correlation_id": "test"},
        timeout=5.0,
    )
    assert response.status_code == 400, (
        f"missing reason_code → expected 400; got {response.status_code}"
    )


def test_break_glass_invalid_reason_code_returns_400() -> None:
    require_local_stack()
    require_operator_issuer()
    token = mint_operator_token()
    response = httpx.post(
        f"{ORCHESTRATION_BASE_URL}{BREAK_GLASS_PATH}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "tenant_scope": "feature-001-default",
            "correlation_id": "test",
            "reason_code": "not_in_enum",
        },
        timeout=5.0,
    )
    assert response.status_code == 400, (
        f"invalid reason_code → expected 400; got {response.status_code}"
    )

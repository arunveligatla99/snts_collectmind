"""T230: per-kind minimum field set enforcement on the audit writer.

Asserts that ``AuditEventWriter.write(kind=<new-kind>)`` raises ``ValueError`` when the
``originating_finding`` payload (the carrier for kind-specific fields per the FR-005b /
FR-013b / FR-023 / vehicle_assignment_change minimum-field-set patterns) is missing any
required field for the named kind.

Made green by T209 (Phase 8): the writer's ``_KIND_MIN_FIELDS`` dict enforces the per-kind
required-fields contract. This unit test pins the contract independent of the DB.

Anchors: FR-005b / FR-013b / FR-023 / Principle XVII / Principle IV.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from collectmind.registry.audit import AuditEventWriter, _KIND_MIN_FIELDS


class _FakeConn:
    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.fetchrow = AsyncMock(return_value={"event_id": "synth"})


class _FakeDb:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self, _tenant_id: str) -> Any:
        conn = self._conn

        class _Ctx:
            async def __aenter__(_self) -> _FakeConn:
                return conn

            async def __aexit__(_self, *_a: Any) -> None:
                return None

        return _Ctx()


# Sample valid payloads per new kind. Each carries the FULL minimum field set per
# _KIND_MIN_FIELDS. Each test parametrically drops one required field and asserts the
# writer raises ValueError.
_VALID_PAYLOADS: dict[str, dict[str, Any]] = {
    "break_glass": {
        "operator_principal_subject": "alice",
        "tenant_scope": "tenant-a",
        "reason_code": "support_escalation",
    },
    "tenant_config_change": {
        "service_principal_subject": "svc-tenant-mgmt",
        "target_tenant_id": "tenant-a",
    },
    "deployment_rejected": {
        "policy_ref": {"policy_id": "p", "version": "1.0.0"},
        "target_vehicle_id": "VIN-1",
        "policy_declared_tenant_id": "tenant-a",
        "vehicle_owning_tenant_id": "tenant-b",
    },
    "vehicle_assignment_change": {
        "service_principal_subject": "svc-fleet",
        "vehicle_id": "VIN-1",
        "new_tenant_id": "tenant-a",
        "reason_code": "initial_provisioning",
    },
}


@pytest.mark.parametrize("kind", sorted(_KIND_MIN_FIELDS.keys()))
@pytest.mark.asyncio
async def test_writer_accepts_full_minimum_field_set(kind: str) -> None:
    """With every required field present, the writer succeeds (no ValueError)."""
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    payload = dict(_VALID_PAYLOADS[kind])
    event_id = await writer.write(
        tenant_id="tenant-x",
        kind=kind,
        correlation_id="cid-001",
        principal_subject="sub",
        originating_finding=payload,
    )
    assert event_id


@pytest.mark.parametrize("kind", sorted(_KIND_MIN_FIELDS.keys()))
@pytest.mark.asyncio
async def test_writer_rejects_missing_required_field(kind: str) -> None:
    """Drop each required field one at a time and assert ValueError is raised."""
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    required = _KIND_MIN_FIELDS[kind]
    for field_to_drop in required:
        payload = dict(_VALID_PAYLOADS[kind])
        del payload[field_to_drop]
        with pytest.raises(ValueError, match=field_to_drop):
            await writer.write(
                tenant_id="tenant-x",
                kind=kind,
                correlation_id=f"cid-{field_to_drop}",
                principal_subject="sub",
                originating_finding=payload,
            )


def test_kind_min_fields_covers_all_four_new_kinds() -> None:
    """Meta-test: _KIND_MIN_FIELDS covers the four new kinds shipped by feature 002."""
    assert set(_KIND_MIN_FIELDS.keys()) == {
        "break_glass",
        "tenant_config_change",
        "deployment_rejected",
        "vehicle_assignment_change",
    }

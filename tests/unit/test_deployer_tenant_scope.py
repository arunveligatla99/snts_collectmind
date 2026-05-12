"""T285 coverage sweep: unit tests for the Phase 12 deployer wrappers.

Exercises ``collectmind.deployer.tenant_scope_check`` + ``collectmind.deployer.node`` at
the unit tier so coverage on these load-bearing modules clears the Principle IV 85%
floor. Integration coverage is at ``tests/integration/test_deployment_tenant_scope.py``;
this file complements that with dependency-mocked unit assertions for the structural
contracts (FR-021 first-gate, FR-022 no-retry, FR-023 audit-row minimum field set).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectmind.deployer.client import DeployResponse
from collectmind.deployer.node import deploy_with_tenant_scope_check
from collectmind.deployer.tenant_scope_check import (
    TenantVehicleMismatch,
    validate_tenant_scope,
)
from collectmind.errors import Fatal


def _ownership_cache(owner_by_vehicle: dict[str, str | None]) -> MagicMock:
    cache = MagicMock()
    cache.get_owner = AsyncMock(side_effect=owner_by_vehicle.get)
    return cache


def _audit_writer_double() -> MagicMock:
    writer = MagicMock()
    writer.write = AsyncMock(return_value="event-id")
    return writer


class _RecordingCollector:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def deploy(self, **kwargs: Any) -> DeployResponse:
        self.calls.append(kwargs)
        return DeployResponse(deployment_id="dep-1", status="accepted")


def test_tenant_vehicle_mismatch_is_fatal_subclass() -> None:
    """FR-022: ``TenantVehicleMismatch`` MUST extend ``Fatal`` so the existing
    Recoverable-class retry posture does not engage."""
    assert issubclass(TenantVehicleMismatch, Fatal)


def test_tenant_vehicle_mismatch_carries_fr023_minimum_field_set() -> None:
    """The exception's ``details`` MUST carry the FR-023 minimum field set so the
    deployer-node wrapper can write the audit row without re-deriving the values."""
    exc = TenantVehicleMismatch(
        policy_id="p-1",
        target_vehicle_id="VIN-1",
        policy_declared_tenant_id="tenant-a",
        vehicle_owning_tenant_id="tenant-b",
    )
    assert exc.policy_id == "p-1"
    assert exc.target_vehicle_id == "VIN-1"
    assert exc.policy_declared_tenant_id == "tenant-a"
    assert exc.vehicle_owning_tenant_id == "tenant-b"
    assert exc.details == {
        "policy_id": "p-1",
        "target_vehicle_id": "VIN-1",
        "policy_declared_tenant_id": "tenant-a",
        "vehicle_owning_tenant_id": "tenant-b",
    }


@pytest.mark.asyncio
async def test_validate_tenant_scope_passes_on_matching_owner() -> None:
    """Matching tenant: function returns without raising; no audit work expected."""
    cache = _ownership_cache({"VIN-1": "tenant-a"})
    await validate_tenant_scope(
        policy={"policy_id": "p-1", "tenant_id": "tenant-a", "vehicle_scope": ["VIN-1"]},
        ownership_cache=cache,
    )
    cache.get_owner.assert_awaited_once_with("VIN-1")


@pytest.mark.asyncio
async def test_validate_tenant_scope_raises_fatal_on_first_mismatch() -> None:
    """FR-021 first-gate: the iteration MUST stop at the first violating vehicle and the
    Fatal MUST carry the FR-023 fields for that vehicle. Subsequent vehicles in the scope
    are NOT consulted (no partial work)."""
    cache = _ownership_cache({"VIN-1": "tenant-b", "VIN-2": "tenant-a"})
    with pytest.raises(TenantVehicleMismatch) as exc:
        await validate_tenant_scope(
            policy={
                "policy_id": "p-1",
                "tenant_id": "tenant-a",
                "vehicle_scope": ["VIN-1", "VIN-2"],
            },
            ownership_cache=cache,
        )
    assert exc.value.target_vehicle_id == "VIN-1"
    assert exc.value.vehicle_owning_tenant_id == "tenant-b"
    # Only VIN-1 consulted; iteration stopped at the first violation.
    cache.get_owner.assert_awaited_once_with("VIN-1")


@pytest.mark.asyncio
async def test_validate_tenant_scope_treats_unknown_vehicle_as_mismatch() -> None:
    """An unknown vehicle (owner=None) MUST also raise — a policy claiming a vehicle the
    ownership store does not know about is itself a mismatch (defense-in-depth)."""
    cache = _ownership_cache({"VIN-1": None})
    with pytest.raises(TenantVehicleMismatch) as exc:
        await validate_tenant_scope(
            policy={"policy_id": "p-1", "tenant_id": "tenant-a", "vehicle_scope": ["VIN-1"]},
            ownership_cache=cache,
        )
    assert exc.value.vehicle_owning_tenant_id is None


@pytest.mark.asyncio
async def test_deploy_with_tenant_scope_check_happy_path_invokes_collector() -> None:
    """Matching scope: collector.deploy MUST be invoked once; no audit row written for
    ``kind=deployment_rejected``."""
    cache = _ownership_cache({"VIN-1": "tenant-a"})
    writer = _audit_writer_double()
    collector = _RecordingCollector()

    response = await deploy_with_tenant_scope_check(
        policy={
            "policy_id": "p-1",
            "version": "1.0.0",
            "tenant_id": "tenant-a",
            "vehicle_scope": ["VIN-1"],
        },
        tenant_id="tenant-a",
        correlation_id="cid-1",
        collector=collector,  # type: ignore[arg-type]
        ownership_cache=cache,
        audit_writer=writer,
    )

    assert response is not None
    assert response.status == "accepted"
    assert len(collector.calls) == 1
    writer.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_deploy_with_tenant_scope_check_mismatch_writes_audit_then_raises() -> None:
    """Mismatch path: collector.deploy NEVER invoked; audit row written with the FR-023
    minimum field set inside the Fatal handler; the Fatal then re-raises."""
    cache = _ownership_cache({"VIN-1": "tenant-b"})
    writer = _audit_writer_double()
    collector = _RecordingCollector()

    with pytest.raises(TenantVehicleMismatch):
        await deploy_with_tenant_scope_check(
            policy={
                "policy_id": "p-1",
                "version": "1.0.0",
                "tenant_id": "tenant-a",
                "vehicle_scope": ["VIN-1"],
            },
            tenant_id="tenant-a",
            correlation_id="cid-1",
            collector=collector,  # type: ignore[arg-type]
            ownership_cache=cache,
            audit_writer=writer,
        )

    # FR-022: collector never called on the mismatch branch.
    assert collector.calls == []

    # FR-023: audit row written with the full minimum field set on originating_finding.
    writer.write.assert_awaited_once()
    kwargs = writer.write.await_args.kwargs
    assert kwargs["kind"] == "deployment_rejected"
    assert kwargs["correlation_id"] == "cid-1"
    assert kwargs["tenant_id"] == "tenant-a"
    payload = kwargs["originating_finding"]
    assert payload["policy_ref"] == {"policy_id": "p-1", "version": "1.0.0"}
    assert payload["target_vehicle_id"] == "VIN-1"
    assert payload["policy_declared_tenant_id"] == "tenant-a"
    assert payload["vehicle_owning_tenant_id"] == "tenant-b"

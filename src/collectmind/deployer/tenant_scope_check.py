"""Deployment-client tenant-scope check (feature 002 / T276 / ADR-0009 Part 6).

Implements FR-021's first-gate contract: before any outbound deploy or any audit-row
write, verify every target vehicle in the policy belongs to the policy's declared
tenant. On any mismatch, raise Fatal ``TenantVehicleMismatch`` immediately. No partial
work, no outbound call, no pre-emptive audit row — the audit row for the rejection is
written by the deployer-node wrapper (T277) inside its Fatal-handling path.

Production wiring constructs the ``OwnershipCache`` in ``app.py``'s lifespan and passes
it through; the integration tier's ``test_deployment_tenant_scope.py`` calls
``validate_tenant_scope`` without an explicit cache and falls back to the module-level
host-friendly default constructed lazily on first use.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from collectmind.cache.ownership_cache import OwnershipCache
from collectmind.errors import Fatal

logger = structlog.get_logger(__name__)


class TenantVehicleMismatch(Fatal):
    """Fatal error class for FR-022.

    Raised when any target vehicle's owning tenant does not match the policy's declared
    tenant. Supersedes the deployer's existing Recoverable retry posture; the deployer
    MUST NOT retry on this class (FR-022) and MUST NOT have issued any outbound call
    before raising it (ADR-0009 Part 6).
    """

    def __init__(
        self,
        *,
        policy_id: str,
        target_vehicle_id: str,
        policy_declared_tenant_id: str,
        vehicle_owning_tenant_id: str | None,
    ) -> None:
        super().__init__(
            code="TENANT_VEHICLE_MISMATCH",
            status=409,
            reason=(
                f"target vehicle {target_vehicle_id!r} is owned by "
                f"{vehicle_owning_tenant_id!r}, not {policy_declared_tenant_id!r}"
            ),
            details={
                "policy_id": policy_id,
                "target_vehicle_id": target_vehicle_id,
                "policy_declared_tenant_id": policy_declared_tenant_id,
                "vehicle_owning_tenant_id": vehicle_owning_tenant_id,
            },
        )
        self.policy_id = policy_id
        self.target_vehicle_id = target_vehicle_id
        self.policy_declared_tenant_id = policy_declared_tenant_id
        self.vehicle_owning_tenant_id = vehicle_owning_tenant_id


async def _build_default_ownership_cache() -> OwnershipCache:
    """Build a host-friendly ``OwnershipCache`` from environment defaults.

    Used only when ``validate_tenant_scope`` / ``deploy_with_tenant_scope_check`` are
    called without an explicit cache (the integration test surface). Production wiring
    in ``app.py`` always passes an explicit cache constructed in the lifespan handler.

    Each call constructs fresh asyncpg + redis-py connections. Not memoized — connections
    are bound to the current event loop and pytest-asyncio creates a new loop per test.

    Env vars:
        - ``POSTGRES_DSN_HOST`` (default: ``postgresql://collectmind:localdev@localhost:5433/collectmind``)
        - ``REDIS_URL`` (default: ``redis://localhost:6379/0``)
    """
    from redis.asyncio import Redis as AsyncRedis

    from collectmind.registry.db import Database
    from collectmind.registry.tenant_vehicles import TenantVehiclesRepository

    dsn = os.environ.get(
        "POSTGRES_DSN_HOST",
        "postgresql://collectmind:localdev@localhost:5433/collectmind",
    )
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    db = Database(dsn)
    await db.connect()
    redis_client = AsyncRedis.from_url(redis_url, decode_responses=True)
    repo = TenantVehiclesRepository(db)
    return OwnershipCache(redis_client=redis_client, repo=repo)


async def validate_tenant_scope(
    *,
    policy: dict[str, Any],
    ownership_cache: OwnershipCache | None = None,
) -> None:
    """First-gate scope validation. Raises ``TenantVehicleMismatch`` on the first
    mismatched target vehicle; iteration stops at the first violation.

    Per Phase 12.b implementation directive: this MUST be the first check executed on the
    deployer hot path. It does not consult the rate-limiter, does not write any audit
    row, does not log to the audit chain, does not issue any outbound call. If a vehicle
    in ``policy.vehicle_scope`` does not belong to ``policy.tenant_id``, this raises
    immediately with the FR-023 minimum field set carried on the exception's ``details``.

    The caller (the deployer-node wrapper at ``collectmind.deployer.node``) catches the
    raised exception and writes the ``kind=deployment_rejected`` audit row inside its
    Fatal-handling path before letting the exception propagate.

    Anchors: FR-021 / FR-022 / ADR-0009 Part 6.
    """
    policy_declared_tenant_id = str(policy.get("tenant_id", ""))
    policy_id = str(policy.get("policy_id", ""))
    vehicle_scope = list(policy.get("vehicle_scope") or [])

    cache = ownership_cache if ownership_cache is not None else await _build_default_ownership_cache()

    for target_vehicle_id in vehicle_scope:
        owner = await cache.get_owner(str(target_vehicle_id))
        if owner != policy_declared_tenant_id:
            # First gate. Raise immediately; no partial work; caller writes the audit row.
            logger.warning(
                "tenant_scope_check_mismatch",
                policy_id=policy_id,
                target_vehicle_id=target_vehicle_id,
                policy_declared_tenant_id=policy_declared_tenant_id,
                vehicle_owning_tenant_id=owner,
            )
            raise TenantVehicleMismatch(
                policy_id=policy_id,
                target_vehicle_id=str(target_vehicle_id),
                policy_declared_tenant_id=policy_declared_tenant_id,
                vehicle_owning_tenant_id=owner,
            )

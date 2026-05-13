"""Deployer node wrapper with tenant-scope check + atomic audit-write on Fatal
(feature 002 / T277 / FR-021 / FR-022 / FR-023 / ADR-0009 Part 6).

Wraps an outbound ``CollectorAIClient.deploy(...)`` with the FR-021 first-gate scope
check (``validate_tenant_scope``). On Fatal ``TenantVehicleMismatch``:

    1. The audit row of kind ``deployment_rejected`` is written carrying the FR-023
       minimum field set (``policy_ref`` / ``target_vehicle_id`` /
       ``policy_declared_tenant_id`` / ``vehicle_owning_tenant_id``).
    2. The Fatal is re-raised to the caller. The collector's ``deploy(...)`` is NEVER
       invoked on a mismatch — the scope check fires before any outbound call AND the
       audit-write happens inside the Fatal handler, not on the happy path.
    3. The Fatal class supersedes the deployer's existing Recoverable retry posture per
       Spec FR-022; no retry is attempted.

Per Phase 12.b implementation directive: the audit write is the last act before the
Fatal propagates. ``AuditEventWriter.write(kind="deployment_rejected", ...)`` runs
synchronously inside the ``except TenantVehicleMismatch`` block; if the audit write
itself raises, the audit failure propagates instead of the original Fatal (the original
Fatal's details remain on the audit-failure traceback).
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from collectmind.cache.ownership_cache import OwnershipCache
from collectmind.deployer.client import CollectorAIClient, DeployResponse
from collectmind.deployer.tenant_scope_check import (
    TenantVehicleMismatch,
    validate_tenant_scope,
)
from collectmind.registry.audit import AuditEventWriter

logger = structlog.get_logger(__name__)


async def _build_default_audit_writer() -> AuditEventWriter:
    """Build a host-friendly ``AuditEventWriter`` from env defaults.

    Used only when ``deploy_with_tenant_scope_check`` is called without an explicit
    audit writer (the integration test surface). Production wiring in ``app.py`` always
    passes an explicit writer constructed in the lifespan handler.

    Each call constructs fresh asyncpg connections. Not memoized — connections are bound
    to the current event loop and pytest-asyncio creates a new loop per test.

    Env var: ``POSTGRES_DSN_HOST`` (same default as the tenant-scope-check factory).
    """
    from collectmind.registry.db import Database

    dsn = os.environ.get(
        "POSTGRES_DSN_HOST",
        "postgresql://collectmind:localdev@localhost:5433/collectmind",
    )
    db = Database(dsn)
    await db.connect()
    return AuditEventWriter(db)


async def deploy_with_tenant_scope_check(
    *,
    policy: dict[str, Any],
    tenant_id: str,
    correlation_id: str,
    collector: CollectorAIClient,
    ownership_cache: OwnershipCache | None = None,
    audit_writer: AuditEventWriter | None = None,
) -> DeployResponse | None:
    """Run the FR-021 scope check, then deploy via the collector.

    On a tenant-vehicle mismatch:
        - ``collector.deploy(...)`` is NEVER invoked (the scope check fires first).
        - An immutable ``kind=deployment_rejected`` audit row is written carrying the
          FR-023 minimum field set.
        - The Fatal ``TenantVehicleMismatch`` is re-raised; FR-022 supersedes Recoverable
          retry.

    On a matching scope: the collector is invoked once and its response is returned to
    the caller (no audit row of kind ``deployment_rejected`` is written; the existing
    ``kind=deployed`` audit-row write remains the responsibility of the surrounding
    graph runner — this wrapper is the scope-check + rejection-audit layer only).

    Args:
        policy: the generated policy dict; must carry ``tenant_id``, ``policy_id``,
            ``version``, ``vehicle_scope``.
        tenant_id: the requesting principal's tenant id (the JWT-derived value).
        correlation_id: the request correlation id; threads through the audit row.
        collector: the downstream ``CollectorAIClient`` to invoke on a matching scope.
        ownership_cache: optional override for the scope-check's ownership lookup;
            falls back to the host-friendly lazy default.
        audit_writer: optional override for the audit-row writer; falls back to the
            host-friendly lazy default.
    """
    try:
        await validate_tenant_scope(policy=policy, ownership_cache=ownership_cache)
    except TenantVehicleMismatch as mismatch:
        # Atomic audit-write inside the Fatal handler. This is the last act before the
        # Fatal propagates; the collector.deploy(...) is NEVER reached.
        writer = audit_writer if audit_writer is not None else await _build_default_audit_writer()
        await writer.write(
            tenant_id=tenant_id,
            kind="deployment_rejected",
            correlation_id=correlation_id,
            principal_subject=tenant_id,
            originating_finding={
                "policy_ref": {
                    "policy_id": str(policy.get("policy_id", "")),
                    "version": str(policy.get("version", "1.0.0")),
                },
                "target_vehicle_id": mismatch.target_vehicle_id,
                "policy_declared_tenant_id": mismatch.policy_declared_tenant_id,
                "vehicle_owning_tenant_id": mismatch.vehicle_owning_tenant_id,
            },
        )
        logger.info(
            "deployment_rejected_audit_written",
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            target_vehicle_id=mismatch.target_vehicle_id,
            vehicle_owning_tenant_id=mismatch.vehicle_owning_tenant_id,
        )
        raise

    # Scope check passed. Issue the outbound call.
    response = collector.deploy(
        tenant_id=tenant_id,
        policy_id=str(policy.get("policy_id", "")),
        version=str(policy.get("version", "1.0.0")),
        vehicle_scope=list(policy.get("vehicle_scope") or []),
        payload=policy,
        payload_signature=b"",
        signature_key_id="",
    )
    return response

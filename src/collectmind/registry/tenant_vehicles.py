"""Tenant-vehicle ownership repository (feature 002 / T235 / ADR-0009).

Two access paths:
    - ``get_owner(vehicle_id)`` — read the current owner of a vehicle. Uses a service-
      principal connection (BYPASSRLS) because the deployer's tenant-scope check
      (T276) needs the authoritative answer regardless of the requesting tenant's
      RLS context. Returns ``None`` if the vehicle is not in the ownership store.
    - ``assign(vehicle_id, tenant_id, ...)`` — service-principal write. Inserts the
      current-state row; the ``tenant_vehicles_history_trigger`` (migration 015)
      appends to the append-only history; the ``tenant_vehicles_audit_trigger``
      writes the ``kind=vehicle_assignment_change`` audit row. All in one transaction.

Phase 12 (T275 / T276) wires this repository into the deployer hot path; Phase 9.b ships
the primitive only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog

from collectmind.registry.db import Database

logger = structlog.get_logger(__name__)


ReasonCode = Literal[
    "initial_provisioning",
    "resale",
    "fleet_reassignment",
    "oem_handoff",
    "lease_return",
    "totaled",
    "other",
]


@dataclass(frozen=True)
class VehicleOwnership:
    vehicle_id: str
    tenant_id: str
    assigned_at: str
    assigned_by_subject: str
    reason_code: str


class TenantVehiclesRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_owner(self, vehicle_id: str) -> str | None:
        """Return the current owning tenant id for a vehicle, or ``None`` if unknown."""
        async with self._db.acquire_service_principal() as conn:
            row = await conn.fetchrow(
                "SELECT tenant_id FROM tenant_vehicles WHERE vehicle_id = $1",
                vehicle_id,
            )
        return str(row["tenant_id"]) if row is not None else None

    async def assign(
        self,
        vehicle_id: str,
        tenant_id: str,
        *,
        assigned_by_subject: str,
        reason_code: ReasonCode,
    ) -> None:
        """Service-principal assignment. Triggers history + audit-row writes atomically."""
        async with self._db.acquire_service_principal() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO tenant_vehicles (vehicle_id, tenant_id, assigned_by_subject, reason_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (vehicle_id) DO UPDATE SET
                  tenant_id = EXCLUDED.tenant_id,
                  assigned_by_subject = EXCLUDED.assigned_by_subject,
                  reason_code = EXCLUDED.reason_code,
                  assigned_at = now()
                """,
                vehicle_id,
                tenant_id,
                assigned_by_subject,
                reason_code,
            )
        logger.info("vehicle_assigned", vehicle_id=vehicle_id, tenant_id=tenant_id, reason=reason_code)

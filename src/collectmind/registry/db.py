"""asyncpg pool with tenant-scoped + service-principal RLS context managers."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

# Feature 002 / migration 017: non-BYPASSRLS tenant role. The orchestration-api connects as
# the superuser (`collectmind`) but drops into `collectmind_tenant` via SET LOCAL ROLE inside
# `acquire(tenant_id)` so the RESTRICTIVE RLS policies actually enforce.
_TENANT_ROLE = os.environ.get("POSTGRES_TENANT_ROLE", "collectmind_tenant")


class Database:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 10) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )
        logger.info("db_pool_ready", min_size=self._min_size, max_size=self._max_size)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        if self._pool is None:
            return False
        async with self._pool.acquire() as conn:
            value = await conn.fetchval("SELECT 1")
            return value == 1

    @asynccontextmanager
    async def acquire(self, tenant_id: str) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a tenant-scoped connection inside a transaction.

        Steps (in order, inside ``conn.transaction()`` so all three are transaction-local):
            1. ``SET LOCAL ROLE collectmind_tenant`` — drops into the non-BYPASSRLS role so
               RESTRICTIVE RLS policies actually enforce. Per migration 017, the role exists
               and the superuser is granted membership.
            2. ``SET LOCAL app.tenant_id = $1`` — sets the GUC consulted by every RLS policy.
            3. Yield the connection to the caller.

        On COMMIT/ROLLBACK the role reverts to the session role (the superuser), and
        ``app.tenant_id`` reverts to NULL. The next transaction on the same pooled connection
        starts with NO context — under the RESTRICTIVE RLS missing-context defense (migration
        012) every query returns zero rows until the next ``acquire(tenant_id)`` lands.

        ADR-0007 Part 3 is the binding contract; T226 enforces it under test.
        """
        if self._pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {_TENANT_ROLE}")
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn

    @asynccontextmanager
    async def acquire_service_principal(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a service-principal connection that bypasses RLS.

        Used by:
            - The break-glass primitive (FR-005a) — cross-tenant audit reads under elevated
              audit (ADR-0007 Part 4 / FR-005b atomic-audit row writer).
            - The tenant_config write primitive (FR-013) — service-principal-only INSERT/
              UPDATE/DELETE; triggers the tenant_config_change atomic audit row.
            - The tenant_vehicles assignment primitive (ADR-0009 Part 3) — same shape.

        The connection runs under the BYPASSRLS superuser role (the session default). The
        caller is responsible for ensuring any write produces the matching atomic-audit row;
        the DB triggers enforce the constraint structurally.

        Transaction wrapping is the caller's responsibility — service-principal writes often
        need to compose with other writes in a single transaction (break-glass: SELECT +
        audit-row INSERT; tenant_config: INSERT/UPDATE + audit trigger fires inside same txn).
        """
        if self._pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self._pool.acquire() as conn:
            yield conn

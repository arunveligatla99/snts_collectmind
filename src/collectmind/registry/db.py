"""asyncpg pool with a tenant-scoped RLS context manager."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


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
        """Acquire a connection inside a transaction with ``app.tenant_id`` set.

        Feature 002 (ADR-0007 Part 3) tightens the contract: ``set_config('app.tenant_id',
        $1, true)`` is transaction-local ONLY when called inside a transaction. Outside a
        transaction, ``is_local=true`` falls back to session-scope per Postgres docs, which
        leaks across connection-pool reuse. The connection-pool footgun this guards against:
        request A on tenant X sets the GUC on a pooled connection; request B on tenant Y
        reuses the same connection and inherits the stale GUC unless it explicitly resets.

        The fix: wrap every ``acquire(tenant_id)`` in ``conn.transaction()`` so the GUC is
        genuinely transaction-local. On commit/rollback the setting reverts to NULL, and any
        subsequent transaction on the same pooled connection starts with no context — under
        the RESTRICTIVE RLS missing-context defense (migration 012) every query returns zero
        rows until the next ``acquire(tenant_id)`` sets a fresh GUC.

        Tested by ``tests/integration/test_rls_restrictive.py::test_stale_gucs_fail_closed``
        (feature 002 T226).
        """
        if self._pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn

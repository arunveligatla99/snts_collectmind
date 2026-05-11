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
        """Acquire a connection with `app.tenant_id` set so RLS policies scope reads."""
        if self._pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn

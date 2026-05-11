"""Unit tests for registry/db.py (T134). asyncpg.create_pool mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectmind.registry.db import Database


@pytest.mark.asyncio
async def test_acquire_raises_when_pool_not_initialized() -> None:
    db = Database(dsn="postgresql://x")
    with pytest.raises(RuntimeError, match="not initialized"):
        async with db.acquire("t"):
            pass


@pytest.mark.asyncio
async def test_ping_returns_false_when_pool_not_initialized() -> None:
    db = Database(dsn="postgresql://x")
    assert await db.ping() is False


@pytest.mark.asyncio
async def test_connect_then_close_lifecycle() -> None:
    with patch("collectmind.registry.db.asyncpg") as ap:
        pool = MagicMock()
        pool.close = AsyncMock()
        ap.create_pool = AsyncMock(return_value=pool)
        db = Database(dsn="postgresql://x")
        await db.connect()
        await db.connect()  # idempotent
        ap.create_pool.assert_awaited_once()
        await db.close()
        pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_executes_select_one_inside_pool() -> None:
    with patch("collectmind.registry.db.asyncpg") as ap:
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=1)
        pool = MagicMock()

        class _Acquire:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *_a):
                return None

        pool.acquire = MagicMock(return_value=_Acquire())
        ap.create_pool = AsyncMock(return_value=pool)
        db = Database(dsn="postgresql://x")
        await db.connect()
        assert await db.ping() is True
        conn.fetchval.assert_awaited_with("SELECT 1")


@pytest.mark.asyncio
async def test_acquire_sets_app_tenant_id_inside_transaction() -> None:
    with patch("collectmind.registry.db.asyncpg") as ap:
        conn = MagicMock()
        conn.execute = AsyncMock()
        pool = MagicMock()

        class _Acquire:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *_a):
                return None

        pool.acquire = MagicMock(return_value=_Acquire())
        ap.create_pool = AsyncMock(return_value=pool)
        db = Database(dsn="postgresql://x")
        await db.connect()
        async with db.acquire("tenant-X") as c:
            assert c is conn
        conn.execute.assert_awaited_with("SELECT set_config('app.tenant_id', $1, true)", "tenant-X")

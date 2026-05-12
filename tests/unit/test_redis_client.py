"""Unit tests for redis/client.py (T134 + Phase 14 T293 update).

Post Phase 14 T293 cleanup the legacy single-tenant API (``get_signal`` /
``put_signal``) raises ``LegacyKeyShapeError`` unconditionally. The tenant-scoped
API (``get_signal_for_tenant`` / ``put_signal_for_tenant``) is the only path that
reads or writes the hot store. Redis client mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectmind.redis.client import HotStore, LegacyKeyShapeError


class TestHotStore:
    @pytest.mark.asyncio
    async def test_connect_and_close_lifecycle(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.aclose = AsyncMock()
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://localhost:6379/0")
            await store.connect()
            await store.connect()  # idempotent
            klass.from_url.assert_called_once_with("redis://localhost:6379/0", decode_responses=True)
            await store.close()
            instance.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ping_returns_false_when_not_connected(self) -> None:
        store = HotStore("redis://x")
        assert await store.ping() is False

    @pytest.mark.asyncio
    async def test_ping_returns_true_when_redis_replies_ok(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.ping = AsyncMock(return_value=True)
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x")
            await store.connect()
            assert await store.ping() is True

    @pytest.mark.asyncio
    async def test_legacy_get_signal_always_raises(self) -> None:
        """Post Phase 14 T293: legacy get_signal raises Fatal regardless of connection state."""
        store = HotStore("redis://x")
        with pytest.raises(LegacyKeyShapeError):
            await store.get_signal("VIN-1", "Vehicle.Foo")

    @pytest.mark.asyncio
    async def test_legacy_put_signal_always_raises(self) -> None:
        """Post Phase 14 T293: legacy put_signal raises Fatal regardless of connection state."""
        store = HotStore("redis://x")
        with pytest.raises(LegacyKeyShapeError):
            await store.put_signal("VIN-1", "Vehicle.Foo", "42")

    @pytest.mark.asyncio
    async def test_get_signal_for_tenant_returns_value(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.get = AsyncMock(return_value="42")
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x")
            await store.connect()
            assert await store.get_signal_for_tenant("tenant-a", "VIN-1", "Vehicle.Foo") == "42"
            instance.get.assert_awaited_with("tenant-a:VIN-1:Vehicle.Foo")

    @pytest.mark.asyncio
    async def test_get_signal_for_tenant_returns_none_on_miss(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.get = AsyncMock(return_value=None)
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x")
            await store.connect()
            assert await store.get_signal_for_tenant("tenant-a", "VIN-1", "Vehicle.Foo") is None

    @pytest.mark.asyncio
    async def test_put_signal_for_tenant_writes_with_ttl(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.set = AsyncMock()
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x", default_ttl=60)
            await store.connect()
            await store.put_signal_for_tenant("tenant-a", "VIN-1", "Vehicle.Foo", "42")
            instance.set.assert_awaited_with("tenant-a:VIN-1:Vehicle.Foo", "42", ex=60)

    @pytest.mark.asyncio
    async def test_get_signal_for_tenant_raises_when_not_connected(self) -> None:
        store = HotStore("redis://x")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_signal_for_tenant("tenant-a", "VIN-1", "Vehicle.Foo")

    @pytest.mark.asyncio
    async def test_put_signal_for_tenant_raises_when_not_connected(self) -> None:
        store = HotStore("redis://x")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.put_signal_for_tenant("tenant-a", "VIN-1", "Vehicle.Foo", "42")

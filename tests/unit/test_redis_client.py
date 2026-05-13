"""Unit tests for redis/client.py (T134). Redis client mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectmind.redis.client import HotStore


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
    async def test_get_signal_raises_when_not_connected(self) -> None:
        store = HotStore("redis://x")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_signal("v", "s")

    @pytest.mark.asyncio
    async def test_get_signal_returns_value(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.get = AsyncMock(return_value="42")
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x")
            await store.connect()
            assert await store.get_signal("VIN-1", "Vehicle.Foo") == "42"
            instance.get.assert_awaited_with("VIN-1:Vehicle.Foo")

    @pytest.mark.asyncio
    async def test_put_signal_writes_with_ttl(self) -> None:
        with patch("collectmind.redis.client.AsyncRedis") as klass:
            instance = MagicMock()
            instance.set = AsyncMock()
            klass.from_url = MagicMock(return_value=instance)
            store = HotStore("redis://x", default_ttl=60)
            await store.connect()
            await store.put_signal("VIN-1", "Vehicle.Foo", "42")
            instance.set.assert_awaited_with("VIN-1:Vehicle.Foo", "42", ex=60)

    @pytest.mark.asyncio
    async def test_put_signal_raises_when_not_connected(self) -> None:
        store = HotStore("redis://x")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.put_signal("v", "s", "x")

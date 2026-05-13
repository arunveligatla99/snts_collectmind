"""T285 coverage sweep: TenantConfigRepository + _TTLCache unit tests."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectmind.registry.tenant_config import (
    DEFAULT_INBOUND_BURST,
    DEFAULT_INBOUND_SUSTAINED_RPS,
    DEFAULT_QUERY_BURST,
    DEFAULT_QUERY_SUSTAINED_RPS,
    TenantConfigRepository,
    _default_config,
    _TTLCache,
)


def test_default_config_uses_fr012_values() -> None:
    config = _default_config("tenant-a")
    assert config.source == "default"
    assert config.inbound.sustained_rps == DEFAULT_INBOUND_SUSTAINED_RPS
    assert config.inbound.burst_capacity == DEFAULT_INBOUND_BURST
    assert config.query.sustained_rps == DEFAULT_QUERY_SUSTAINED_RPS
    assert config.query.burst_capacity == DEFAULT_QUERY_BURST


def test_ttl_cache_miss_returns_none() -> None:
    cache = _TTLCache(ttl_seconds=5.0)
    assert cache.get("tenant-x") is None


def test_ttl_cache_hit_then_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _TTLCache(ttl_seconds=1.0)
    config = _default_config("tenant-a")
    cache.put("tenant-a", config)
    assert cache.get("tenant-a") is config

    # Fast-forward time past TTL.
    fake_now = time.monotonic() + 100.0
    monkeypatch.setattr(time, "monotonic", lambda: fake_now)
    assert cache.get("tenant-a") is None


def test_ttl_cache_eviction_at_capacity() -> None:
    cache = _TTLCache(ttl_seconds=60.0, capacity=2)
    cache.put("a", _default_config("a"))
    cache.put("b", _default_config("b"))
    cache.put("c", _default_config("c"))  # forces an eviction
    assert len(cache._data) == 2  # type: ignore[attr-defined]


def test_ttl_cache_invalidate_drops_entry() -> None:
    cache = _TTLCache(ttl_seconds=60.0)
    cache.put("a", _default_config("a"))
    cache.invalidate("a")
    assert cache.get("a") is None


@pytest.mark.asyncio
async def test_get_for_tenant_returns_cached_on_hit() -> None:
    """Cache hit MUST skip the DB altogether."""
    db = MagicMock()
    db.acquire = MagicMock()
    repo = TenantConfigRepository(db)
    cached = _default_config("tenant-a")
    repo._cache.put("tenant-a", cached)  # type: ignore[attr-defined]
    result = await repo.get_for_tenant("tenant-a")
    assert result is cached
    db.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_for_tenant_returns_default_on_db_miss() -> None:
    """No row in tenant_config → FR-012 defaults returned + cached."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)

    class _AcquireCtx:
        async def __aenter__(self) -> object:
            return conn

        async def __aexit__(self, *_: object) -> None:
            return None

    db = MagicMock()
    db.acquire = MagicMock(return_value=_AcquireCtx())

    repo = TenantConfigRepository(db)
    result = await repo.get_for_tenant("tenant-a")
    assert result.source == "default"
    assert result.tenant_id == "tenant-a"
    # Cached after first lookup.
    assert repo._cache.get("tenant-a") is not None  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_for_tenant_uses_override_row_when_present() -> None:
    from datetime import datetime

    conn = MagicMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "tenant_id": "tenant-a",
            "inbound_sustained_rps": 1000,
            "inbound_burst_capacity": 2000,
            "query_sustained_rps": 100,
            "query_burst_capacity": 200,
            "updated_at": datetime(2026, 5, 11),
        }
    )

    class _AcquireCtx:
        async def __aenter__(self) -> object:
            return conn

        async def __aexit__(self, *_: object) -> None:
            return None

    db = MagicMock()
    db.acquire = MagicMock(return_value=_AcquireCtx())

    repo = TenantConfigRepository(db)
    result = await repo.get_for_tenant("tenant-a")
    assert result.source == "override"
    assert result.inbound.sustained_rps == 1000
    assert result.query.burst_capacity == 200


def test_repository_invalidate_clears_cache() -> None:
    db = MagicMock()
    repo = TenantConfigRepository(db)
    repo._cache.put("a", _default_config("a"))  # type: ignore[attr-defined]
    repo.invalidate("a")
    assert repo._cache.get("a") is None  # type: ignore[attr-defined]

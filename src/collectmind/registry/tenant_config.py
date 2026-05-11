"""Tenant configuration repository + in-process cache (feature 002 / T234 / FR-013).

Two-layer read:
    Layer 1 — in-process LRU cache. 1024-tenant capacity; 5-second TTL (the safety net
              for NOTIFY-pipeline failures per ADR-0008 Part 4).
    Layer 2 — Postgres ``tenant_config`` table. SELECT under the requesting tenant's
              RLS context (tenant-scoped reads are allowed by FR-013a).

The cache-first-with-Postgres-fallback ordering is the contract called out by the user at
Phase 9.b kickoff: T241's handler MUST do cache-first, fall back to Postgres on miss, and
NOT short-circuit to either layer exclusively. The cache invalidation path is wired by
``ratelimit.config_cache`` (Phase 10), which subscribes to Postgres NOTIFY and clears the
cache entry on configuration changes.

For Phase 9.b this module ships the synchronous read primitives + a small TTL-aware cache;
Phase 10 lands the LISTEN consumer that subscribes to ``tenant_config_changed``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from collectmind.registry.db import Database

logger = structlog.get_logger(__name__)


# FR-012 defaults applied when no tenant_config row exists.
DEFAULT_INBOUND_SUSTAINED_RPS = 2000
DEFAULT_INBOUND_BURST = 4000
DEFAULT_QUERY_SUSTAINED_RPS = 200
DEFAULT_QUERY_BURST = 400


@dataclass(frozen=True)
class RateLimitBucket:
    sustained_rps: int
    burst_capacity: int


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    inbound: RateLimitBucket
    query: RateLimitBucket
    source: str  # "default" | "override"
    updated_at: str | None = None


_DEFAULT_INBOUND = RateLimitBucket(DEFAULT_INBOUND_SUSTAINED_RPS, DEFAULT_INBOUND_BURST)
_DEFAULT_QUERY = RateLimitBucket(DEFAULT_QUERY_SUSTAINED_RPS, DEFAULT_QUERY_BURST)


def _default_config(tenant_id: str) -> TenantConfig:
    return TenantConfig(
        tenant_id=tenant_id,
        inbound=_DEFAULT_INBOUND,
        query=_DEFAULT_QUERY,
        source="default",
    )


class _TTLCache:
    """Tiny TTL cache. Phase 10 replaces this with an LRU + NOTIFY consumer per ADR-0008."""

    def __init__(self, ttl_seconds: float = 5.0, capacity: int = 1024) -> None:
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._data: dict[str, tuple[float, TenantConfig]] = {}

    def get(self, tenant_id: str) -> TenantConfig | None:
        entry = self._data.get(tenant_id)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._data.pop(tenant_id, None)
            return None
        return value

    def put(self, tenant_id: str, config: TenantConfig) -> None:
        if len(self._data) >= self._capacity:
            # Naive eviction: drop the oldest entry.
            oldest_key = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest_key, None)
        self._data[tenant_id] = (time.monotonic() + self._ttl, config)

    def invalidate(self, tenant_id: str) -> None:
        self._data.pop(tenant_id, None)


class TenantConfigRepository:
    """Read tenant_config with cache-first, Postgres fallback."""

    def __init__(self, db: Database, cache: _TTLCache | None = None) -> None:
        self._db = db
        self._cache = cache or _TTLCache()

    async def get_for_tenant(self, tenant_id: str) -> TenantConfig:
        """Cache-first read of the requesting tenant's effective config.

        Returns the FR-012 defaults if no override row exists in ``tenant_config``.
        """
        cached = self._cache.get(tenant_id)
        if cached is not None:
            return cached
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT tenant_id, inbound_sustained_rps, inbound_burst_capacity,
                       query_sustained_rps, query_burst_capacity, updated_at
                FROM tenant_config WHERE tenant_id = $1
                """,
                tenant_id,
            )
        if row is None:
            config = _default_config(tenant_id)
        else:
            config = TenantConfig(
                tenant_id=str(row["tenant_id"]),
                inbound=RateLimitBucket(int(row["inbound_sustained_rps"]), int(row["inbound_burst_capacity"])),
                query=RateLimitBucket(int(row["query_sustained_rps"]), int(row["query_burst_capacity"])),
                source="override",
                updated_at=row["updated_at"].isoformat() if row["updated_at"] is not None else None,
            )
        self._cache.put(tenant_id, config)
        return config

    def invalidate(self, tenant_id: str) -> None:
        """Called by the LISTEN/NOTIFY consumer (Phase 10) on tenant_config_changed."""
        self._cache.invalidate(tenant_id)

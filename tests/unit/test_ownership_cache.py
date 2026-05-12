"""T274: OwnershipCache write-through + invalidation unit tests (Phase 12 US4 / ADR-0009 Part 4).

Asserts the four properties the Phase 12 vehicle-ownership cache MUST satisfy per
[ADR-0009 Part 4](../../docs/adr/0009-tenant-vehicle-ownership-store.md):

    1. Cache miss → Postgres lookup → write-back to Redis with the canonical 1h TTL
       (key shape ``vehicle_ownership:{vehicle_id}``).
    2. Cache hit → Postgres NEVER consulted.
    3. ``invalidate(vehicle_id)`` deletes the Redis entry so the next read repopulates.
    4. Redis unavailability falls back to Postgres (failure-OPEN posture per ADR-0009
       Part 4 — explicitly distinguished from the rate-limiter's failure-CLOSED posture
       per ADR-0008 Part 3; ownership lookup is a correctness gate, not a security
       primitive, so a Redis outage must NOT block deployments).

Made green by T275. Red phase: the Phase 8 placeholder at
``src/collectmind/cache/ownership_cache.py`` defines ``__init__(self) -> None`` that
immediately raises ``NotImplementedError``. Every test instantiates ``OwnershipCache(...)``
and so trips either ``TypeError`` (signature mismatch) or ``NotImplementedError`` (stub
guard) until T275 lands the real constructor + methods.

Anchors: ADR-0009 Part 4 / FR-021 / Principle II / Principle IV.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectmind.cache.ownership_cache import OwnershipCache

# Pinned by ADR-0009 Part 4. The cache key is global (not tenant-scoped) because the
# lookup answers "who owns this vehicle?" — exactly the operator-level question the
# deployer needs before issuing any outbound call.
CACHE_KEY_PREFIX = "vehicle_ownership:"
CACHE_TTL_SECONDS = 3600  # ADR-0009 Part 4: 1 h


def _redis_double() -> MagicMock:
    """Test double for the asyncio Redis client. ``get`` defaults to a miss."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


def _repo_double(owner: str | None) -> MagicMock:
    """Test double for ``TenantVehiclesRepository``; exposes ``get_owner`` only."""
    repo = MagicMock()
    repo.get_owner = AsyncMock(return_value=owner)
    return repo


def _ttl_seconds_from_set_call(set_mock: AsyncMock) -> Any:
    """Extract the TTL argument from a Redis ``SET`` call, accepting either positional
    (``set(key, value, 3600)``) or keyword form (``set(key, value, ex=3600)``)."""
    args, kwargs = set_mock.await_args
    if "ex" in kwargs:
        return kwargs["ex"]
    if len(args) >= 3:
        return args[2]
    return None


@pytest.mark.asyncio
async def test_cache_miss_hits_postgres_and_populates_redis() -> None:
    """Miss path: Redis returns None → Postgres lookup → SET back to Redis with TTL.

    Pins three contractual properties of write-through:
      - the cached key shape is ``vehicle_ownership:{vehicle_id}`` (no tenant prefix),
      - the cached value is the owning tenant id returned by the repo,
      - the TTL on write-back is exactly 3600 seconds (ADR-0009 Part 4).
    """
    redis = _redis_double()
    redis.get.return_value = None
    repo = _repo_double("tenant-a")
    cache = OwnershipCache(redis_client=redis, repo=repo)

    owner = await cache.get_owner("VIN-1")

    assert owner == "tenant-a"
    redis.get.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}VIN-1")
    repo.get_owner.assert_awaited_once_with("VIN-1")
    redis.set.assert_awaited_once()
    set_args, _ = redis.set.await_args
    assert set_args[0] == f"{CACHE_KEY_PREFIX}VIN-1"
    assert set_args[1] == "tenant-a"
    assert _ttl_seconds_from_set_call(redis.set) == CACHE_TTL_SECONDS, (
        f"ADR-0009 Part 4 violation: write-back TTL must be {CACHE_TTL_SECONDS}s "
        f"(1 h); got {_ttl_seconds_from_set_call(redis.set)}"
    )


@pytest.mark.asyncio
async def test_cache_hit_skips_postgres() -> None:
    """Hit path: Redis returns the cached owner → Postgres is NEVER consulted.

    This is the hot-path property: SC-005's latency-preservation budget is honored only if
    cache hits stay within one Redis round trip. A cache hit that still touches Postgres
    silently doubles deployer latency.
    """
    redis = _redis_double()
    redis.get.return_value = "tenant-b"
    repo = _repo_double(None)
    cache = OwnershipCache(redis_client=redis, repo=repo)

    owner = await cache.get_owner("VIN-2")

    assert owner == "tenant-b"
    redis.get.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}VIN-2")
    repo.get_owner.assert_not_awaited()
    # No write-back on hit — the value is already in Redis.
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalidate_clears_redis_key() -> None:
    """Explicit invalidation removes the Redis entry; next read repopulates.

    Invalidation is called by the service-principal write path that mutates
    ``tenant_vehicles`` (ownership transition); without it, a cache hit keeps serving the
    pre-transition owner for up to one TTL window and the deployer would deny legitimate
    deployments.
    """
    redis = _redis_double()
    repo = _repo_double(None)
    cache = OwnershipCache(redis_client=redis, repo=repo)

    await cache.invalidate("VIN-3")
    redis.delete.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}VIN-3")


@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_postgres() -> None:
    """Failure-OPEN posture (ADR-0009 Part 4) — opposite of the rate-limiter's
    failure-CLOSED posture (ADR-0008 Part 3).

    A Redis outage must NOT block deployments — ownership lookup is a correctness gate,
    not a security primitive. The cache silently falls back to Postgres and the deployer
    proceeds. The same applies if the write-back to Redis fails on a miss (the lookup
    answer is still valid; the cache merely stays cold for this key).
    """
    redis = _redis_double()
    redis.get.side_effect = RuntimeError("redis connection lost")
    repo = _repo_double("tenant-a")
    cache = OwnershipCache(redis_client=redis, repo=repo)

    owner = await cache.get_owner("VIN-4")
    assert owner == "tenant-a", (
        "ADR-0009 Part 4 violation: failure-OPEN posture requires Postgres fallback "
        "when Redis is unavailable; got None instead of the authoritative answer"
    )
    repo.get_owner.assert_awaited_once_with("VIN-4")

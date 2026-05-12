"""Tenant-vehicle ownership cache (feature 002 / T275 / ADR-0009 Part 4).

Write-through Redis cache over the ``tenant_vehicles`` repository:

    - Key shape: ``vehicle_ownership:{vehicle_id}`` (global, not tenant-scoped — the lookup
      answers *who owns this vehicle*, the operator-level question the deployer needs).
    - TTL: 1 hour (short enough that a missed invalidation expires quickly; long enough
      that cache hit rate stays high under steady-state deployment traffic).
    - Failure-OPEN on Redis outage. The deployer falls back to Postgres on any Redis
      error (correctness gate, not security primitive — opposite posture from
      ADR-0008 Part 3's rate-limiter, which is failure-CLOSED).

Sits between ``collectmind.deployer.tenant_scope_check.validate_tenant_scope`` and the
authoritative ``TenantVehiclesRepository`` (Postgres ``tenant_vehicles`` table, ADR-0009
Part 1).
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

_CACHE_KEY_PREFIX = "vehicle_ownership:"
_CACHE_TTL_SECONDS = 3600  # ADR-0009 Part 4: 1 h


class _OwnershipRepoProto(Protocol):
    async def get_owner(self, vehicle_id: str) -> str | None: ...


class _AsyncRedisProto(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: str, ex: int) -> Any: ...
    async def delete(self, *keys: str) -> Any: ...


class OwnershipCache:
    """Write-through Redis cache over ``TenantVehiclesRepository.get_owner``.

    The Redis client and the repository are passed in. Production wiring builds them in
    ``app.py``'s lifespan; tests build them inline (host-side asyncpg + redis-py) or pass
    test doubles.
    """

    def __init__(self, *, redis_client: _AsyncRedisProto, repo: _OwnershipRepoProto) -> None:
        self._redis = redis_client
        self._repo = repo

    @staticmethod
    def _key(vehicle_id: str) -> str:
        return f"{_CACHE_KEY_PREFIX}{vehicle_id}"

    async def get_owner(self, vehicle_id: str) -> str | None:
        """Return the current owning tenant id for ``vehicle_id``, or ``None`` if unknown.

        Hit path: one Redis ``GET``, no Postgres call.
        Miss path: Redis ``GET`` returns ``None``, repo lookup runs, repo answer is written
            back to Redis with the canonical TTL, repo answer returned.
        Redis-outage path: any exception from ``redis.get`` falls through to the repo.
            The repo answer is returned; the write-back is skipped (the cache stays cold
            for this key — the next call retries the cache and may succeed).
        """
        key = self._key(vehicle_id)
        try:
            cached = await self._redis.get(key)
        except Exception as exc:
            logger.warning(
                "ownership_cache_redis_unavailable",
                error=str(exc),
                vehicle_id=vehicle_id,
            )
            return await self._repo.get_owner(vehicle_id)

        if cached is not None:
            return cached if isinstance(cached, str) else str(cached)

        owner = await self._repo.get_owner(vehicle_id)
        if owner is not None:
            try:
                await self._redis.set(key, owner, ex=_CACHE_TTL_SECONDS)
            except Exception as exc:
                # Write-back failure is non-fatal — the lookup answer is still authoritative.
                logger.warning(
                    "ownership_cache_writeback_failed",
                    error=str(exc),
                    vehicle_id=vehicle_id,
                )
        return owner

    async def invalidate(self, vehicle_id: str) -> None:
        """Drop the cache entry for ``vehicle_id``.

        Called by the service-principal write path that mutates ``tenant_vehicles``
        (ownership transition); without it, a cache hit keeps serving the pre-transition
        owner for up to one TTL window and the deployer denies legitimate deployments.
        """
        await self._redis.delete(self._key(vehicle_id))

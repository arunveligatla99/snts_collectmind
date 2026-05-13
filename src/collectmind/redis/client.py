"""Redis hot-store client wrapper.

Key shape (post Phase 14 T293 cleanup): ``tenant_id:vehicle_id:signal_name`` per
FR-018 + ADR-0008 Part 5. The feature-001 ``vehicle_id:signal_name`` shape is gone;
the dual-read fallback that bridged the migration window (Phase 11) has been removed
along with the ``HOT_STORE_LEGACY_FALLBACK_ENABLED`` env var.

Defense-in-depth: the legacy single-tenant ``get_signal`` / ``put_signal`` methods remain
on the class but always raise ``LegacyKeyShapeError`` (Fatal). Any pre-cutover caller
that survived the rollover sees a clear Fatal at call time rather than a silent
single-tenant read or write. The kept-for-defense pattern matches the constitution's
preference for structural enforcement over discipline.

User's Phase 11 watch-point 3 (still binding): RLS does NOT apply to Redis. Tenant
isolation in the hot store is enforced PURELY by key namespacing. ``_hot_store_key()``
is a PURE function with NO Redis connection, NO global state, and NO env-var lookups.
"""

from __future__ import annotations

from redis.asyncio import Redis as AsyncRedis

DEFAULT_TTL_SECONDS = 24 * 3600


def _hot_store_key(tenant_id: str, vehicle_id: str, signal_name: str) -> str:
    """Build a tenant-scoped hot-store key. PURE function (watch-point 3).

    NO Redis connection. NO global state. NO env-var lookups. The property test in T264
    exercises this function directly; any impurity breaks the structural-isolation contract
    that tenant isolation in the hot store rests on (RLS doesn't apply to Redis).
    """
    return f"{tenant_id}:{vehicle_id}:{signal_name}"


class LegacyKeyShapeError(RuntimeError):
    """Raised when a feature-001-era single-tenant hot-store API is called.

    Fatal error class per FR-020. The caller MUST NOT retry. Post Phase 14 T293
    cleanup: the legacy ``get_signal`` / ``put_signal`` methods raise this
    unconditionally (defense-in-depth — no code path should be reaching them).
    """


class HotStore:
    def __init__(self, url: str, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._url = url
        self._default_ttl = default_ttl
        self._client: AsyncRedis | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = AsyncRedis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        if self._client is None:
            return False
        result = await self._client.ping()
        return bool(result)

    # ─── Legacy single-tenant API (Phase 14 T293: Fatal-only) ──────────────────────
    # Kept on the class so any feature-001-era caller surfaces clearly. Calling either
    # method ALWAYS raises LegacyKeyShapeError; there is no longer an env-var gate.

    async def get_signal(self, vehicle_id: str, signal_name: str) -> str | None:
        raise LegacyKeyShapeError(
            f"legacy hot-store read attempted for {vehicle_id}:{signal_name}; "
            f"use get_signal_for_tenant(tenant_id, vehicle_id, signal_name) instead. "
            f"The legacy single-tenant API was removed in Phase 14 T293."
        )

    async def put_signal(self, vehicle_id: str, signal_name: str, value: str) -> None:
        raise LegacyKeyShapeError(
            f"legacy hot-store write attempted for {vehicle_id}:{signal_name}; "
            f"use put_signal_for_tenant(tenant_id, vehicle_id, signal_name, value) instead. "
            f"The legacy single-tenant API was removed in Phase 14 T293."
        )

    # ─── Feature 002 tenant-scoped API ─────────────────────────────────────────────

    async def put_signal_for_tenant(self, tenant_id: str, vehicle_id: str, signal_name: str, value: str) -> None:
        """Write a telemetry value under the tenant-scoped key shape (FR-018)."""
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        await self._client.set(_hot_store_key(tenant_id, vehicle_id, signal_name), value, ex=self._default_ttl)

    async def get_signal_for_tenant(self, tenant_id: str, vehicle_id: str, signal_name: str) -> str | None:
        """Read a telemetry value under the tenant-scoped key shape (FR-018).

        Post Phase 14 T293: reads the tenant-scoped key only; the legacy-shape fallback
        branch is gone. A miss returns ``None`` cleanly — there is no longer a parallel
        lookup against the legacy shape.
        """
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        value = await self._client.get(_hot_store_key(tenant_id, vehicle_id, signal_name))
        return str(value) if value is not None else None

    @property
    def client(self) -> AsyncRedis:
        """Direct access to the underlying redis-py client (used by ratelimit middleware)."""
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        return self._client

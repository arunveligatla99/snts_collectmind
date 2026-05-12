"""Redis hot-store client wrapper.

Feature 001 key shape: ``vehicle_id:signal_name`` (legacy; single-tenant).
Feature 002 key shape: ``tenant_id:vehicle_id:signal_name`` (per FR-018 + ADR-0008 Part 5).

The transition is a TTL-driven natural rollover (ADR-0008 Part 5):
    - Writers immediately switch to the new shape at deploy cutover.
    - Readers prefer the new shape; during the rollover window (24h existing TTL) they fall
      back to the legacy shape on cache miss. The fallback is gated by the env var
      ``HOT_STORE_LEGACY_FALLBACK_ENABLED``.
    - After the rollover window, ops sets the env var to ``false``. From that point any
      legacy-shape key observation raises ``LegacyKeyShapeError`` (Fatal) per FR-020.

User's Phase 11 watch-point 3: RLS does NOT apply to Redis. Tenant isolation in the hot
store is enforced PURELY by key namespacing. ``_hot_store_key()`` is a PURE function with
NO Redis connection, NO global state, and NO env-var lookups — the property test in T264
exercises it directly under hypothesis-generated tenant/vehicle/signal triples to enforce
the structural isolation contract.
"""

from __future__ import annotations

import os

from redis.asyncio import Redis as AsyncRedis

DEFAULT_TTL_SECONDS = 24 * 3600

# Env-var gate for the legacy-shape fallback branch (ADR-0008 Part 5). Read once per call so
# tests can toggle without restarting the process. The helper below isolates the read so
# the pure key-construction function stays env-free.
_LEGACY_FALLBACK_ENV = "HOT_STORE_LEGACY_FALLBACK_ENABLED"


def _legacy_fallback_enabled() -> bool:
    """Env-gated dual-read flag. Watch-point 2: the dual-read code has a deadline."""
    return os.environ.get(_LEGACY_FALLBACK_ENV, "true").lower() == "true"


def _hot_store_key(tenant_id: str, vehicle_id: str, signal_name: str) -> str:
    """Build a tenant-scoped hot-store key. PURE function (watch-point 3).

    NO Redis connection. NO global state. NO env-var lookups. The property test in T264
    exercises this function directly; any impurity breaks the structural-isolation contract
    that tenant isolation in the hot store rests on (RLS doesn't apply to Redis).
    """
    return f"{tenant_id}:{vehicle_id}:{signal_name}"


def _legacy_key(vehicle_id: str, signal_name: str) -> str:
    """Build the feature-001 legacy hot-store key. Same purity contract."""
    return f"{vehicle_id}:{signal_name}"


class LegacyKeyShapeError(RuntimeError):
    """Raised when a legacy-shape key is observed after the rollover window has closed.

    Fatal error class per FR-020. The caller MUST NOT retry; the audit dispatcher MUST log
    the attempt as a structured event. Lands in the orchestration-api logs and (via the
    error-class metric) in Prometheus.
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

    # ─── Feature 001 legacy API ────────────────────────────────────────────────────
    # The single-tenant calls. AFTER the rollover window closes
    # (HOT_STORE_LEGACY_FALLBACK_ENABLED=false), these methods raise LegacyKeyShapeError
    # to surface accidental regression.

    async def get_signal(self, vehicle_id: str, signal_name: str) -> str | None:
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        if not _legacy_fallback_enabled():
            raise LegacyKeyShapeError(
                f"legacy hot-store read attempted for {vehicle_id}:{signal_name} after "
                f"HOT_STORE_LEGACY_FALLBACK_ENABLED was disabled; use get_signal_for_tenant"
            )
        return await self._client.get(_legacy_key(vehicle_id, signal_name))

    async def put_signal(self, vehicle_id: str, signal_name: str, value: str) -> None:
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        if not _legacy_fallback_enabled():
            raise LegacyKeyShapeError(
                f"legacy hot-store write attempted for {vehicle_id}:{signal_name} after "
                f"HOT_STORE_LEGACY_FALLBACK_ENABLED was disabled; use put_signal_for_tenant"
            )
        await self._client.set(_legacy_key(vehicle_id, signal_name), value, ex=self._default_ttl)

    # ─── Feature 002 tenant-scoped API ─────────────────────────────────────────────
    # Writers ALWAYS use the new tenant-scoped shape. Readers prefer the new shape, fall
    # back to the legacy shape on miss during the rollover window per ADR-0008 Part 5.

    async def put_signal_for_tenant(self, tenant_id: str, vehicle_id: str, signal_name: str, value: str) -> None:
        """Write a telemetry value under the tenant-scoped key shape (FR-018).

        Writers ALWAYS use the new shape from deploy cutover. The legacy key is never
        written by tenant-aware callers; if any legacy key exists in production it was
        written by a pre-cutover orchestration-api and will expire naturally at the TTL.
        """
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        await self._client.set(_hot_store_key(tenant_id, vehicle_id, signal_name), value, ex=self._default_ttl)

    async def get_signal_for_tenant(self, tenant_id: str, vehicle_id: str, signal_name: str) -> str | None:
        """Read a telemetry value under the tenant-scoped key shape.

        Watch-point 2: new-shape FIRST, then legacy-shape on miss. Reverse order would
        defeat the rollover by always preferring stale data.

        During the rollover window (HOT_STORE_LEGACY_FALLBACK_ENABLED=true), a new-shape
        miss falls back to the legacy shape. The legacy fallback returns whatever value
        the pre-cutover writer left there — note that fallback is by vehicle_id+signal
        only, with NO tenant context (this is the documented cost of the rollover window
        per ADR-0008 Part 5; the gap is bounded by the 24h TTL).
        """
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        # Step 1 (new-shape FIRST): tenant-scoped key.
        new_shape_key = _hot_store_key(tenant_id, vehicle_id, signal_name)
        value = await self._client.get(new_shape_key)
        if value is not None:
            return str(value)
        # Step 2: legacy-shape fallback on miss. Gated by env var.
        if _legacy_fallback_enabled():
            legacy_value = await self._client.get(_legacy_key(vehicle_id, signal_name))
            if legacy_value is not None:
                return str(legacy_value)
            return None
        # After rollover window: legacy fallback disabled. If a legacy key still exists
        # for the vehicle/signal pair, that's a Fatal regression — raise.
        legacy_value = await self._client.get(_legacy_key(vehicle_id, signal_name))
        if legacy_value is not None:
            raise LegacyKeyShapeError(
                f"legacy-shape key observed for {vehicle_id}:{signal_name} after rollover "
                f"window closed (HOT_STORE_LEGACY_FALLBACK_ENABLED=false). Phase 14 cleanup "
                f"PR (T293) is pending or production has stale legacy keys that survived "
                f"the TTL window."
            )
        return None

    async def get_signal_for_tenant_strict(self, tenant_id: str, vehicle_id: str, signal_name: str) -> str | None:
        """Strict variant: ALWAYS raises if a legacy-shape key exists for this
        ``(vehicle_id, signal_name)`` pair, regardless of the env var. Used by callers that
        want explicit post-rollover hygiene checks (e.g., the Phase 14 sweep that asserts
        no legacy-shape keys remain).
        """
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        legacy_value = await self._client.get(_legacy_key(vehicle_id, signal_name))
        if legacy_value is not None:
            raise LegacyKeyShapeError(
                f"legacy-shape key observed in strict-read for {vehicle_id}:{signal_name}; "
                f"caller asked for the strict-mode invariant. Remove the legacy key or run "
                f"the Phase 14 cleanup sweep."
            )
        value = await self._client.get(_hot_store_key(tenant_id, vehicle_id, signal_name))
        return str(value) if value is not None else None

    @property
    def client(self) -> AsyncRedis:
        """Direct access to the underlying redis-py client (used by ratelimit middleware)."""
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        return self._client

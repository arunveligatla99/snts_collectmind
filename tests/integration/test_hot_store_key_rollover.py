"""T265: TTL-driven natural rollover from legacy key shape to tenant-scoped shape.

Asserts ADR-0008 Part 5: writers immediately switch to the new key shape at deploy
cutover; readers prefer the new shape and fall back to the legacy shape during the
existing TTL window. Legacy keys expire naturally.

User's Phase 11 watch-point 1 (load-bearing): "Pure flag-flip-on-cutover loses recent
data." Without a dual-read window, every read against a pre-cutover-written value
returns a cache miss until the writer re-populates. The dual-read window covers the
gap.

User's Phase 11 watch-point 2: "The dual-read code needs a deadline." The
``HOT_STORE_LEGACY_FALLBACK_ENABLED`` env var gates the fallback; after the 24h TTL
elapses, ops sets it to ``false`` and the legacy-shape fallback path becomes Fatal
(per T270). Phase 14 ships the one-time-cleanup PR that removes the branch entirely.

Red phase: Phase 11.b T267 + T268 pending. The hot_store.py rewrite hasn't landed; the
test fails because the dual-shape read path doesn't exist.

Anchors: ADR-0008 Part 5 / FR-019 / Principle IV.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from redis.asyncio import Redis as AsyncRedis

from collectmind.redis.client import HotStore

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def hot_store() -> HotStore:
    store = HotStore(REDIS_URL)
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def raw_redis() -> AsyncRedis:
    client = AsyncRedis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_reader_prefers_new_shape_when_both_present(hot_store: HotStore, raw_redis: AsyncRedis) -> None:
    """If both shapes exist for the same logical key, reader returns the new-shape value."""
    # Pre-seed legacy-shape key directly.
    await raw_redis.set("VIN-ROLLOVER:Vehicle.Speed", "legacy-value", ex=60)
    # Write the same logical key under the new shape via the tenant-scoped API.
    await hot_store.put_signal_for_tenant("tenant-rollover", "VIN-ROLLOVER", "Vehicle.Speed", "new-value")
    # Reader for tenant-rollover MUST see the new-shape value.
    result = await hot_store.get_signal_for_tenant("tenant-rollover", "VIN-ROLLOVER", "Vehicle.Speed")
    assert result == "new-value", (
        f"ADR-0008 Part 5 violation: reader should prefer new-shape over legacy; got {result!r}"
    )


@pytest.mark.asyncio
async def test_reader_falls_back_to_legacy_during_rollover(hot_store: HotStore, raw_redis: AsyncRedis) -> None:
    """During the rollover window (HOT_STORE_LEGACY_FALLBACK_ENABLED=true), a read for a
    new-shape miss MUST fall back to the legacy shape.
    """
    os.environ["HOT_STORE_LEGACY_FALLBACK_ENABLED"] = "true"
    await raw_redis.set("VIN-FALLBACK:Vehicle.Speed", "legacy-only", ex=60)
    # No new-shape key written. Reader for ANY tenant SHOULD fall back to the legacy
    # key during the rollover window. (The fallback is by vehicle_id+signal only; it has
    # no tenant context — that's the price of the rollover window.)
    result = await hot_store.get_signal_for_tenant("tenant-rollover-2", "VIN-FALLBACK", "Vehicle.Speed")
    assert result == "legacy-only", (
        f"ADR-0008 Part 5 violation: legacy-shape fallback failed during rollover window; "
        f"got {result!r}"
    )


@pytest.mark.asyncio
async def test_legacy_keys_expire_naturally(hot_store: HotStore, raw_redis: AsyncRedis) -> None:
    """Legacy keys carry the existing TTL (24h in production; 2s here for testability)."""
    await raw_redis.set("VIN-EXPIRE:Vehicle.Speed", "transient", ex=2)
    # Immediately readable via fallback.
    os.environ["HOT_STORE_LEGACY_FALLBACK_ENABLED"] = "true"
    assert await hot_store.get_signal_for_tenant("any-tenant", "VIN-EXPIRE", "Vehicle.Speed") == "transient"
    # After TTL, the legacy key is gone.
    await asyncio.sleep(3)
    assert await hot_store.get_signal_for_tenant("any-tenant", "VIN-EXPIRE", "Vehicle.Speed") is None


@pytest.fixture(scope="module")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

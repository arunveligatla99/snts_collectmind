"""T266: legacy-shape refused post-rollover.

Asserts FR-020: after the rollover window closes (``HOT_STORE_LEGACY_FALLBACK_ENABLED=false``,
T270 guard active), any code path that observes a legacy-shape key MUST raise a Fatal
error class and audit the attempt. The guard prevents accidental regression after the
24h+epsilon TTL window elapses.

User's Phase 11 watch-point 2: the dual-read code has a deadline. This test enforces
the deadline by simulating the post-rollover state (env var toggled to ``false``) and
asserting that any legacy-shape access raises rather than silently allows.

Red phase: Phase 11.b T270 (Fatal-error guard) pending. Without it, reads against
legacy-shape keys either return None silently (if no legacy key exists) or return the
legacy value (if one happens to still exist). Both violate FR-020.

Anchors: FR-020 / Principle X / Principle IV.
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
async def test_legacy_key_read_refused_post_rollover(hot_store: HotStore, raw_redis: AsyncRedis) -> None:
    """With HOT_STORE_LEGACY_FALLBACK_ENABLED=false, the reader MUST raise on legacy keys.

    Setup: a legacy-shape key exists (e.g., a key that wasn't migrated and somehow survived
    past the rollover window). With the guard active, reading it MUST raise
    ``LegacyKeyShapeError`` (Fatal) and the failure MUST be audited.
    """
    os.environ["HOT_STORE_LEGACY_FALLBACK_ENABLED"] = "false"
    await raw_redis.set("VIN-POST-ROLLOVER:Vehicle.Speed", "should-not-be-read", ex=60)
    try:
        from collectmind.redis.client import LegacyKeyShapeError  # type: ignore[attr-defined]
    except ImportError:
        pytest.fail(
            "Phase 11.b T270 has not landed: LegacyKeyShapeError class missing from "
            "collectmind.redis.client. Required by FR-020 to surface accidental legacy-shape "
            "access after the rollover window."
        )
    with pytest.raises(LegacyKeyShapeError):
        await hot_store.get_signal_for_tenant_strict(
            "tenant-post-rollover", "VIN-POST-ROLLOVER", "Vehicle.Speed"
        )


@pytest.mark.asyncio
async def test_legacy_key_write_refused_post_rollover(hot_store: HotStore) -> None:
    """The write path also rejects the legacy shape post-rollover (defense in depth)."""
    os.environ["HOT_STORE_LEGACY_FALLBACK_ENABLED"] = "false"
    try:
        from collectmind.redis.client import LegacyKeyShapeError  # type: ignore[attr-defined]
    except ImportError:
        pytest.fail("LegacyKeyShapeError missing (T270 pending)")
    # The legacy write API (put_signal without tenant_id) MUST raise post-rollover.
    with pytest.raises(LegacyKeyShapeError):
        await hot_store.put_signal("VIN-NEVER-WRITE", "Vehicle.Speed", "denied")


@pytest.fixture(scope="module")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

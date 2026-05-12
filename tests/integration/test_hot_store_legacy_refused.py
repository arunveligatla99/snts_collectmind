"""T266 (Phase 11) + T293 (Phase 14): legacy single-tenant hot-store API always raises.

Post Phase 14 T293 cleanup the legacy ``get_signal`` / ``put_signal`` methods raise
``LegacyKeyShapeError`` unconditionally — the ``HOT_STORE_LEGACY_FALLBACK_ENABLED``
env-var gate is gone. The class keeps the methods on the surface as a Fatal-only
defense-in-depth guard: any pre-cutover caller that survived the rollover surfaces
clearly at call time.

This test asserts:
    1. ``HotStore.get_signal(...)`` raises ``LegacyKeyShapeError`` (no env-var
       manipulation required; the Fatal is unconditional).
    2. ``HotStore.put_signal(...)`` raises ``LegacyKeyShapeError`` (same).
    3. ``HotStore.get_signal_for_tenant_strict`` is GONE — the import fails.

Anchors: FR-020 / Principle X / Principle IV / ADR-0008 Part 5.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from collectmind.redis.client import HotStore, LegacyKeyShapeError

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def hot_store() -> HotStore:
    store = HotStore(REDIS_URL)
    await store.connect()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_legacy_get_signal_always_raises(hot_store: HotStore) -> None:
    """Post Phase 14 cleanup: ``get_signal`` raises ``LegacyKeyShapeError`` on any call."""
    with pytest.raises(LegacyKeyShapeError):
        await hot_store.get_signal("VIN-LEGACY", "Vehicle.Speed")


@pytest.mark.asyncio
async def test_legacy_put_signal_always_raises(hot_store: HotStore) -> None:
    """Post Phase 14 cleanup: ``put_signal`` raises ``LegacyKeyShapeError`` on any call."""
    with pytest.raises(LegacyKeyShapeError):
        await hot_store.put_signal("VIN-LEGACY", "Vehicle.Speed", "value")


def test_strict_variant_removed_post_cleanup() -> None:
    """Phase 14 T293 removes ``get_signal_for_tenant_strict``; the only tenant-scoped read
    API is now ``get_signal_for_tenant``. A future caller using the old name MUST fail
    at attribute-access time."""
    assert not hasattr(HotStore, "get_signal_for_tenant_strict"), (
        "Phase 14 T293 cleanup did not remove get_signal_for_tenant_strict; the variant "
        "is redundant post-rollover and must not exist on the class surface."
    )


@pytest.fixture(scope="module")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

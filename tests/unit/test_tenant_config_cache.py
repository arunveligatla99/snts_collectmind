"""T248: tenant_config cache reload via LISTEN/NOTIFY.

Asserts ADR-0008 Part 4: in-process LRU cache with a 5-second TTL plus a Postgres
``LISTEN tenant_config_changed`` subscriber that invalidates the named tenant's cache
entry within 1 second of the configuration write.

Two assertions:
    1. TTL fallback — cache entry expires within 5 seconds even without a NOTIFY signal
       (the safety net for NOTIFY-pipeline failures: asyncpg reconnect, backlog overflow).
    2. NOTIFY-driven invalidation — within 1 second of an INSERT/UPDATE/DELETE on
       tenant_config, the cache entry for that tenant is invalidated. Phase 10.b T256
       wires the asyncio LISTEN consumer.

Red phase: Phase 10.b T256 (config_cache.py LISTEN consumer) hasn't landed. Tests fail
because the consumer doesn't subscribe to NOTIFY events; cache only expires via TTL.

Anchors: ADR-0008 Part 4 / Principle IV.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

# Import the existing TenantConfigRepository from Phase 9.b. The LISTEN-consumer extension
# lands in Phase 10.b T256.
from collectmind.registry.tenant_config import _TTLCache

pytestmark = pytest.mark.asyncio


def test_ttl_cache_expires_within_five_seconds() -> None:
    """Synchronous TTL fallback works even if NOTIFY pipeline is silent."""
    cache = _TTLCache(ttl_seconds=0.5, capacity=4)
    from collectmind.registry.tenant_config import (
        RateLimitBucket,
        TenantConfig,
    )

    config = TenantConfig(
        tenant_id="t-a",
        inbound=RateLimitBucket(2000, 4000),
        query=RateLimitBucket(200, 400),
        source="override",
    )
    cache.put("t-a", config)
    assert cache.get("t-a") is not None, "fresh put should be readable"
    time.sleep(0.6)
    assert cache.get("t-a") is None, "TTL-expired entry must not be returned"


def test_ttl_cache_invalidate_drops_entry() -> None:
    """Explicit ``invalidate(tenant_id)`` (called by the NOTIFY consumer in T256) clears."""
    cache = _TTLCache(ttl_seconds=60.0)
    from collectmind.registry.tenant_config import RateLimitBucket, TenantConfig

    config = TenantConfig(
        tenant_id="t-x",
        inbound=RateLimitBucket(2000, 4000),
        query=RateLimitBucket(200, 400),
        source="override",
    )
    cache.put("t-x", config)
    assert cache.get("t-x") is not None
    cache.invalidate("t-x")
    assert cache.get("t-x") is None, "after invalidate(), entry must be absent"


@pytest.mark.asyncio
async def test_listen_notify_consumer_exists_in_config_cache_module() -> None:
    """Phase 10.b T256 ships ``ratelimit/config_cache.py`` with a LISTEN consumer.

    The consumer:
        - Subscribes to Postgres ``LISTEN tenant_config_changed``.
        - On NOTIFY, invokes ``TenantConfigRepository.invalidate(tenant_id)``.
        - Reconnects on asyncpg connection loss; the 5-second TTL covers the reconnect
          window so stale entries can't persist longer than the TTL.

    Red phase: module ``collectmind.ratelimit.config_cache`` does not have a public
    ``TenantConfigCacheConsumer`` (or equivalent) class. Test fails with ImportError.
    """
    config_cache_module = Path(__file__).resolve().parents[2] / "src" / "collectmind" / "ratelimit" / "config_cache.py"
    assert config_cache_module.exists(), f"Phase 10.b T256 has not landed: {config_cache_module} missing"
    # Try to import the LISTEN consumer. The exact name is implementation-detail; the test
    # accepts any of a few common shapes that the Phase-10.b impl might pick.
    try:
        from collectmind.ratelimit import config_cache  # type: ignore
    except ImportError as exc:
        pytest.fail(f"cannot import collectmind.ratelimit.config_cache: {exc}")
    candidate_names = ("TenantConfigCacheConsumer", "ConfigCacheConsumer", "ListenConsumer")
    available = [name for name in candidate_names if hasattr(config_cache, name)]
    assert available, (
        f"Phase 10.b T256 violation: collectmind.ratelimit.config_cache must export one of "
        f"{candidate_names!r} (the LISTEN tenant_config_changed consumer); module exports: "
        f"{dir(config_cache)}"
    )


@pytest.mark.asyncio
async def test_notify_invalidation_within_one_second() -> None:
    """End-to-end NOTIFY → cache invalidation within 1 s. Requires running Postgres."""
    pytest.skip(
        "Phase 10.b integration test: requires the orchestration-api's config_cache "
        "consumer to be running. Will be replaced by an integration-tier test under "
        "tests/integration/ once T256 + T258 land."
    )
    # The full integration test will:
    #   1. Read config for tenant-a (populates cache).
    #   2. UPDATE tenant_config for tenant-a as service-principal.
    #   3. Within 1s, observe the cache entry is gone.
    # Asyncio overhead + LISTEN delivery latency = ~50-200ms in practice; budget is 1s.
    await asyncio.sleep(0)

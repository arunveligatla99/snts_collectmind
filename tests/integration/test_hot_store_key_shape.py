"""T264: hot-store tenant-scoped key shape.

Asserts FR-018: every hot-store telemetry entry MUST be keyed under
``tenant_id:vehicle_id:signal_name`` so two tenants writing to the same vehicle identifier
and signal name cannot collide.

User's Phase 11 watch-point 3 (load-bearing): **RLS does not apply to Redis.** Tenant
isolation in the hot store is enforced PURELY by key namespacing. A bug in key construction
is a cross-tenant data leak with no DB-level safety net. The property test below exercises
the key-construction function under hypothesis-generated tenant/vehicle/signal triples and
asserts that any key constructed from tenant A's context CANNOT be read using tenant B's
context, for ANY input combination.

Red phase: Phase 11.b T267/T268/T269 (hot_store.py + key-shape change) hasn't landed. The
existing ``get_signal(vehicle_id, signal_name)`` / ``put_signal(vehicle_id, signal_name, value)``
API doesn't accept a tenant_id parameter; test fails with TypeError on the call signature.

Anchors: FR-018 / Principle X / Principle IV.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collectmind.redis.client import HotStore

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def hot_store() -> HotStore:
    store = HotStore(REDIS_URL)
    await store.connect()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_set_get_round_trip_with_tenant_scoping(hot_store: HotStore) -> None:
    """Tenant-A writes a value; tenant-A reads back; tenant-B reads cache-miss."""
    await hot_store.put_signal_for_tenant("tenant-a", "VIN-COLLISION-1", "Vehicle.Speed", "42.5")
    a_value = await hot_store.get_signal_for_tenant("tenant-a", "VIN-COLLISION-1", "Vehicle.Speed")
    assert a_value == "42.5", f"tenant-a write/read round trip failed; got {a_value}"

    b_value = await hot_store.get_signal_for_tenant("tenant-b", "VIN-COLLISION-1", "Vehicle.Speed")
    assert b_value is None, (
        f"FR-018 violation: tenant-b read tenant-a's value at the same vehicle_id+signal "
        f"({b_value!r}); cross-tenant collision under shared VIN."
    )


@pytest.mark.asyncio
async def test_cross_tenant_no_collision_on_same_vin(hot_store: HotStore) -> None:
    """Both tenants write to same VIN+signal with different values; each reads OWN value."""
    await hot_store.put_signal_for_tenant("tenant-a", "VIN-COLLISION-2", "Vehicle.Speed", "10")
    await hot_store.put_signal_for_tenant("tenant-b", "VIN-COLLISION-2", "Vehicle.Speed", "999")
    assert await hot_store.get_signal_for_tenant("tenant-a", "VIN-COLLISION-2", "Vehicle.Speed") == "10"
    assert await hot_store.get_signal_for_tenant("tenant-b", "VIN-COLLISION-2", "Vehicle.Speed") == "999"


@pytest.mark.asyncio
async def test_key_carries_tenant_prefix(hot_store: HotStore) -> None:
    """Verify the on-disk Redis key shape directly. FR-018: tenant_id MUST be the prefix."""
    await hot_store.put_signal_for_tenant("tenant-prefix-test", "VIN-X", "Vehicle.Speed", "1.0")
    # Inspect via the underlying client.
    keys = await hot_store.client.keys("*tenant-prefix-test*")
    assert any(
        "tenant-prefix-test:VIN-X:Vehicle.Speed" in key for key in keys
    ), f"FR-018 violation: expected key 'tenant-prefix-test:VIN-X:Vehicle.Speed' in keyspace; got {keys!r}"


# ─── Property test (user watch-point 3) ─────────────────────────────────────────
# Any key constructed from tenant A's context MUST NOT be readable from tenant B's
# context, for ANY input combination of tenant/vehicle/signal. This is the structural
# isolation contract that the test bar enforces because RLS doesn't apply to Redis.

_SAFE_SEGMENT = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-."),
    min_size=1,
    max_size=32,
)


@given(
    tenant_a=_SAFE_SEGMENT,
    tenant_b=_SAFE_SEGMENT,
    vehicle_id=_SAFE_SEGMENT,
    signal=_SAFE_SEGMENT,
)
@settings(max_examples=30, deadline=None)
def test_property_cross_tenant_key_isolation(tenant_a: str, tenant_b: str, vehicle_id: str, signal: str) -> None:
    """For every (tenant_a, tenant_b, vehicle, signal) where tenant_a != tenant_b, the
    hot-store key constructed from tenant_a's context MUST differ from the key constructed
    from tenant_b's context — even when vehicle_id + signal are identical.

    This is the structural isolation contract: a key collision implies a cross-tenant data
    leak, with no DB-level safety net (Redis has no RLS). The function under test is the
    key-construction helper from hot_store.py.
    """
    if tenant_a == tenant_b:
        return  # Same tenant; no cross-tenant property to assert.
    # The function is Phase 11.b T267's responsibility; import lazily.
    try:
        from collectmind.redis.client import _hot_store_key  # type: ignore[attr-defined]
    except ImportError:
        pytest.fail(
            "Phase 11.b T267 has not landed: _hot_store_key helper missing from "
            "collectmind.redis.client. Key-construction must be a pure function so the "
            "structural isolation property is testable."
        )
    key_a = _hot_store_key(tenant_a, vehicle_id, signal)
    key_b = _hot_store_key(tenant_b, vehicle_id, signal)
    assert key_a != key_b, (
        f"FR-018 + watch-point 3 violation: key collision across tenants "
        f"({tenant_a!r} vs {tenant_b!r}) on (vehicle={vehicle_id!r}, signal={signal!r}). "
        f"Both keys = {key_a!r}. Tenant isolation in Redis is purely by key namespacing; "
        f"a collision here is a cross-tenant data leak with no DB safety net."
    )


# Allow running the async-fixture tests without loop fixture explicitness.
@pytest.fixture(scope="module")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

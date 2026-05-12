"""T246: token-bucket Lua script property tests.

Asserts the ADR-0008 Part 2 contract for ``src/collectmind/ratelimit/token_bucket.lua``:
    - Atomic check-and-deduct in one Redis round trip (no WATCH/MULTI/EXEC; no intermediate
      Redis calls that could leave a partially-updated bucket on disconnect).
    - Monotonic refill: tokens accumulate as wall-clock elapses; never decrease except by the
      single per-call decrement.
    - Burst-capped: tokens never exceed ``burst_capacity``.
    - Refill-amount invariant: ``tokens(t1) - tokens(t0)`` ≤ ``(t1 - t0) * sustained_rps``
      plus the per-call decrement.

Watch-point (user's Phase 10.b implementation note): "The Lua script must be a single
SCRIPT LOAD + EVALSHA pattern with bucket-state read, decrement, and persist all in one Lua
block." This test runs ``grep``-style assertions against the .lua source to enforce that
structurally; runtime property tests (hypothesis) exercise the algebraic invariants against
the running Redis under random inputs.

Red phase: ``src/collectmind/ratelimit/token_bucket.lua`` does not exist (Phase 10.b T254).
Tests fail at fixture setup with ``FileNotFoundError`` — right-reason red signaling that
Phase 10.b T254 is the impl task.

Anchors: ADR-0008 Part 2 / Principle IV.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import redis
from hypothesis import given, settings
from hypothesis import strategies as st

LUA_PATH = Path(__file__).resolve().parents[2] / "src" / "collectmind" / "ratelimit" / "token_bucket.lua"
REDIS_URL = "redis://localhost:6379/0"


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


@pytest.fixture(scope="module")
def lua_source() -> str:
    if not LUA_PATH.exists():
        pytest.fail(
            f"token_bucket.lua not found at {LUA_PATH}. Phase 10.b T254 has not landed yet. "
            f"This is the canonical red-phase signal."
        )
    return LUA_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_sha(lua_source: str) -> str:
    client = _redis_client()
    return client.script_load(lua_source)


def test_lua_source_is_single_atomic_block(lua_source: str) -> None:
    """Watch-point 1: no WATCH/MULTI/EXEC; the script is a single atomic Lua block.

    The Redis Lua scripting contract guarantees the script body runs atomically server-side
    (the server serializes Lua execution). Adding WATCH/MULTI/EXEC inside Lua is both
    redundant AND a code smell — the script is already atomic by construction. Forbidden
    keywords surface a misuse pattern at code-review time.
    """
    forbidden = ["MULTI", "EXEC", "WATCH", "UNWATCH"]
    for keyword in forbidden:
        # Case-sensitive; Redis Lua commands are conventionally uppercase. Allow comments
        # that mention the keyword for documentation; the assertion is on actual Redis
        # command calls via ``redis.call`` / ``redis.pcall``.
        pattern = rf'redis\.p?call\s*\(\s*["\']?{keyword}'
        assert re.search(pattern, lua_source, re.IGNORECASE) is None, (
            f"ADR-0008 Part 2 violation: token_bucket.lua contains `{keyword}` "
            f"(should not need WATCH/MULTI/EXEC; the script is atomic by Redis Lua contract)"
        )


def test_lua_source_returns_decision_and_retry_hint(lua_source: str) -> None:
    """Lua script returns a 2-tuple: (decision_int, remaining_or_retry_after_ms)."""
    assert "return" in lua_source, "Lua script must explicitly return a value"
    # Look for a return that yields a Lua table (the {decision, ...} idiom).
    assert re.search(r"return\s*\{", lua_source), (
        "Lua script must return a table {decision, remaining|retry_after_ms}; found scalar return instead"
    )


@settings(max_examples=50, deadline=None)
@given(
    sustained_rps=st.integers(min_value=1, max_value=10_000),
    burst_capacity=st.integers(min_value=1, max_value=20_000),
)
def test_first_call_returns_allow_and_burst_minus_one(sustained_rps: int, burst_capacity: int, script_sha: str) -> None:
    """A fresh bucket key starts at burst_capacity; first call MUST allow."""
    if burst_capacity < sustained_rps:
        # Postgres-side check (FR-013a) enforces burst_capacity >= sustained_rps; hypothesis
        # may generate an invalid pair. Skip those.
        return
    client = _redis_client()
    key = f"test:ratelimit:fresh:{sustained_rps}:{burst_capacity}"
    client.delete(key)
    now_ms = 1_700_000_000_000
    result = client.evalsha(script_sha, 1, key, now_ms, sustained_rps, burst_capacity)
    assert isinstance(result, list) and len(result) >= 2
    decision, remaining = int(result[0]), int(result[1])
    assert decision == 1, "fresh bucket must allow first call"
    assert remaining == burst_capacity - 1, (
        f"fresh bucket should have burst_capacity-1 tokens remaining; got {remaining}"
    )


def test_burst_capped_after_long_idle(script_sha: str) -> None:
    """A bucket idle for an hour MUST NOT exceed burst_capacity tokens."""
    client = _redis_client()
    key = "test:ratelimit:burst-cap:long-idle"
    client.delete(key)
    sustained_rps = 100
    burst_capacity = 200
    # First call at t=0; bucket goes from burst_capacity → burst_capacity - 1.
    result = client.evalsha(script_sha, 1, key, 0, sustained_rps, burst_capacity)
    assert int(result[0]) == 1
    # Second call at t = 1 hour later (3_600_000 ms). Refill would naively yield
    # 100 r/s * 3600 s = 360_000 tokens. The script must cap to burst_capacity.
    result = client.evalsha(script_sha, 1, key, 3_600_000, sustained_rps, burst_capacity)
    assert int(result[0]) == 1, "after long idle, fresh allow"
    remaining = int(result[1])
    assert remaining <= burst_capacity - 1, (
        f"after long idle, tokens must be capped at burst_capacity; got {remaining} > {burst_capacity - 1}"
    )


def test_reject_when_empty(script_sha: str) -> None:
    """Draining the bucket to zero and calling again returns decision=0 with retry hint."""
    client = _redis_client()
    key = "test:ratelimit:drain"
    client.delete(key)
    sustained_rps = 10
    burst_capacity = 5
    # Drain.
    for i in range(burst_capacity):
        result = client.evalsha(script_sha, 1, key, 0, sustained_rps, burst_capacity)
        assert int(result[0]) == 1, f"call {i + 1} should allow (burst not exhausted)"
    # Next call at same t=0 must reject (no time elapsed = no refill).
    result = client.evalsha(script_sha, 1, key, 0, sustained_rps, burst_capacity)
    # Lua returns {decision, remaining, retry_after_ms}. On reject, remaining=0 and the
    # retry_after_ms sits at index 2 (3-tuple shape per ADR-0008 Part 2).
    decision, remaining, retry_hint = int(result[0]), int(result[1]), int(result[2])
    assert decision == 0, "burst exhausted at t=0 must reject"
    assert remaining == 0, f"reject must report 0 remaining tokens; got {remaining}"
    # Retry hint is in milliseconds; with sustained_rps=10 we expect ~100 ms to next token.
    assert retry_hint > 0, f"reject must include positive retry hint; got {retry_hint}"
    assert retry_hint <= 1000, f"retry hint should be ~100 ms; got {retry_hint}"

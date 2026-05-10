"""T059: Composite-key idempotency on duplicate findings (FR-012, Clarifications Q1).

Unit-tier coverage of the idempotency check. The integration-tier coverage of the same
behavior lives in tests/integration/test_idempotency_integration.py (T063).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def checker():
    from collectmind.ingest.idempotency import IdempotencyChecker

    return IdempotencyChecker.in_memory()


@pytest.mark.asyncio
async def test_first_publication_returns_first_seen(checker) -> None:
    decision = await checker.check_or_record("feature-001-default", "F-001", payload_sha=b"x" * 32)
    assert decision.first_seen is True


@pytest.mark.asyncio
async def test_second_publication_returns_replay(checker) -> None:
    await checker.check_or_record("feature-001-default", "F-001", payload_sha=b"x" * 32)
    decision = await checker.check_or_record("feature-001-default", "F-001", payload_sha=b"x" * 32)
    assert decision.first_seen is False
    assert decision.idempotent_replay is True


@pytest.mark.asyncio
async def test_different_tenant_same_finding_id_is_first_seen(checker) -> None:
    await checker.check_or_record("tenant-a", "F-001", payload_sha=b"x" * 32)
    decision = await checker.check_or_record("tenant-b", "F-001", payload_sha=b"x" * 32)
    assert decision.first_seen is True


@pytest.mark.asyncio
async def test_different_payload_same_key_flagged(checker) -> None:
    """A re-publication with a different payload SHA is a contract violation."""
    await checker.check_or_record("feature-001-default", "F-001", payload_sha=b"x" * 32)
    decision = await checker.check_or_record("feature-001-default", "F-001", payload_sha=b"y" * 32)
    assert decision.first_seen is False
    assert decision.payload_changed is True

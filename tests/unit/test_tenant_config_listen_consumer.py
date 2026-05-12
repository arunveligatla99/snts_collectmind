"""T285 coverage sweep: unit tests for the TenantConfigCacheConsumer (LISTEN/NOTIFY)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectmind.ratelimit.config_cache import (
    NOTIFY_CHANNEL,
    TenantConfigCacheConsumer,
)


def _repo_double() -> MagicMock:
    repo = MagicMock()
    repo.invalidate = MagicMock()
    return repo


@pytest.mark.asyncio
async def test_start_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling start() twice does not spawn a second task."""

    async def _never_ready() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(
        "collectmind.ratelimit.config_cache.asyncpg.connect",
        AsyncMock(side_effect=lambda dsn=None: _ConnDouble()),
    )

    consumer = TenantConfigCacheConsumer("postgresql://x", _repo_double())
    await consumer.start()
    task_after_first = consumer._task  # type: ignore[attr-defined]
    await consumer.start()
    assert consumer._task is task_after_first  # type: ignore[attr-defined]
    await consumer.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task_and_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """stop() cancels the consumer task and closes the asyncpg connection."""
    conn = _ConnDouble()
    monkeypatch.setattr(
        "collectmind.ratelimit.config_cache.asyncpg.connect",
        AsyncMock(return_value=conn),
    )
    consumer = TenantConfigCacheConsumer("postgresql://x", _repo_double())
    await consumer.start()
    await asyncio.sleep(0.05)  # let _run_forever connect
    await consumer.stop()
    assert consumer._task is None  # type: ignore[attr-defined]


def test_on_notify_invalidates_named_tenant() -> None:
    """A NOTIFY payload carrying a tenant_id MUST invalidate that tenant's cache entry."""
    repo = _repo_double()
    consumer = TenantConfigCacheConsumer("postgresql://x", repo)
    consumer._on_notify(None, 0, NOTIFY_CHANNEL, "tenant-a")  # type: ignore[arg-type]
    repo.invalidate.assert_called_once_with("tenant-a")


def test_on_notify_ignores_empty_payload() -> None:
    """An empty payload (system-generated NOTIFY) MUST be a no-op."""
    repo = _repo_double()
    consumer = TenantConfigCacheConsumer("postgresql://x", repo)
    consumer._on_notify(None, 0, NOTIFY_CHANNEL, "")  # type: ignore[arg-type]
    repo.invalidate.assert_not_called()


class _ConnDouble:
    """asyncpg.Connection double; supports add_listener + is_closed + close."""

    def __init__(self) -> None:
        self._closed = False
        self.listeners: list[str] = []

    async def add_listener(self, channel: str, _handler: object) -> None:
        self.listeners.append(channel)

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

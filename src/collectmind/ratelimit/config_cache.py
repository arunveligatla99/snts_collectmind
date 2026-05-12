"""Tenant_config LISTEN/NOTIFY consumer (feature 002 / T256 / ADR-0008 Part 4).

Background asyncio task that subscribes to Postgres ``LISTEN tenant_config_changed``
and invalidates the named tenant's entry in the in-process ``TenantConfigRepository``
cache when a configuration write is committed.

The combination of NOTIFY (sub-second responsiveness) + the 5-second TTL on the cache
(safety net for NOTIFY-pipeline failures) gives operators "push + pull fallback"
semantics. NOTIFY drops the cache entry; the next request from that tenant fetches
the fresh value from Postgres.

ADR-0008 Part 4 is the authoritative design.
"""

from __future__ import annotations

import asyncio

import asyncpg
import structlog

from collectmind.registry.tenant_config import TenantConfigRepository

logger = structlog.get_logger(__name__)

NOTIFY_CHANNEL = "tenant_config_changed"


class TenantConfigCacheConsumer:
    """Background asyncio consumer for the LISTEN tenant_config_changed channel.

    Lifecycle:
        ``await consumer.start()`` connects + LISTEN; spawns the consume loop.
        ``await consumer.stop()`` cancels the task + closes the connection.

    Reconnect behavior: if the connection drops, the consumer logs the error and
    reconnects with exponential backoff (1s, 2s, 4s, ..., capped at 30s). During the
    reconnect window the cache TTL covers stale entries.
    """

    def __init__(self, dsn: str, repo: TenantConfigRepository) -> None:
        self._dsn = dsn
        self._repo = repo
        self._conn: asyncpg.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run_forever(), name="tenant-config-listener")
        logger.info("tenant_config_listener_started", channel=NOTIFY_CHANNEL)

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception) as exc:
                if not isinstance(exc, asyncio.CancelledError):
                    logger.warning("tenant_config_listener_stop_error", error=str(exc))
            self._task = None
        if self._conn is not None and not self._conn.is_closed():
            await self._conn.close()
            self._conn = None

    async def _run_forever(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                self._conn = await asyncpg.connect(dsn=self._dsn)
                await self._conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
                logger.info("tenant_config_listener_connected", channel=NOTIFY_CHANNEL)
                backoff = 1.0
                # Park here until cancelled; asyncpg invokes _on_notify out-of-band.
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "tenant_config_listener_disconnected",
                    error=str(exc),
                    backoff_seconds=backoff,
                )
                if self._conn is not None and not self._conn.is_closed():
                    try:
                        await self._conn.close()
                    except Exception as close_exc:
                        logger.warning("tenant_config_listener_close_error", error=str(close_exc))
                    self._conn = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        if not payload:
            return
        self._repo.invalidate(payload)
        logger.info("tenant_config_invalidated", tenant_id=payload)

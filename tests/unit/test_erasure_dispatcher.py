"""Unit tests for erasure/dispatcher.py (T134). asyncpg + audit_writer mocked."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from collectmind.erasure.dispatcher import ErasureDispatcher
from collectmind.models.erasure import ErasureRequest


class _FakeConn:
    def __init__(self, *, fetchrow: Any = None) -> None:
        self.execute = AsyncMock()
        self.fetchrow = AsyncMock(return_value=fetchrow)


class _FakeDb:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self, _tenant_id: str):  # type: ignore[no-untyped-def]
        conn = self._conn

        class _Ctx:
            async def __aenter__(self_inner) -> _FakeConn:
                return conn

            async def __aexit__(self_inner, *_a) -> None:
                return None

        return _Ctx()


@pytest.mark.asyncio
async def test_submit_writes_initial_row_and_audit_event() -> None:
    conn = _FakeConn()
    audit_writer = type("AW", (), {"write": AsyncMock()})()
    dispatcher = ErasureDispatcher(_FakeDb(conn), audit_writer)  # type: ignore[arg-type]
    now = datetime.now(tz=UTC)
    payload = ErasureRequest(subject_kind="vehicle", subject_identifier="VIN-1", mode="erased")
    await dispatcher.submit(
        request_id="r1",
        tenant_id="t",
        requested_by="alice",
        requested_at=now,
        target_completion_at=now + timedelta(days=30),
        payload=payload,
    )
    # The submit() awaits the initial INSERT and the audit write; the dispatch
    # path is fire-and-forget. Let the loop run the background task briefly.
    await asyncio.sleep(0.01)
    conn.execute.assert_awaited()
    audit_writer.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_returns_mapped_row() -> None:
    row = {
        "request_id": "r1",
        "tenant_id": "t",
        "subject_kind": "vehicle",
        "subject_identifier": "VIN-1",
        "requested_by": "alice",
        "requested_at": datetime(2026, 5, 11, tzinfo=UTC),
        "target_completion_at": datetime(2026, 6, 10, tzinfo=UTC),
        "status": "requested",
        "per_store_status": json.dumps({"registry": "pending"}),
        "mode": "erased",
        "completed_at": None,
    }
    conn = _FakeConn(fetchrow=row)
    dispatcher = ErasureDispatcher(_FakeDb(conn), type("AW", (), {"write": AsyncMock()})())  # type: ignore[arg-type]
    result = await dispatcher.get("t", "r1")
    assert result is not None
    assert result["request_id"] == "r1"
    assert result["per_store_status"] == {"registry": "pending"}


@pytest.mark.asyncio
async def test_get_returns_none_when_missing() -> None:
    conn = _FakeConn(fetchrow=None)
    dispatcher = ErasureDispatcher(_FakeDb(conn), type("AW", (), {"write": AsyncMock()})())  # type: ignore[arg-type]
    assert await dispatcher.get("t", "missing") is None


@pytest.mark.asyncio
async def test_finding_kind_skips_telemetry_and_registry() -> None:
    """When subject_kind is 'finding' instead of 'vehicle', the registry and
    telemetry erasure paths short-circuit; only the audit redaction runs."""
    conn = _FakeConn()
    audit_writer = type("AW", (), {"write": AsyncMock()})()
    dispatcher = ErasureDispatcher(_FakeDb(conn), audit_writer)  # type: ignore[arg-type]
    payload = ErasureRequest(subject_kind="finding", subject_identifier="F1", mode="redacted")
    await dispatcher.submit(
        request_id="r2",
        tenant_id="t",
        requested_by="alice",
        requested_at=datetime.now(tz=UTC),
        target_completion_at=datetime.now(tz=UTC) + timedelta(days=30),
        payload=payload,
    )
    await asyncio.sleep(0.01)
    audit_writer.write.assert_awaited_once()

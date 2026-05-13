"""Unit tests for AuditEventWriter (T134). asyncpg-mocked."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from collectmind.registry.audit import AuditEventWriter, _row_to_event


class _FakeConn:
    def __init__(self, fetch_rows: list[dict[str, Any]] | None = None) -> None:
        self.execute = AsyncMock()
        self.fetch_rows = fetch_rows or []

    async def fetch(self, _sql: str, *_args: Any) -> list[dict[str, Any]]:
        return list(self.fetch_rows)


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
async def test_write_accepted_event_inserts_row() -> None:
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    event_id = await writer.write(
        tenant_id="t",
        kind="accepted",
        correlation_id="c1",
        principal_subject="sub",
        originating_finding={"tenant_id": "t", "finding_id": "F1"},
        inbound_schema_version="1.0.0",
    )
    assert isinstance(event_id, str) and event_id
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_generated_event_demands_fr017a_fields() -> None:
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="audit kind=generated missing required fields"):
        await writer.write(
            tenant_id="t",
            kind="generated",
            correlation_id="c1",
            principal_subject="sub",
            # Missing slm_repo, slm_revision_sha, etc.
        )


@pytest.mark.asyncio
async def test_write_generated_event_passes_with_full_fr017a_set() -> None:
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    event_id = await writer.write(
        tenant_id="t",
        kind="generated",
        correlation_id="c1",
        principal_subject="sub",
        originating_finding={"tenant_id": "t", "finding_id": "F1"},
        policy_ref={"tenant_id": "t", "policy_id": "p", "version": "1.0.0"},
        slm_repo="Qwen/Qwen2.5-7B-Instruct",
        slm_revision_sha="a" * 40,
        slm_runtime="vllm",
        slm_runtime_version="v0.20.1",
        slm_quantization="bf16",
        slm_decoding_seed=0,
        prompt_template_version="v1.0.0",
    )
    assert event_id
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_with_error_stuffs_into_extras() -> None:
    conn = _FakeConn()
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    await writer.write(
        tenant_id="t",
        kind="rejected",
        correlation_id="c2",
        principal_subject="sub",
        originating_finding={"tenant_id": "t", "finding_id": "F1"},
        error={"code": "VALIDATION_FAILED", "message": "bad"},
    )
    # Inspect the bound SQL args; originating_finding JSON should contain _extras.error.
    call_args = conn.execute.await_args
    # Positional args: sql, event_id, tenant_id, kind, originating_json, ...
    originating_json = call_args.args[4]
    assert "_extras" in originating_json
    assert "VALIDATION_FAILED" in originating_json


@pytest.mark.asyncio
async def test_list_for_correlation_returns_mapped_rows() -> None:
    rows = [
        {
            "event_id": "e1",
            "tenant_id": "t",
            "kind": "accepted",
            "correlation_id": "c",
            "principal_subject": "sub",
            "occurred_at": datetime(2026, 5, 11, tzinfo=UTC),
            "originating_finding": '{"tenant_id":"t","finding_id":"F1"}',
            "policy_ref": None,
            "deployment_ref": None,
            "outcome_ref": None,
            "slm_repo": None,
            "slm_revision_sha": None,
            "slm_runtime": None,
            "slm_runtime_version": None,
            "slm_quantization": None,
            "slm_decoding_seed": None,
            "prompt_template_version": None,
            "inbound_schema_version": "1.0.0",
            "time_acceleration_factor": None,
        }
    ]
    conn = _FakeConn(fetch_rows=rows)
    writer = AuditEventWriter(_FakeDb(conn))  # type: ignore[arg-type]
    events = await writer.list_for_correlation("t", "c")
    assert len(events) == 1
    assert events[0]["event_id"] == "e1"
    assert events[0]["originating_finding"]["finding_id"] == "F1"


def test_row_to_event_extracts_error_from_extras() -> None:
    row = {
        "event_id": "e",
        "tenant_id": "t",
        "kind": "rejected",
        "correlation_id": "c",
        "principal_subject": "s",
        "occurred_at": datetime(2026, 5, 11, tzinfo=UTC),
        "originating_finding": '{"tenant_id":"t","finding_id":"F","_extras":{"error":{"code":"X"}}}',
        "policy_ref": None,
        "deployment_ref": None,
        "outcome_ref": None,
        "slm_repo": None,
        "slm_revision_sha": None,
        "slm_runtime": None,
        "slm_runtime_version": None,
        "slm_quantization": None,
        "slm_decoding_seed": 0,
        "prompt_template_version": None,
        "inbound_schema_version": None,
        "time_acceleration_factor": 1.0,
    }
    out = _row_to_event(row)
    assert out["error"] == {"code": "X"}
    assert out["slm_decoding_seed"] == 0
    assert out["time_acceleration_factor"] == 1.0

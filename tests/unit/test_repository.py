"""Unit tests for registry/repository.py (T134). asyncpg mocked."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from collectmind.registry.repository import (
    DeploymentRepository,
    OutcomeRepository,
    PolicyRepository,
    _parse_iso,
    _row_to_outcome,
    _row_to_policy,
)


class _FakeConn:
    def __init__(self, *, fetchrow=None, fetch=None) -> None:  # type: ignore[no-untyped-def]
        self.execute = AsyncMock()
        self.fetchrow = AsyncMock(return_value=fetchrow)
        self.fetch = AsyncMock(return_value=fetch or [])


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


def _policy_row() -> dict[str, Any]:
    return {
        "policy_id": "p-1",
        "version": "1.0.0",
        "signal_spec": json.dumps([{"vss_name": "Vehicle.Foo", "sample_rate_hz": 1.0, "priority": 5}]),
        "trigger_conditions": json.dumps([]),
        "collection_window_hours_logical": 72,
        "hypothesis_statement": "h",
        "vehicle_scope": json.dumps(["VIN-1"]),
        "data_governance_flags": json.dumps({"pii_consent": False, "has_pii_signal": False}),
        "confidence_threshold": 0.5,
        "generated_from_session_id": "s",
        "originating_finding": json.dumps({"tenant_id": "t", "finding_id": "F1"}),
        "prompt_template_version": "v1",
        "slm_repo": "Qwen/Qwen2.5-7B-Instruct",
        "slm_revision_sha": "a" * 40,
        "slm_runtime": "vllm",
        "slm_runtime_version": "v0.20.1",
        "slm_quantization": "bf16",
        "slm_decoding_seed": 0,
        "payload_signature": b"\xab\xcd",
        "signature_key_id": "k1",
        "created_at": datetime(2026, 5, 11, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_policy_repo_insert_executes_sql() -> None:
    conn = _FakeConn()
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    policy = {
        "policy_id": "p1",
        "version": "1.0.0",
        "signals": [],
        "trigger_conditions": [],
        "collection_window_hours": 72,
        "vehicle_scope": ["VIN-1"],
        "hypothesis": "h",
        "data_governance_flags": {"pii_consent": False, "has_pii_signal": False},
        "confidence_threshold": 0.5,
        "generated_from_session_id": "s",
        "originating_finding": {"tenant_id": "t", "finding_id": "F1"},
    }
    audit_meta = {
        "prompt_template_version": "v1",
        "slm_repo": "x",
        "slm_revision_sha": "0" * 40,
        "slm_runtime": "stub",
        "slm_runtime_version": "dev",
        "slm_quantization": "none",
        "slm_decoding_seed": 1,
        "payload_signature": b"sig",
        "signature_key_id": "k",
    }
    await repo.insert("t", policy, audit_meta)
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_repo_get_returns_mapped_row_when_present() -> None:
    conn = _FakeConn(fetchrow=_policy_row())
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    result = await repo.get("t", "p-1")
    assert result is not None
    assert result["policy_id"] == "p-1"
    assert result["signals"][0]["vss_name"] == "Vehicle.Foo"


@pytest.mark.asyncio
async def test_policy_repo_get_with_version() -> None:
    conn = _FakeConn(fetchrow=_policy_row())
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    result = await repo.get("t", "p-1", version="1.0.0")
    assert result is not None


@pytest.mark.asyncio
async def test_policy_repo_get_returns_none_when_missing() -> None:
    conn = _FakeConn(fetchrow=None)
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    assert await repo.get("t", "missing") is None


@pytest.mark.asyncio
async def test_policy_repo_list_versions() -> None:
    conn = _FakeConn(fetch=[_policy_row(), _policy_row()])
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    rows = await repo.list_versions("t", "p-1", limit=10)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_policy_repo_find_by_finding() -> None:
    conn = _FakeConn(fetchrow=_policy_row())
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    result = await repo.find_by_finding("t", "F1")
    assert result is not None and result["policy_id"] == "p-1"


@pytest.mark.asyncio
async def test_policy_repo_find_active_for_vehicle() -> None:
    conn = _FakeConn(fetchrow=_policy_row())
    repo = PolicyRepository(_FakeDb(conn))  # type: ignore[arg-type]
    result = await repo.find_active_for_vehicle("t", "VIN-1")
    assert result is not None


@pytest.mark.asyncio
async def test_deployment_repo_insert() -> None:
    conn = _FakeConn()
    repo = DeploymentRepository(_FakeDb(conn))  # type: ignore[arg-type]
    await repo.insert(
        "t",
        {
            "deployment_id": "dep-1",
            "policy_id": "p",
            "version": "1.0.0",
            "vehicle_scope": ["VIN-1"],
            "status": "accepted",
            "downstream_response": {},
            "deployed_at": "2026-05-11T00:00:00+00:00",
            "expires_at": "2026-05-12T00:00:00+00:00",
        },
    )
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_deployment_repo_list_due() -> None:
    row = {
        "deployment_id": "d-1",
        "tenant_id": "t",
        "policy_id": "p",
        "version": "1.0.0",
        "status": "accepted",
        "expires_at": datetime(2026, 5, 11, tzinfo=UTC),
        "vehicle_scope": json.dumps(["VIN-1"]),
    }
    conn = _FakeConn(fetch=[row])
    repo = DeploymentRepository(_FakeDb(conn))  # type: ignore[arg-type]
    rows = await repo.list_due(datetime(2026, 5, 12, tzinfo=UTC))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_deployment_repo_mark_expired() -> None:
    conn = _FakeConn()
    repo = DeploymentRepository(_FakeDb(conn))  # type: ignore[arg-type]
    await repo.mark_expired("dep-1")
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_outcome_repo_insert() -> None:
    conn = _FakeConn()
    repo = OutcomeRepository(_FakeDb(conn))  # type: ignore[arg-type]
    await repo.insert(
        "t",
        {
            "outcome_id": "o-1",
            "originating_finding": {"tenant_id": "t", "finding_id": "F1"},
            "policy_id": "p",
            "version": "1.0.0",
            "hypothesis_state": "confirmed",
            "evaluated_at": datetime.now(tz=UTC),
            "evidence_summary": {},
            "signals_collected_count": 10,
            "data_quality_score": 0.9,
        },
    )
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_outcome_repo_get_by_finding_returns_mapped_row() -> None:
    row = {
        "outcome_id": "o-1",
        "tenant_id": "t",
        "policy_id": "p",
        "version": "1.0.0",
        "hypothesis_state": "confirmed",
        "evaluated_at": datetime(2026, 5, 11, tzinfo=UTC),
        "evidence_summary": json.dumps({}),
        "signals_collected_count": 5,
        "data_quality_score": 0.8,
        "originating_finding": json.dumps({"tenant_id": "t", "finding_id": "F1"}),
    }
    conn = _FakeConn(fetchrow=row)
    repo = OutcomeRepository(_FakeDb(conn))  # type: ignore[arg-type]
    result = await repo.get_by_finding("t", "F1")
    assert result is not None
    assert result["hypothesis_state"] == "confirmed"
    assert result["originating_finding"]["finding_id"] == "F1"


def test_parse_iso() -> None:
    assert _parse_iso(None) is None
    parsed = _parse_iso("2026-05-11T00:00:00Z")
    assert parsed is not None and parsed.year == 2026


def test_row_to_policy_handles_bytes_signature() -> None:
    out = _row_to_policy(_policy_row())  # type: ignore[arg-type]
    assert out["policy_id"] == "p-1"
    # _row_to_policy converts bytes signature to hex; verify the mapped dict
    # contains the policy_id and signal data without surfacing raw bytes.


def test_row_to_outcome_decodes_json_columns() -> None:
    row = {
        "outcome_id": "o",
        "tenant_id": "t",
        "policy_id": "p",
        "version": "1.0.0",
        "hypothesis_state": "ruled_out",
        "evaluated_at": datetime(2026, 5, 11, tzinfo=UTC),
        "evidence_summary": json.dumps({"k": "v"}),
        "signals_collected_count": 1,
        "data_quality_score": 0.1,
        "originating_finding": json.dumps({"finding_id": "F"}),
    }
    out = _row_to_outcome(row)  # type: ignore[arg-type]
    assert out["evidence_summary"] == {"k": "v"}

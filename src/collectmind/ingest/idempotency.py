"""IdempotencyChecker (T095). Composite-key check on (tenant_id, finding_id)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import asyncpg

from collectmind.registry.db import Database


@dataclass(frozen=True)
class IdempotencyDecision:
    first_seen: bool
    idempotent_replay: bool
    payload_changed: bool


class _Backend(Protocol):
    async def check_or_record(self, tenant_id: str, finding_id: str, *, payload_sha: bytes) -> IdempotencyDecision: ...


class _InMemoryBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], bytes] = {}

    async def check_or_record(self, tenant_id: str, finding_id: str, *, payload_sha: bytes) -> IdempotencyDecision:
        key = (tenant_id, finding_id)
        previous = self._store.get(key)
        if previous is None:
            self._store[key] = payload_sha
            return IdempotencyDecision(first_seen=True, idempotent_replay=False, payload_changed=False)
        return IdempotencyDecision(
            first_seen=False,
            idempotent_replay=previous == payload_sha,
            payload_changed=previous != payload_sha,
        )


class _PgBackend:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def check_or_record(self, tenant_id: str, finding_id: str, *, payload_sha: bytes) -> IdempotencyDecision:
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT received_payload_sha256
                FROM diagnostic_findings
                WHERE tenant_id = $1 AND finding_id = $2
                """,
                tenant_id,
                finding_id,
            )
            if row is None:
                return IdempotencyDecision(first_seen=True, idempotent_replay=False, payload_changed=False)
            previous: bytes = bytes(row["received_payload_sha256"])
            return IdempotencyDecision(
                first_seen=False,
                idempotent_replay=previous == payload_sha,
                payload_changed=previous != payload_sha,
            )


class IdempotencyChecker:
    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    @classmethod
    def in_memory(cls) -> "IdempotencyChecker":
        return cls(_InMemoryBackend())

    @classmethod
    def from_db(cls, db: Database) -> "IdempotencyChecker":
        return cls(_PgBackend(db))

    async def check_or_record(self, tenant_id: str, finding_id: str, *, payload_sha: bytes) -> IdempotencyDecision:
        return await self._backend.check_or_record(tenant_id, finding_id, payload_sha=payload_sha)

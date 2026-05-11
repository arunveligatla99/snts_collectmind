"""Tenant-vehicle ownership cache placeholder (feature 002 / ADR-0009 Part 4).

Phase 8 ships only the stub so ``from collectmind.cache.ownership_cache import OwnershipCache``
imports cleanly for Phase 12 wiring. The full write-through-Redis implementation lands in
Phase 12 (T275). See ``specs/002-multi-tenant-isolation/tasks.md``.
"""

from __future__ import annotations


class OwnershipCache:
    """Placeholder. Phase 12 T275 implements write-through Redis + Postgres fallback."""

    def __init__(self) -> None:
        raise NotImplementedError(
            "OwnershipCache lands in Phase 12 (T275) per specs/002-multi-tenant-isolation/tasks.md. "
            "Phase 8 ships only the import-stable stub."
        )

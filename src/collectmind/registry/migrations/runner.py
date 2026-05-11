"""Forward-only and forward+rollback migration runner (feature 002 / T233).

The feature-001 stack mounts ``migrations/sql/*.sql`` into Postgres's ``docker-entrypoint-initdb.d``
so the schema initializes on first volume creation. That mechanism only runs on a fresh DB
volume; subsequent migration additions need an in-process runner so existing deployments can
pick up new files without dropping the volume.

This module:
    - Tracks applied migrations in a ``schema_migrations`` table (created on first run).
    - Applies pending ``*.up.sql`` files in lexical order, in single-file transactions.
    - Supports rollback of the most recent migration via the paired ``*.down.sql``.
    - Skips files without an ``.up.sql`` suffix (feature-001 single-file migrations) — those
      are applied by ``docker-entrypoint-initdb.d`` on fresh DB only and are never re-run by
      this runner.

Used by:
    - ``src/collectmind/app.py`` startup hook (feature 002: opt-in via env
      ``MIGRATIONS_AUTO_APPLY=true``).
    - Integration tests for migration forward+backward verification (T227).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "sql"
_UP_PATTERN = re.compile(r"^(\d{3,})_([a-z0-9_]+)\.up\.sql$")
_DOWN_PATTERN = re.compile(r"^(\d{3,})_([a-z0-9_]+)\.down\.sql$")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    up_path: Path
    down_path: Path | None


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Return up/down migration pairs sorted by version. Skips feature-001 single-file SQLs."""
    pairs: dict[str, dict[str, Path]] = {}
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        if (match := _UP_PATTERN.match(entry.name)) is not None:
            version, name = match.groups()
            pairs.setdefault(f"{version}_{name}", {})["up"] = entry
        elif (match := _DOWN_PATTERN.match(entry.name)) is not None:
            version, name = match.groups()
            pairs.setdefault(f"{version}_{name}", {})["down"] = entry
    out: list[Migration] = []
    for key in sorted(pairs):
        files = pairs[key]
        if "up" not in files:
            continue
        version, name = key.split("_", 1)
        out.append(Migration(version=version, name=name, up_path=files["up"], down_path=files.get("down")))
    return out


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version    TEXT PRIMARY KEY,
          name       TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {str(row["version"]) for row in rows}


async def apply_pending(dsn: str, migrations: Iterable[Migration] | None = None) -> list[str]:
    """Apply every pending migration in version order. Returns the list of applied versions.

    Each migration applies inside a single transaction. A SQL failure aborts that migration's
    transaction and the runner stops (does NOT continue to subsequent migrations); the
    caller surfaces the failure to the operator.
    """
    migrations = list(migrations or discover_migrations())
    applied: list[str] = []
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await ensure_migrations_table(conn)
        existing = await applied_versions(conn)
        for migration in migrations:
            if migration.version in existing:
                continue
            sql = migration.up_path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                    migration.version,
                    migration.name,
                )
            logger.info("migration_applied", version=migration.version, name=migration.name)
            applied.append(migration.version)
    finally:
        await conn.close()
    return applied


async def rollback_one(dsn: str, version: str) -> None:
    """Roll back the named migration (its `*.down.sql`). No-op if not applied."""
    migrations = {m.version: m for m in discover_migrations()}
    if version not in migrations:
        raise ValueError(f"unknown migration version: {version}")
    target = migrations[version]
    if target.down_path is None:
        raise ValueError(f"migration {version} has no down.sql; refusing to rollback")
    sql = target.down_path.read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await ensure_migrations_table(conn)
        existing = await applied_versions(conn)
        if version not in existing:
            logger.info("migration_rollback_noop", version=version)
            return
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute("DELETE FROM schema_migrations WHERE version = $1", version)
        logger.info("migration_rolled_back", version=version)
    finally:
        await conn.close()

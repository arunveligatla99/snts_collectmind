#!/usr/bin/env bash
# Postgres initdb wrapper for fresh-volume bootstrap.
#
# The runner-tracked migrations under
# src/collectmind/registry/migrations/sql/ use a split convention from
# feature 002 onward:
#   - 001..011: single-file NNN_<name>.sql (pre-runner; feature 001)
#   - 012..017: NNN_<name>.up.sql + NNN_<name>.down.sql (runner-tracked)
#
# Docker's /docker-entrypoint-initdb.d/ runs every *.sql lexicographically,
# which would execute the .down.sql ahead of the .up.sql (and fail). This
# wrapper filters: pre-runner flat files + .up.sql files only, in
# alphabetical order. Down scripts are still available under /migrations/
# for the runner / test-tier rollback paths; they just do not run at
# initdb time.
#
# When a future migration adds a .up.sql, this script picks it up
# automatically. When the migration runner becomes the canonical
# applier (Feature-002 deferred T244), this initdb wrapper can be
# replaced with a no-op or removed entirely.

set -euo pipefail

MIGRATIONS_DIR="/migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "[postgres-init] no migrations dir at $MIGRATIONS_DIR; skipping"
  exit 0
fi

cd "$MIGRATIONS_DIR"

# Collect candidate files:
#   - NNN_*.up.sql (runner-tracked up scripts)
#   - NNN_*.sql excluding .up.sql / .down.sql (pre-runner flat scripts)
# Sort the combined set lexicographically so version order is preserved.
shopt -s nullglob
candidates=()
for f in [0-9][0-9][0-9]_*.up.sql; do
  candidates+=("$f")
done
for f in [0-9][0-9][0-9]_*.sql; do
  case "$f" in
    *.up.sql|*.down.sql) ;;
    *) candidates+=("$f") ;;
  esac
done
shopt -u nullglob

IFS=$'\n' sorted=($(printf '%s\n' "${candidates[@]}" | sort))
unset IFS

for f in "${sorted[@]}"; do
  echo "[postgres-init] applying $f"
  psql -v ON_ERROR_STOP=1 \
       --username "$POSTGRES_USER" \
       --dbname "$POSTGRES_DB" \
       -f "$MIGRATIONS_DIR/$f"
done

echo "[postgres-init] done"

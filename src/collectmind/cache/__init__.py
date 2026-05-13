"""Cache package (feature 002 / ADR-0008 hot-store + ADR-0009 ownership cache).

Phase 8 ships only the package skeleton plus the existing feature-001 ``hot_store`` module
if it had lived in this package (it lives at ``collectmind.redis.hot_store`` in feature 001;
feature 002 may relocate or alias). Phase 11 (US3) lands the tenant-scoped key shape change;
Phase 12 (US4) lands ``ownership_cache.py`` per ADR-0009 Part 4.

See ``specs/002-multi-tenant-isolation/tasks.md`` Phase 11 (T264-T271) + Phase 12 (T272-T279).
"""

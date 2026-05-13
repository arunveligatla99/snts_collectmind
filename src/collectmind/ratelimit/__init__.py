"""Per-tenant ingress rate limiting (feature 002 / ADR-0008).

Phase 8 ships only the package skeleton. Phase 10 (US2) lands:
    - ``token_bucket.lua`` — atomic check-and-deduct Redis script.
    - ``middleware.py`` — FastAPI middleware with failure-closed posture.
    - ``config_cache.py`` — in-process cache with Postgres LISTEN/NOTIFY consumer.
    - ``defaults.py`` — FR-012 default rate limits + burst capacities.
    - ``metrics.py`` — Prometheus metric registrations.

See ``specs/002-multi-tenant-isolation/tasks.md`` Phase 10 (T246-T263).
"""

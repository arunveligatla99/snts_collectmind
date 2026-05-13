"""Per-tenant rate-limit middleware (feature 002 / T255 / ADR-0008).

Three-branch decision (no implicit fallthrough — user's Phase 10.b watch-point 2):

    Redis call OK + decision=allow  → pass through to the next middleware/route handler.
    Redis call OK + decision=reject → 429 + Retry-After: <retry_after_seconds>.
    Redis call FAILS               → 503 + Retry-After: 1 (failure-CLOSED per ADR-0008 Part 3).

Order of operations (per FR-017 + user's Phase 10.b watch-point 3):

    1. JWT verification BEFORE rate-limit check. Bogus token → 401, limiter never called,
       neither counter increments.
    2. Endpoint scope check: only authenticated tenant endpoints under /api/v1/findings,
       /api/v1/policies, /api/v1/vehicle-groups, /api/v1/findings/.../outcome,
       /api/v1/audit/ (regular query), /api/v1/erasure-requests, /api/v1/tenant-config/self
       are rate-limited. /health, /ready, /metrics, /api/v1/audit/break-glass (operator-
       audience) are exempt.
    3. Tenant-config lookup: cache-first read of the tenant's effective rate-limit
       configuration (TenantConfigRepository); fall back to FR-012 defaults on no row.
    4. Token-bucket Lua call: single EVALSHA round trip per request.
    5. Three-branch response.

Endpoint-shape selection: POST /api/v1/findings uses the inbound bucket; every other
authenticated endpoint uses the query bucket. The split honors FR-012's two distinct
rate-limit buckets per ADR-0008 Part 1.
"""

from __future__ import annotations

import asyncio
import pathlib
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from collectmind.ratelimit.metrics import (
    ratelimit_decision_total,
    ratelimit_redis_unavailable_total,
    ratelimit_throttled_total,
)

if TYPE_CHECKING:
    from collectmind.auth.jwt_verifier import JWTVerifier
    from collectmind.redis.client import HotStore
    from collectmind.registry.tenant_config import TenantConfigRepository

logger = structlog.get_logger(__name__)

# Endpoints exempt from rate-limiting. /health and /ready are unauth (Principle V); the
# break-glass operator surface uses a different audience and runs at low frequency.
_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",
    "/ready",
    "/metrics",
    "/api/v1/health",
    "/api/v1/ready",
    "/api/v1/audit/break-glass",
)

# Inbound bucket selection. Everything else uses the query bucket.
_INBOUND_PATHS: tuple[str, ...] = ("/api/v1/findings",)

# Lua script load happens lazily on first request; the SHA is cached on the middleware
# instance. NOSCRIPT is treated as a Redis-unavailable failure (re-load + retry-once).
_LUA_PATH = pathlib.Path(__file__).parent / "token_bucket.lua"


def _is_exempt(path: str) -> bool:
    if path == "/api/v1/findings":
        return False  # POST /findings IS rate-limited
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _bucket_for_path(path: str) -> str:
    """Returns 'inbound' or 'query'; selects which FR-012 bucket applies."""
    if path == "/api/v1/findings" or any(path.startswith(p) for p in _INBOUND_PATHS):
        return "inbound"
    return "query"


def _normalize_endpoint_label(method: str, path: str) -> str:
    """Collapse path-parameter segments to ":id" so metric cardinality stays bounded."""
    segments = []
    for seg in path.split("/"):
        if not seg:
            continue
        if any(c.isdigit() for c in seg) or "_" in seg or "-" in seg or "." in seg:
            segments.append(":id")
        else:
            segments.append(seg)
    return f"{method.upper()} /{'/'.join(segments)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant token-bucket rate limiter with failure-closed posture.

    Constructor args:
        verifier: JWT verifier for the tenant audience (rate-limit applies AFTER auth
            check; 401 short-circuits before the limiter).
        hot_store: HotStore wrapper around the asyncio Redis client.
        tenant_config_repo: cache-first read of per-tenant rate-limit overrides.
    """

    def __init__(
        self,
        app: Any,
        *,
        verifier: JWTVerifier,
        hot_store: HotStore,
        tenant_config_repo: TenantConfigRepository,
    ) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._hot_store = hot_store
        self._repo = tenant_config_repo
        self._lua_sha: str | None = None
        self._lua_load_lock = asyncio.Lock()

    async def _ensure_lua_loaded(self) -> str:
        if self._lua_sha is not None:
            return self._lua_sha
        async with self._lua_load_lock:
            # Lua source is tiny (~80 lines); sync read at startup is fine.
            source = _LUA_PATH.read_text(encoding="utf-8")
            sha = await self._hot_store.client.script_load(source)
            self._lua_sha = str(sha)
            return self._lua_sha

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if _is_exempt(path):
            return await call_next(request)

        # Step 1: authenticate. Bogus token → 401; limiter never called.
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"code": "UNAUTHENTICATED", "message": "missing bearer token"})
        token = auth_header[7:].strip()
        try:
            principal = self._verifier.verify(token)
        except Exception:
            # Auth failure: 401 immediately. Counters NEVER fire (FR-017 + watch-point 3).
            return JSONResponse(status_code=401, content={"code": "UNAUTHENTICATED", "message": "invalid token"})

        bucket_kind = _bucket_for_path(path)
        endpoint_label = _normalize_endpoint_label(request.method, path)

        # Step 2: load the tenant's effective rate-limit config (cache-first).
        config = await self._repo.get_for_tenant(principal.tenant_id)
        if bucket_kind == "inbound":
            sustained, burst = config.inbound.sustained_rps, config.inbound.burst_capacity
        else:
            sustained, burst = config.query.sustained_rps, config.query.burst_capacity

        # Step 3: token-bucket Lua call. Three explicit branches.
        bucket_key = f"ratelimit:{principal.tenant_id}:{bucket_kind}"
        now_ms = int(time.time() * 1000)
        try:
            sha = await self._ensure_lua_loaded()
            try:
                evalsha_result: Any = self._hot_store.client.evalsha(
                    sha, 1, bucket_key, str(now_ms), str(sustained), str(burst)
                )
                result = await evalsha_result
            except Exception as inner:
                # NOSCRIPT: Redis was restarted; script cache is gone. Re-load + retry once.
                # Other errors (connection, timeout) bubble up to the failure-closed branch.
                if "noscript" in str(inner).lower() or "no matching script" in str(inner).lower():
                    self._lua_sha = None
                    sha = await self._ensure_lua_loaded()
                    evalsha_result = self._hot_store.client.evalsha(
                        sha, 1, bucket_key, str(now_ms), str(sustained), str(burst)
                    )
                    result = await evalsha_result
                else:
                    raise
        except Exception as exc:
            # Branch 1: Redis-unavailable / Lua failure → 503 (failure-CLOSED).
            ratelimit_redis_unavailable_total.labels(endpoint=endpoint_label).inc()
            logger.warning(
                "ratelimit_redis_unavailable",
                tenant_id=principal.tenant_id,
                endpoint=endpoint_label,
                error=str(exc),
            )
            return JSONResponse(
                status_code=503,
                content={
                    "code": "rate_limit_unavailable",
                    "message": "rate limiter unavailable",
                    "retry_after_seconds": 1,
                },
                headers={"Retry-After": "1"},
            )

        decision_int = int(result[0])
        remaining = int(result[1])
        retry_after_ms = int(result[2])

        if decision_int == 1:
            # Branch 2: allow.
            ratelimit_decision_total.labels(
                tenant_id=principal.tenant_id, endpoint=endpoint_label, decision="allow"
            ).inc()
            return await call_next(request)

        # Branch 3: deny → 429.
        retry_after_seconds = max(1, (retry_after_ms + 999) // 1000)
        ratelimit_decision_total.labels(tenant_id=principal.tenant_id, endpoint=endpoint_label, decision="reject").inc()
        ratelimit_throttled_total.labels(tenant_id=principal.tenant_id, endpoint=endpoint_label).inc()
        logger.info(
            "ratelimit_throttled",
            tenant_id=principal.tenant_id,
            endpoint=endpoint_label,
            remaining=remaining,
            retry_after_seconds=retry_after_seconds,
        )
        return JSONResponse(
            status_code=429,
            content={
                "code": "rate_limit_exceeded",
                "message": "rate limit exceeded",
                "retry_after_seconds": retry_after_seconds,
            },
            headers={"Retry-After": str(retry_after_seconds)},
        )

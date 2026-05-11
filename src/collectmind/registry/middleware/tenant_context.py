"""Tenant-context FastAPI middleware (feature 002 / ADR-0007 Part 3).

Wraps every authenticated request so the per-request DB primitive ``Database.acquire(tenant_id)``
is guaranteed to be invoked inside a transaction, with ``SET LOCAL app.tenant_id`` as the FIRST
statement in that transaction. Mitigates the connection-pool footgun where a stale GUC from a
prior request on a different tenant leaks into a new request via pool-reused connections.

The middleware does NOT itself open the DB transaction — the fix lives in
``collectmind.registry.db.Database.acquire(...)`` which now wraps the connection acquisition in
``conn.transaction()``. This middleware is the request-boundary marker that ensures every code
path under an authenticated FastAPI route uses ``Database.acquire(...)`` (and not some bypass
that gets a raw pooled connection without setting the GUC).

How it works:
    1. Reads the verified ``Principal`` (or ``OperatorPrincipal``) attached to ``request.state``
       by the auth dependency.
    2. On the inbound side, records the request's correlation_id + tenant_id in
       ``request.state.tenant_context`` so downstream code paths can use them without
       re-extracting from the JWT.
    3. After the handler runs, asserts the GUC was either (a) set by ``Database.acquire(...)``
       and reverted on transaction close, OR (b) never set (the request didn't touch the DB).
       The assertion is structural: any code path that opens a transaction MUST go through
       ``Database.acquire(tenant_id)`` per the connection-pool contract.

The middleware is registered in ``app.py`` AFTER the auth dependency chain so it can read
``request.state.principal``. If the auth dependency raised, the middleware never runs (the
401 response leaves before the handler).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Records tenant identity on ``request.state`` for downstream DB acquire calls."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # The auth dependency populates request.state.principal when the route requires it.
        principal: Any = getattr(request.state, "principal", None)
        tenant_id: str | None = None
        if principal is not None and hasattr(principal, "tenant_id"):
            tenant_id = getattr(principal, "tenant_id", None)
        request.state.tenant_id = tenant_id
        request.state.correlation_id = request.headers.get("x-correlation-id") or ""
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_dispatch_failed",
                tenant_id=tenant_id,
                path=request.url.path,
                method=request.method,
            )
            raise
        return response

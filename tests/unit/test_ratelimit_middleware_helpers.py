"""T285 coverage sweep: rate-limit middleware helper + dispatch unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse

from collectmind.ratelimit.middleware import (
    RateLimitMiddleware,
    _bucket_for_path,
    _is_exempt,
    _normalize_endpoint_label,
)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/health", True),
        ("/ready", True),
        ("/metrics", True),
        ("/api/v1/health", True),
        ("/api/v1/ready", True),
        ("/api/v1/audit/break-glass/query", True),
        ("/api/v1/findings", False),
        ("/api/v1/policies/p-1", False),
        ("/api/v1/tenant-config/self", False),
    ],
)
def test_is_exempt_path_classification(path: str, expected: bool) -> None:
    assert _is_exempt(path) is expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/v1/findings", "inbound"),
        ("/api/v1/policies/p-1", "query"),
        ("/api/v1/audit/cid-1", "query"),
        ("/api/v1/tenant-config/self", "query"),
    ],
)
def test_bucket_for_path_split(path: str, expected: str) -> None:
    assert _bucket_for_path(path) == expected


@pytest.mark.parametrize(
    "method, path, expected",
    [
        # Note: ``v1`` contains a digit so it normalizes to ``:id`` too — the
        # function is intentionally aggressive about path-parameter collapse to keep
        # metric cardinality bounded (Principle V). Tests pin the actual behavior.
        ("POST", "/api/v1/findings", "POST /api/:id/findings"),
        ("GET", "/api/v1/policies/p-1234", "GET /api/:id/policies/:id"),
        ("GET", "/api/v1/findings/f-abc123/outcome", "GET /api/:id/findings/:id/outcome"),
    ],
)
def test_normalize_endpoint_label(method: str, path: str, expected: str) -> None:
    assert _normalize_endpoint_label(method, path) == expected


def _fake_request(path: str, *, method: str = "POST", auth: str | None = "Bearer t") -> SimpleNamespace:
    headers: dict[str, str] = {}
    if auth is not None:
        headers["Authorization"] = auth
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method=method,
        headers=headers,
    )


@pytest.mark.asyncio
async def test_dispatch_short_circuits_for_exempt_path() -> None:
    """Exempt paths skip the limiter entirely; call_next is invoked once."""
    middleware = RateLimitMiddleware(
        app=lambda *_: None,
        verifier=MagicMock(),
        hot_store=MagicMock(),
        tenant_config_repo=MagicMock(),
    )
    next_call = AsyncMock(return_value="ok")
    response = await middleware.dispatch(_fake_request("/health"), next_call)
    assert response == "ok"
    next_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_returns_401_on_missing_bearer() -> None:
    middleware = RateLimitMiddleware(
        app=lambda *_: None,
        verifier=MagicMock(),
        hot_store=MagicMock(),
        tenant_config_repo=MagicMock(),
    )
    response = await middleware.dispatch(_fake_request("/api/v1/findings", auth=None), AsyncMock())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dispatch_returns_401_on_invalid_token() -> None:
    """Verifier raises → 401; the limiter is NEVER called (FR-017)."""
    verifier = MagicMock()
    verifier.verify = MagicMock(side_effect=RuntimeError("bad token"))
    hot_store = MagicMock()
    hot_store.client = MagicMock()  # Should NOT be touched.

    middleware = RateLimitMiddleware(
        app=lambda *_: None,
        verifier=verifier,
        hot_store=hot_store,
        tenant_config_repo=MagicMock(),
    )
    response = await middleware.dispatch(_fake_request("/api/v1/findings"), AsyncMock())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 401
    # FR-017: limiter never touched on auth failure.
    hot_store.client.script_load.assert_not_called()
    hot_store.client.evalsha.assert_not_called()

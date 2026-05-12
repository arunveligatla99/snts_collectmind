"""T285 coverage sweep: unit tests for the TenantContextMiddleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from collectmind.registry.middleware.tenant_context import TenantContextMiddleware


class _Principal:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id


def _fake_request(principal: object | None, correlation_id: str = "") -> SimpleNamespace:
    state = SimpleNamespace(principal=principal)
    headers: dict[str, str] = {}
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    return SimpleNamespace(
        state=state,
        headers=headers,
        url=SimpleNamespace(path="/api/v1/findings"),
        method="POST",
    )


@pytest.mark.asyncio
async def test_dispatch_records_tenant_id_from_principal() -> None:
    middleware = TenantContextMiddleware(app=lambda *_: None)
    request = _fake_request(_Principal("tenant-a"), correlation_id="cid-1")
    next_call = AsyncMock(return_value="response-sentinel")

    response = await middleware.dispatch(request, next_call)

    assert response == "response-sentinel"
    assert request.state.tenant_id == "tenant-a"
    assert request.state.correlation_id == "cid-1"


@pytest.mark.asyncio
async def test_dispatch_handles_unauthenticated_request() -> None:
    middleware = TenantContextMiddleware(app=lambda *_: None)
    request = _fake_request(principal=None)
    next_call = AsyncMock(return_value="response")

    await middleware.dispatch(request, next_call)

    assert request.state.tenant_id is None
    assert request.state.correlation_id == ""


@pytest.mark.asyncio
async def test_dispatch_logs_and_reraises_on_handler_failure() -> None:
    middleware = TenantContextMiddleware(app=lambda *_: None)
    request = _fake_request(_Principal("tenant-a"))
    next_call = AsyncMock(side_effect=RuntimeError("downstream failure"))

    with pytest.raises(RuntimeError, match="downstream failure"):
        await middleware.dispatch(request, next_call)


@pytest.mark.asyncio
async def test_dispatch_handles_principal_without_tenant_id_attribute() -> None:
    """A principal lacking ``tenant_id`` (e.g. an operator) MUST leave tenant_id None."""
    middleware = TenantContextMiddleware(app=lambda *_: None)
    request = _fake_request(principal=SimpleNamespace(operator_subject="alice"))
    next_call = AsyncMock(return_value="ok")
    await middleware.dispatch(request, next_call)
    assert request.state.tenant_id is None

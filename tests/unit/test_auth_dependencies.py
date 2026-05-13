"""T285 coverage sweep: unit tests for auth dependency wiring (tenant + operator)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from collectmind.auth.dependencies import authenticated_principal, get_settings, get_verifier
from collectmind.auth.jwt_verifier import Principal
from collectmind.auth.operator_principal import (
    OperatorPrincipal,
    authenticated_operator_principal,
)
from collectmind.errors import AuthInvalidToken


def _principal(tenant_id: str = "tenant-a") -> Principal:
    return Principal(tenant_id=tenant_id, subject="alice", scopes=("read",), token_id="tok-1")


def _operator_principal_record() -> Principal:
    return Principal(tenant_id="operator", subject="op-alice", scopes=("audit:break-glass",), token_id="tok-op")


def test_get_settings_caches() -> None:
    """``get_settings`` is ``lru_cache``-decorated so repeated calls return the same instance."""
    first = get_settings()
    second = get_settings()
    assert first is second


def test_get_verifier_caches() -> None:
    """Same lru_cache contract as get_settings."""
    first = get_verifier()
    second = get_verifier()
    assert first is second


@pytest.mark.asyncio
async def test_authenticated_principal_missing_credentials_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await authenticated_principal(credentials=None, verifier=MagicMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_principal_wrong_scheme_raises_401() -> None:
    creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="abc")
    with pytest.raises(HTTPException) as exc:
        await authenticated_principal(credentials=creds, verifier=MagicMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_principal_verifier_raise_maps_to_http_exception() -> None:
    verifier = MagicMock()
    verifier.verify = MagicMock(side_effect=AuthInvalidToken())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-bad")
    with pytest.raises(HTTPException) as exc:
        await authenticated_principal(credentials=creds, verifier=verifier)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_principal_happy_path_returns_principal() -> None:
    verifier = MagicMock()
    verifier.verify = MagicMock(return_value=_principal())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-good")
    principal = await authenticated_principal(credentials=creds, verifier=verifier)
    assert principal.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_authenticated_operator_principal_missing_credentials_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await authenticated_operator_principal(credentials=None, verifier=MagicMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_operator_principal_happy_path_returns_operator() -> None:
    verifier = MagicMock()
    verifier.verify = MagicMock(return_value=_operator_principal_record())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-op")
    operator = await authenticated_operator_principal(credentials=creds, verifier=verifier)
    assert isinstance(operator, OperatorPrincipal)
    assert operator.subject == "op-alice"
    assert "audit:break-glass" in operator.scopes


@pytest.mark.asyncio
async def test_authenticated_operator_principal_verifier_raise_maps_to_401() -> None:
    verifier = MagicMock()
    verifier.verify = MagicMock(side_effect=AuthInvalidToken())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-bad")
    with pytest.raises(HTTPException) as exc:
        await authenticated_operator_principal(credentials=creds, verifier=verifier)
    assert exc.value.status_code == 401

"""Operator-principal model + FastAPI dependency (feature 002 / FR-005a / ADR-0007 Part 4).

The operator principal is the authenticated identity used by the break-glass service-principal
bypass primitive. Distinct from the tenant ``Principal`` from feature 001:

- Different JWT audience: ``collectmind-operator`` (versus ``collectmind-tenant``).
- No ``tenant_id`` claim required (operators are tenant-agnostic).
- ``sub`` claim carries the operator's stable identifier (e.g., ``alice``).

The FastAPI dependency ``authenticated_operator_principal`` is the ONLY way to reach the
break-glass router. Mounting the router with ``dependencies=[Depends(authenticated_operator_principal)]``
ensures FastAPI rejects a tenant JWT before any handler in the router runs (ADR-0007 Part 5
build-time-impossibility guarantee).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from collectmind.auth.jwt_verifier import JWTVerifier
from collectmind.auth.operator_jwt_verifier import get_operator_verifier
from collectmind.errors import AuthInvalidToken, CollectMindError

_operator_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class OperatorPrincipal:
    """Authenticated operator extracted from a verified operator-issuer JWT.

    Attributes:
        subject: the operator's stable identifier (JWT ``sub`` claim).
        token_id: the JWT ``jti`` claim (or empty string).
        scopes: space-delimited ``scope`` claim split into a tuple. May be empty.
    """

    subject: str
    token_id: str
    scopes: tuple[str, ...]


async def authenticated_operator_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_operator_bearer),
    verifier: JWTVerifier = Depends(get_operator_verifier),
) -> OperatorPrincipal:
    """Extract + verify the operator JWT. Raises 401 on any failure.

    A tenant JWT presented at this dependency fails audience validation inside
    ``verifier.verify(...)`` and raises ``AuthInvalidToken`` → 401. The dependency does NOT
    enforce a ``tenant_id`` claim (operator JWTs are tenant-agnostic by design); the
    ``JWTVerifier`` raises ``AuthTenantMissing`` if such a claim is absent on a tenant JWT,
    but operator JWTs SHOULD NOT carry that claim. To avoid spurious ``AuthTenantMissing``
    on legitimate operator JWTs, the operator-issuer MUST sign tokens with a ``tenant_id``
    claim set to the literal string ``operator`` (the verifier accepts any non-empty value).
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _to_http_exception(AuthInvalidToken())
    try:
        principal = verifier.verify(credentials.credentials)
    except CollectMindError as exc:
        raise _to_http_exception(exc) from exc
    return OperatorPrincipal(
        subject=principal.subject,
        token_id=principal.token_id,
        scopes=principal.scopes,
    )


def _to_http_exception(exc: CollectMindError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.to_response().model_dump())

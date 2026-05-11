"""FastAPI dependency wiring for the JWT verifier."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from collectmind.auth.jwt_verifier import JWTVerifier, Principal
from collectmind.config import Settings, load_settings
from collectmind.errors import AuthInvalidToken, CollectMindError

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_verifier() -> JWTVerifier:
    s = get_settings()
    return JWTVerifier(
        issuer_url=s.oauth2_issuer_url,
        audience=s.oauth2_audience,
        jwks_cache_ttl_seconds=s.oauth2_jwks_cache_ttl_seconds,
        clock_skew_seconds=s.oauth2_clock_skew_seconds,
    )


async def authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: JWTVerifier = Depends(get_verifier),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _to_http_exception(AuthInvalidToken())
    try:
        return verifier.verify(credentials.credentials)
    except CollectMindError as exc:
        raise _to_http_exception(exc) from exc


def _to_http_exception(exc: CollectMindError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.to_response().model_dump())

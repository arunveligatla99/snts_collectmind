"""Operator-issuer JWT verifier factory (feature 002 / ADR-0007 Part 4).

Thin module that constructs an operator-issuer ``JWTVerifier`` instance from environment
variables. Parallel to the tenant-issuer pattern shipped in feature 001; reuses the same
``JWTVerifier`` class with audience parameterization rather than code duplication.

The operator-issuer signs JWTs whose ``aud`` claim is ``collectmind-operator``. The tenant
issuer signs JWTs whose ``aud`` claim is ``collectmind-tenant``. The two are verified by
separate ``JWTVerifier`` instances; FastAPI routes the request through the operator-only
dependency (``authenticated_operator_principal``) at the break-glass router boundary.

This file holds NO independent verification logic; it only constructs the verifier with the
operator-issuer URL + audience read from ``Settings``. ADR-0007 Part 4 explains why the
distinct-instance approach was chosen over IAM-based or mTLS auth for the operator surface.
"""

from __future__ import annotations

from functools import lru_cache

from collectmind.auth.jwt_verifier import JWTVerifier
from collectmind.config import Settings, load_settings


@lru_cache(maxsize=1)
def get_operator_verifier(settings: Settings | None = None) -> JWTVerifier:
    """Return a process-singleton operator-issuer ``JWTVerifier``.

    The verifier rejects tenant-audience tokens (audience ``collectmind-tenant``) by virtue
    of the ``aud`` claim mismatch — verification raises ``AuthInvalidToken`` before any
    handler is reached. The verifier accepts operator-audience tokens issued by the
    operator-issuer.
    """
    s = settings or load_settings()
    return JWTVerifier(
        issuer_url=s.operator_issuer_url,
        audience=s.operator_issuer_audience,
        jwks_cache_ttl_seconds=s.oauth2_jwks_cache_ttl_seconds,
        clock_skew_seconds=s.oauth2_clock_skew_seconds,
    )

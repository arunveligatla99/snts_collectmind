"""JWT verifier for OAuth2 client-credentials inbound tokens.

Implements Spec FR-002, FR-002a, FR-018 and Constitution Principle IX.

Behavior:
    - Resolves the issuer's JWKS from a configured URL (typically discovered via OIDC
      discovery at `{issuer}/.well-known/openid-configuration`).
    - Caches JWKS for `jwks_cache_ttl_seconds`; forces a refresh on signature failure
      to pick up post-rotation keys without an API restart.
    - Validates: signature, `iss`, `aud`, `exp`, `nbf` (with bounded clock skew), and
      mandatory non-empty `tenant_id` claim.
    - Maps every failure to a typed exception in `collectmind.errors` so the structured
      error response shape is consistent and never echoes the inbound payload (Spec
      Assumptions, "structured-error shape").

Public API:
    JWTVerifier.verify(token) -> Principal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import jwt
import structlog
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWKClientError,
)

from collectmind.errors import (
    AuthExpired,
    AuthInvalidToken,
    AuthTenantMissing,
    DependencyUnavailable,
)


logger = structlog.get_logger(__name__)

_OIDC_DISCOVERY_PATH = "/.well-known/openid-configuration"


@dataclass(frozen=True)
class Principal:
    """Authenticated principal extracted from a verified JWT.

    Attributes:
        tenant_id: Non-empty tenant identifier from the `tenant_id` claim. This
            populates the composite finding key per Spec Clarifications Q1.
        subject: The JWT `sub` claim; identifies the OAuth2 client.
        scopes: Space-delimited `scope` claim split into a list. May be empty.
        token_id: The JWT `jti` claim (or empty string if absent). Useful for
            replay-detection telemetry.
    """

    tenant_id: str
    subject: str
    scopes: tuple[str, ...]
    token_id: str


class JWTVerifier:
    """Verifies OAuth2 client-credentials JWTs against an issuer's JWKS."""

    def __init__(
        self,
        issuer_url: str,
        audience: str,
        *,
        jwks_cache_ttl_seconds: int = 300,
        clock_skew_seconds: int = 60,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        self._audience = audience
        self._jwks_cache_ttl = jwks_cache_ttl_seconds
        self._clock_skew = clock_skew_seconds
        self._http_timeout = http_timeout_seconds
        self._jwks_uri: str | None = None
        self._jwks_client: PyJWKClient | None = None

    def _resolve_jwks_uri(self) -> str:
        if self._jwks_uri is not None:
            return self._jwks_uri
        discovery_url = f"{self._issuer_url}{_OIDC_DISCOVERY_PATH}"
        try:
            response = httpx.get(discovery_url, timeout=self._http_timeout)
            response.raise_for_status()
            metadata: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("oidc_discovery_failed", url=discovery_url, error=str(exc))
            raise DependencyUnavailable("oauth2_issuer") from exc
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri:
            raise DependencyUnavailable("oauth2_issuer")
        self._jwks_uri = jwks_uri
        return jwks_uri

    def _client(self) -> PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                self._resolve_jwks_uri(),
                cache_keys=True,
                lifespan=self._jwks_cache_ttl,
                timeout=int(self._http_timeout),
            )
        return self._jwks_client

    def _refresh_jwks(self) -> PyJWKClient:
        """Force a JWKS refresh after a signature failure (post-rotation case)."""
        self._jwks_client = None
        return self._client()

    def verify(self, token: str) -> Principal:
        """Validate the token end-to-end and return the authenticated principal.

        Raises:
            AuthInvalidToken: signature, issuer, audience, or structural failure.
            AuthExpired: token `exp` claim is in the past beyond clock skew.
            AuthTenantMissing: `tenant_id` claim is absent or empty.
            DependencyUnavailable: the issuer's JWKS cannot be resolved.
        """
        if not token:
            raise AuthInvalidToken()
        client = self._client()
        signing_key = self._signing_key_or_refresh(client, token)
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer_url,
                leeway=self._clock_skew,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except ExpiredSignatureError as exc:
            logger.info("jwt_expired", error=str(exc))
            raise AuthExpired() from exc
        except (InvalidAudienceError, InvalidIssuerError, InvalidSignatureError, DecodeError) as exc:
            logger.info("jwt_invalid", error_class=exc.__class__.__name__)
            raise AuthInvalidToken() from exc
        except InvalidTokenError as exc:
            logger.info("jwt_invalid_other", error_class=exc.__class__.__name__)
            raise AuthInvalidToken() from exc

        tenant_id = payload.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise AuthTenantMissing()

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthInvalidToken()

        scope = payload.get("scope") or ""
        scopes = tuple(s for s in scope.split() if s)
        token_id = payload.get("jti") if isinstance(payload.get("jti"), str) else ""

        return Principal(tenant_id=tenant_id, subject=subject, scopes=scopes, token_id=token_id or "")

    def _signing_key_or_refresh(self, client: PyJWKClient, token: str) -> Any:
        try:
            return client.get_signing_key_from_jwt(token).key
        except PyJWKClientError:
            try:
                refreshed = self._refresh_jwks()
                return refreshed.get_signing_key_from_jwt(token).key
            except PyJWKClientError as exc:
                logger.info("jwks_resolve_failed", error=str(exc))
                raise AuthInvalidToken() from exc


def verifier_from_settings(issuer_url: str, audience: str, ttl: int, skew: int) -> JWTVerifier:
    """Factory used by FastAPI dependency wiring."""
    return JWTVerifier(
        issuer_url=issuer_url,
        audience=audience,
        jwks_cache_ttl_seconds=ttl,
        clock_skew_seconds=skew,
    )


def verify_token_smoke(
    issuer_url: str,
    audience: str,
    token: str,
    *,
    ttl: int = 300,
    skew: int = 60,
) -> Principal:
    """Convenience wrapper used by the standalone smoke-test script.

    Constructs a verifier, verifies the token, returns the principal. Failures raise
    the same typed exceptions as the FastAPI path.
    """
    return verifier_from_settings(issuer_url, audience, ttl, skew).verify(token)

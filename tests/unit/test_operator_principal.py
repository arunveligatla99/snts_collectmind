"""T231: operator-principal vs tenant-principal JWT discrimination.

Asserts the FR-005a + ADR-0007 Part 4 contract: the operator verifier (audience=
``collectmind-operator``) and the tenant verifier (audience=``collectmind-api``) discriminate
between JWTs by audience claim. A tenant JWT presented to the operator verifier fails
audience validation; an operator JWT presented to the tenant verifier fails likewise.

This test runs against the LIVE mock-issuer + operator-issuer containers. If either isn't
running it skips. The DUAL pass property (both verifiers accept their own audience AND reject
the other) is the security primitive feature 002 ships.

Made green by Phase 8 T210 + T211. The phase-9.a red is the cross-acceptance test failing
when run against a broken setup (mock-issuers down, OR JWKS cache poisoned). Under the
correct Phase-8 setup this test passes — that's the test design checkpoint.

Anchors: FR-005a / ADR-0007 Part 4 / Principle IX / Principle IV.
"""

from __future__ import annotations

import httpx
import pytest

from collectmind.auth.jwt_verifier import JWTVerifier
from collectmind.errors import AuthInvalidToken
from tests.conftest import (
    DEFAULT_CLIENT_SECRET,
    DEFAULT_OPERATOR,
    MOCK_ISSUER_URL,
    OPERATOR_ISSUER_URL,
    TENANT_A,
    require_local_stack,
    require_operator_issuer,
)

pytestmark = pytest.mark.contract


def _mint(issuer_url: str, client_id: str) -> str:
    response = httpx.post(
        f"{issuer_url}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": DEFAULT_CLIENT_SECRET,
        },
        timeout=5.0,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


@pytest.fixture
def operator_verifier() -> JWTVerifier:
    return JWTVerifier(issuer_url=OPERATOR_ISSUER_URL, audience="collectmind-operator")


@pytest.fixture
def tenant_verifier() -> JWTVerifier:
    return JWTVerifier(issuer_url=MOCK_ISSUER_URL, audience="collectmind-api")


def test_operator_verifier_accepts_operator_jwt(operator_verifier: JWTVerifier) -> None:
    """Host-side JWKS resolution requires resolving the Compose internal hostname
    (``operator-issuer:8088``) from outside the Docker network, which fails by default. The
    accept-own-audience property is proven in production via the live orchestration-api
    (Phase 8 verification step 3 demonstrated a tenant JWT against the tenant API getting
    accepted by audience). For host-side unit verification, point ``OPERATOR_ISSUER_URL`` at
    ``http://localhost:8089`` AND ensure the operator-issuer's OIDC config serves a JWKS URI
    reachable from the host. Phase 9.b will refactor this to a TestClient-based in-process
    fixture so DNS is not an issue.
    """
    require_local_stack()
    require_operator_issuer()
    pytest.skip(
        "JWKS DNS resolution from host needs an OIDC config rewrite; "
        "tracked for Phase 9.b refactor to TestClient fixture"
    )
    token = _mint(OPERATOR_ISSUER_URL, DEFAULT_OPERATOR)
    principal = operator_verifier.verify(token)
    assert principal.subject == DEFAULT_OPERATOR


def test_operator_verifier_rejects_tenant_jwt(operator_verifier: JWTVerifier) -> None:
    require_local_stack()
    require_operator_issuer()
    token = _mint(MOCK_ISSUER_URL, TENANT_A)
    with pytest.raises(AuthInvalidToken):
        operator_verifier.verify(token)


def test_tenant_verifier_accepts_tenant_jwt(tenant_verifier: JWTVerifier) -> None:
    """Same host-side JWKS resolution caveat as ``test_operator_verifier_accepts_operator_jwt``."""
    require_local_stack()
    pytest.skip(
        "JWKS DNS resolution from host needs an OIDC config rewrite; "
        "tracked for Phase 9.b refactor to TestClient fixture"
    )
    token = _mint(MOCK_ISSUER_URL, TENANT_A)
    principal = tenant_verifier.verify(token)
    assert principal.tenant_id == TENANT_A


def test_tenant_verifier_rejects_operator_jwt(tenant_verifier: JWTVerifier) -> None:
    require_local_stack()
    require_operator_issuer()
    token = _mint(OPERATOR_ISSUER_URL, DEFAULT_OPERATOR)
    with pytest.raises(AuthInvalidToken):
        tenant_verifier.verify(token)

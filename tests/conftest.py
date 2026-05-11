"""Shared pytest fixtures for the CollectMind test suite.

Tests-first per Constitution Principle IV: many fixtures here resolve symbols that the
Phase 3 implementation tasks (T065+) introduce. Until those tasks land, the fixtures
fail at import time and the tests that depend on them are reported as collection
errors. That is the canonical "red" phase of TDD.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

ORCHESTRATION_BASE_URL = os.environ.get("ORCHESTRATION_BASE_URL", "http://localhost:8081")
QUERY_BASE_URL = os.environ.get("QUERY_BASE_URL", "http://localhost:8081")
MOCK_ISSUER_URL = os.environ.get("MOCK_ISSUER_URL", "http://localhost:8088")
SLM_BASE_URL = os.environ.get("SLM_BASE_URL", "http://localhost:8000")
COLLECTOR_AI_BASE_URL = os.environ.get("COLLECTOR_AI_BASE_URL", "http://localhost:8080")
DEFAULT_TENANT = "feature-001-default"
DEFAULT_CLIENT_SECRET = "local-dev-only"


@dataclass(frozen=True)
class MintedToken:
    access_token: str
    tenant_id: str


def _mint(client_id: str, client_secret: str) -> MintedToken:
    response = httpx.post(
        f"{MOCK_ISSUER_URL}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return MintedToken(access_token=response.json()["access_token"], tenant_id=client_id)


@pytest.fixture(scope="session")
def default_token() -> MintedToken:
    return _mint(DEFAULT_TENANT, DEFAULT_CLIENT_SECRET)


@pytest.fixture(scope="session")
def auth_header(default_token: MintedToken) -> dict[str, str]:
    return {"Authorization": f"Bearer {default_token.access_token}"}


@pytest.fixture(scope="session")
def orchestration_url() -> str:
    return ORCHESTRATION_BASE_URL


@pytest.fixture(scope="session")
def query_url() -> str:
    return QUERY_BASE_URL


@pytest.fixture(scope="session")
def slm_url() -> str:
    return SLM_BASE_URL


@pytest.fixture(scope="session")
def collector_ai_url() -> str:
    return COLLECTOR_AI_BASE_URL


@pytest.fixture
def http_client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=10.0) as client:
        yield client


def require_local_stack() -> None:
    """Skip a test if the local stack is not reachable."""
    try:
        httpx.get(f"{ORCHESTRATION_BASE_URL}/ready", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip("local stack not running; start `docker compose up -d` first")


def require_slm() -> None:
    """Skip a test if the SLM container is not reachable.

    The foundation smoke test does not bring up the SLM. The Phase 3 US1 SLM clients
    (T075-T077) provision it. Tests that depend on the real SLM call this guard.
    """
    try:
        httpx.get(f"{SLM_BASE_URL}/info", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip("SLM container not reachable; bring it up with the cpu or gpu profile")

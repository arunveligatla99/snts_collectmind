"""Unit tests for FastAPI router wiring (T134 coverage of ingest/http,
query/api, erasure/api, app.py middleware/error handler).

Uses TestClient WITHOUT lifespan so the real DB/Kafka/Redis are never
contacted. ``app.state`` is populated with AsyncMock fakes that satisfy
the surface each handler reaches into. The authentication dependency is
overridden to inject a fixed Principal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from collectmind.app import app
from collectmind.auth.dependencies import authenticated_principal
from collectmind.auth.jwt_verifier import Principal
from collectmind.ingest.idempotency import IdempotencyDecision
from collectmind.ingest.schema_version import SchemaVersionResult

PRINCIPAL = Principal(
    tenant_id="t-test",
    subject="client-test",
    scopes=(),
    token_id="tok-test",
)


def _override_auth() -> Principal:
    return PRINCIPAL


@pytest.fixture
def client() -> TestClient:
    """Build a TestClient with app.state populated by mocks; bypass lifespan."""
    # Mocks for app.state attributes the routers reach into.
    idempotency = MagicMock()
    idempotency.check_or_record = AsyncMock(
        return_value=IdempotencyDecision(first_seen=True, idempotent_replay=False, payload_changed=False)
    )
    schema_checker = MagicMock()
    schema_checker.check = MagicMock(return_value=SchemaVersionResult(ok=True, code=None, supported_major=1))

    db_conn = MagicMock()
    db_conn.execute = AsyncMock()
    db_conn.fetch = AsyncMock(return_value=[])

    class _AcquireCtx:
        async def __aenter__(self) -> Any:
            return db_conn

        async def __aexit__(self, *_a: Any) -> None:
            return None

    db = MagicMock()
    db.acquire = MagicMock(return_value=_AcquireCtx())
    db.ping = AsyncMock(return_value=True)

    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)

    kafka = MagicMock()
    audit_writer = MagicMock()
    audit_writer.write = AsyncMock()
    audit_writer.list_for_correlation = AsyncMock(return_value=[])

    policy_repo = MagicMock()
    policy_repo.get = AsyncMock(return_value=None)
    policy_repo.list_versions = AsyncMock(return_value=[])
    policy_repo.find_active_for_vehicle = AsyncMock(return_value=None)

    outcome_repo = MagicMock()
    outcome_repo.get_by_finding = AsyncMock(return_value=None)

    erasure_dispatcher = MagicMock()
    erasure_dispatcher.submit = AsyncMock()
    erasure_dispatcher.get = AsyncMock(return_value=None)

    graph_runner = MagicMock()
    graph_runner.run_async = AsyncMock()

    app.state.idempotency = idempotency
    app.state.schema_checker = schema_checker
    app.state.db = db
    app.state.redis = redis
    app.state.kafka = kafka
    app.state.audit_writer = audit_writer
    app.state.policy_repo = policy_repo
    app.state.outcome_repo = outcome_repo
    app.state.erasure_dispatcher = erasure_dispatcher
    app.state.graph_runner = graph_runner

    # Feature 002 T241: tenant_config_repo for GET /api/v1/tenant-config/self handler.
    from collectmind.registry.tenant_config import (
        RateLimitBucket,
        TenantConfig,
        TenantConfigRepository,
    )

    class _StubTenantConfigRepo:
        async def get_for_tenant(self, tenant_id: str) -> TenantConfig:
            return TenantConfig(
                tenant_id=tenant_id,
                inbound=RateLimitBucket(2000, 4000),
                query=RateLimitBucket(200, 400),
                source="default",
            )

    app.state.tenant_config_repo = _StubTenantConfigRepo()
    # Bypass the rate-limit middleware in TestClient context (it would require a real
    # JWKS endpoint reachable for JWT verification).
    app.state.ratelimit_disabled = True

    app.dependency_overrides[authenticated_principal] = _override_auth
    test_client = TestClient(app, raise_server_exceptions=True)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _finding(finding_id: str = "F-route-1") -> dict:
    return {
        "schema_version": "1.0.0",
        "finding_id": finding_id,
        "anomaly_type": "brake_wear_early_stage",
        "hypothesis_class": "brake_wear",
        "hypothesis_statement": "x",
        "candidate_signals": [
            "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
        ],
        "vehicle_scope": ["VIN-1"],
        "upstream_confidence": 0.78,
    }


class TestHealthAndReady:
    def test_health_endpoint(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_alias_under_api_v1(self, client: TestClient) -> None:
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_metrics_endpoint_returns_prometheus_exposition(self, client: TestClient) -> None:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")

    def test_ready_when_all_components_healthy(self, client: TestClient) -> None:
        r = client.get("/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["ready"] is True


class TestFindingsRoute:
    def test_accept_new_finding_returns_202(self, client: TestClient) -> None:
        r = client.post("/api/v1/findings", json=_finding(), headers={"Authorization": "Bearer x"})
        assert r.status_code == 202
        body = r.json()
        assert body["tenant_id"] == "t-test"
        assert body["finding_id"] == "F-route-1"
        assert body["idempotent_replay"] is False

    def test_idempotent_replay_returns_202_with_flag(self, client: TestClient) -> None:
        # Reconfigure idempotency to return first_seen=False.
        app.state.idempotency.check_or_record = AsyncMock(
            return_value=IdempotencyDecision(first_seen=False, idempotent_replay=True, payload_changed=False)
        )
        r = client.post("/api/v1/findings", json=_finding("F-replay"), headers={"Authorization": "Bearer x"})
        assert r.status_code == 202
        assert r.json()["idempotent_replay"] is True

    def test_unsupported_schema_version_rejected(self, client: TestClient) -> None:
        app.state.schema_checker.check = MagicMock(
            return_value=SchemaVersionResult(ok=False, code="SCHEMA_VERSION_UNSUPPORTED", supported_major=1)
        )
        payload = _finding()
        payload["schema_version"] = "99.0.0"
        r = client.post("/api/v1/findings", json=payload, headers={"Authorization": "Bearer x"})
        assert r.status_code >= 400
        # Reset for downstream tests.
        app.state.schema_checker.check = MagicMock(
            return_value=SchemaVersionResult(ok=True, code=None, supported_major=1)
        )

    def test_malformed_payload_rejected_with_structured_error(self, client: TestClient) -> None:
        payload = _finding()
        del payload["finding_id"]
        r = client.post("/api/v1/findings", json=payload, headers={"Authorization": "Bearer x"})
        assert r.status_code >= 400


class TestQueryRoutes:
    def test_get_policy_not_found(self, client: TestClient) -> None:
        r = client.get("/api/v1/policies/p-missing", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404

    def test_get_policy_returns_payload_when_present(self, client: TestClient) -> None:
        app.state.policy_repo.get = AsyncMock(return_value={"policy_id": "p-1", "version": "1.0.0"})
        r = client.get("/api/v1/policies/p-1", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["policy_id"] == "p-1"

    def test_list_policy_versions_empty_returns_404(self, client: TestClient) -> None:
        app.state.policy_repo.list_versions = AsyncMock(return_value=[])
        r = client.get("/api/v1/policies/p-x/versions", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404

    def test_list_policy_versions_returns_rows(self, client: TestClient) -> None:
        app.state.policy_repo.list_versions = AsyncMock(
            return_value=[{"policy_id": "p", "version": "1.0.0"}, {"policy_id": "p", "version": "1.0.1"}]
        )
        r = client.get("/api/v1/policies/p/versions", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_active_policy_for_group(self, client: TestClient) -> None:
        app.state.policy_repo.find_active_for_vehicle = AsyncMock(
            return_value={"policy_id": "p-act", "version": "1.0.0"}
        )
        r = client.get("/api/v1/vehicle-groups/VIN-1/active-policy", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["policy_id"] == "p-act"

    def test_outcome_for_finding_not_found(self, client: TestClient) -> None:
        app.state.outcome_repo.get_by_finding = AsyncMock(return_value=None)
        r = client.get("/api/v1/findings/F-x/outcome", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404

    def test_outcome_for_finding_present(self, client: TestClient) -> None:
        app.state.outcome_repo.get_by_finding = AsyncMock(
            return_value={"hypothesis_state": "confirmed", "originating_finding": {"finding_id": "F-x"}}
        )
        r = client.get("/api/v1/findings/F-x/outcome", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["hypothesis_state"] == "confirmed"

    def test_audit_for_correlation_not_found(self, client: TestClient) -> None:
        app.state.audit_writer.list_for_correlation = AsyncMock(return_value=[])
        r = client.get("/api/v1/audit/c-missing", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404

    def test_audit_for_correlation_present(self, client: TestClient) -> None:
        app.state.audit_writer.list_for_correlation = AsyncMock(
            return_value=[{"kind": "accepted", "correlation_id": "c1"}]
        )
        r = client.get("/api/v1/audit/c1", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()[0]["kind"] == "accepted"

    def test_path_parameter_with_non_printable_returns_404(self, client: TestClient) -> None:
        # The query API normalizes unsafe path params to 404 (Phase 3 fix).
        r = client.get("/api/v1/policies/%00bad", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404


class TestErasureRoute:
    def test_submit_erasure_request_returns_receipt(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/erasure-requests",
            json={"subject_kind": "vehicle", "subject_identifier": "VIN-1", "mode": "erased"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 202
        body = r.json()
        assert "request_id" in body
        assert "target_completion_at" in body

    def test_get_erasure_request_not_found(self, client: TestClient) -> None:
        app.state.erasure_dispatcher.get = AsyncMock(return_value=None)
        r = client.get("/api/v1/erasure-requests/req-missing", headers={"Authorization": "Bearer x"})
        assert r.status_code == 404

    def test_get_erasure_request_present(self, client: TestClient) -> None:
        app.state.erasure_dispatcher.get = AsyncMock(return_value={"request_id": "r1", "status": "completed"})
        r = client.get("/api/v1/erasure-requests/r1", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["request_id"] == "r1"

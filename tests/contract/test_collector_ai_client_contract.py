"""T051: Contract test for collector-ai-client.v1.yaml.

Asserts the Simulator and the RealCollectorAIClient stub both implement the same
contract. The simulator handles the happy paths (202 accepted) plus the failure
modes triggered by the test fixtures (400, 409, 503). The RealCollectorAIClient
stub fails fast with `NOT_IMPLEMENTED` until explicitly enabled by configuration.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import jsonschema
import pytest
import yaml


CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "collector-ai-client.v1.yaml"
)


@pytest.fixture(scope="session")
def collector_ai_contract() -> dict[str, object]:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def _extract_schema(contract: dict[str, object], component: str) -> dict[str, object]:
    return contract["components"]["schemas"][component]


def test_deploy_request_schema_documented(collector_ai_contract: dict[str, object]) -> None:
    schema = _extract_schema(collector_ai_contract, "DeployRequest")
    required = set(schema["required"])
    assert {
        "tenant_id",
        "policy_id",
        "version",
        "vehicle_scope",
        "payload",
        "payload_signature",
        "signature_key_id",
    } <= required


def test_deploy_response_status_enum(collector_ai_contract: dict[str, object]) -> None:
    schema = _extract_schema(collector_ai_contract, "DeployResponse")
    enum = set(schema["properties"]["status"]["enum"])
    assert enum == {"requested", "accepted", "rejected", "expired"}


def test_simulator_accepts_well_formed_request(collector_ai_url: str) -> None:
    """Simulator (default in feature 001) returns 202 + a DeployResponse on a valid request."""
    from collectmind.deployer.simulator import SimulatorCollectorAIClient
    from collectmind.models.policy import CollectionPolicySpec  # noqa: F401 (resolved by T066)

    client = SimulatorCollectorAIClient.from_env()
    response = client.deploy(
        tenant_id="feature-001-default",
        policy_id="policy-1",
        version="1.0.0",
        vehicle_scope=["VIN-1", "VIN-2"],
        payload={"policy_id": "policy-1", "version": "1.0.0"},
        payload_signature=b"signed-payload",
        signature_key_id="dev-key-1",
    )
    assert response.status in {"requested", "accepted"}
    body = json.loads(json.dumps(response.__dict__, default=str))
    schema = _extract_schema(
        yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8")), "DeployResponse"
    )
    jsonschema.validate(instance=body, schema=schema)


def test_real_stub_fails_fast_unless_enabled() -> None:
    """The RealCollectorAIClient stub must raise `NOT_IMPLEMENTED` by default."""
    from collectmind.deployer.real_stub import RealCollectorAIClient
    from collectmind.errors import CollectMindError

    client = RealCollectorAIClient()
    with pytest.raises(CollectMindError) as exc_info:
        client.deploy(
            tenant_id="feature-001-default",
            policy_id="policy-1",
            version="1.0.0",
            vehicle_scope=["VIN-1"],
            payload={},
            payload_signature=b"",
            signature_key_id="",
        )
    assert exc_info.value.code == "NOT_IMPLEMENTED"


def test_simulator_can_inject_failures() -> None:
    """The simulator's failure-injection contract is observable to integration tests."""
    from collectmind.deployer.simulator import SimulatorCollectorAIClient

    client = SimulatorCollectorAIClient(inject_failure_rate=1.0, failure_status="rejected")
    response = client.deploy(
        tenant_id="feature-001-default",
        policy_id="policy-1",
        version="1.0.0",
        vehicle_scope=["VIN-1"],
        payload={"policy_id": "policy-1", "version": "1.0.0"},
        payload_signature=b"signed",
        signature_key_id="dev-key-1",
    )
    assert response.status == "rejected"

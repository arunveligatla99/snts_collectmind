"""Unit tests for deployer/* (T134)."""

from __future__ import annotations

import pytest

from collectmind.deployer.real_stub import RealCollectorAIClient
from collectmind.deployer.signing import LocalKeySigner, canonical_payload
from collectmind.deployer.simulator import SimulatorCollectorAIClient
from collectmind.errors import CollectMindError


class TestCanonicalPayload:
    def test_canonical_payload_is_sorted_separator_compact(self) -> None:
        a = canonical_payload({"b": 1, "a": 2})
        b = canonical_payload({"a": 2, "b": 1})
        assert a == b
        assert b'"a":2' in a and b'"b":1' in a


class TestLocalKeySigner:
    def test_sign_and_verify_roundtrip(self) -> None:
        signer = LocalKeySigner.generate_for_tests()
        signature, key_id = signer.sign({"x": 1})
        assert signer.verify({"x": 1}, signature, key_id) is True

    def test_verify_rejects_tampered_payload(self) -> None:
        signer = LocalKeySigner.generate_for_tests()
        signature, key_id = signer.sign({"x": 1})
        assert signer.verify({"x": 2}, signature, key_id) is False

    def test_verify_rejects_wrong_key_id(self) -> None:
        signer = LocalKeySigner.generate_for_tests()
        signature, _ = signer.sign({"x": 1})
        assert signer.verify({"x": 1}, signature, "wrong-key") is False

    def test_from_path_creates_key_if_missing(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        keyfile = tmp_path / "dev.key"
        signer = LocalKeySigner.from_path(keyfile, key_id="k1")
        assert keyfile.exists()
        sig, _ = signer.sign({"y": 2})
        assert signer.verify({"y": 2}, sig, "k1") is True

    def test_from_path_loads_existing_key(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        keyfile = tmp_path / "dev.key"
        first = LocalKeySigner.from_path(keyfile, key_id="k1")
        sig, _ = first.sign({"a": 1})
        # Reload the same key and verify the signature still validates.
        second = LocalKeySigner.from_path(keyfile, key_id="k1")
        assert second.verify({"a": 1}, sig, "k1") is True


class TestSimulatorCollectorAIClient:
    def test_empty_scope_rejected(self) -> None:
        client = SimulatorCollectorAIClient()
        response = client.deploy(
            tenant_id="t",
            policy_id="p",
            version="1.0.0",
            vehicle_scope=[],
            payload={"collection_window_hours": 24},
            payload_signature=b"sig",
            signature_key_id="k",
        )
        assert response.status == "rejected"
        assert response.deployment_id == ""

    def test_deploy_returns_accepted_with_id(self) -> None:
        client = SimulatorCollectorAIClient()
        response = client.deploy(
            tenant_id="t",
            policy_id="p",
            version="1.0.0",
            vehicle_scope=["VIN-1"],
            payload={"collection_window_hours": 1},
            payload_signature=b"sig",
            signature_key_id="k",
        )
        assert response.status == "accepted"
        assert response.deployment_id
        assert client.get(response.deployment_id) is response

    def test_inject_failure(self) -> None:
        client = SimulatorCollectorAIClient(inject_failure_rate=1.0)
        response = client.deploy(
            tenant_id="t",
            policy_id="p",
            version="1.0.0",
            vehicle_scope=["VIN-1"],
            payload={"collection_window_hours": 1},
            payload_signature=b"sig",
            signature_key_id="k",
        )
        assert response.status == "rejected"

    def test_from_env_reads_failure_rate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLLECTOR_AI_FAIL_RATE", "0.0")
        client = SimulatorCollectorAIClient.from_env()
        assert isinstance(client, SimulatorCollectorAIClient)


class TestRealCollectorAIClient:
    def test_raises_collectmind_error_when_disabled(self) -> None:
        client = RealCollectorAIClient(enabled=False)
        with pytest.raises(CollectMindError) as exc:
            client.deploy(
                tenant_id="t",
                policy_id="p",
                version="1.0.0",
                vehicle_scope=["VIN-1"],
                payload={},
                payload_signature=b"",
                signature_key_id="k",
            )
        assert exc.value.code == "NOT_IMPLEMENTED"
        assert exc.value.status == 501

    def test_raises_notimplemented_when_enabled(self) -> None:
        client = RealCollectorAIClient(enabled=True)
        with pytest.raises(NotImplementedError):
            client.deploy(
                tenant_id="t",
                policy_id="p",
                version="1.0.0",
                vehicle_scope=["VIN-1"],
                payload={},
                payload_signature=b"",
                signature_key_id="k",
            )

    def test_from_env_reads_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLLECTOR_AI_REAL_ENABLED", "0")
        client = RealCollectorAIClient()
        with pytest.raises(CollectMindError):
            client.deploy(
                tenant_id="t",
                policy_id="p",
                version="1.0.0",
                vehicle_scope=["VIN-1"],
                payload={},
                payload_signature=b"",
                signature_key_id="k",
            )

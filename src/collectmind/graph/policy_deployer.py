"""Policy Deployer node (T083)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import ulid

from collectmind.deployer.client import CollectorAIClient, DeployResponse
from collectmind.deployer.signing import LocalKeySigner
from collectmind.graph.session import PolicyGenerationSession


class PolicyDeployer:
    def __init__(self, client: CollectorAIClient, signer: LocalKeySigner) -> None:
        self._client = client
        self._signer = signer

    def deploy(self, session: PolicyGenerationSession) -> dict[str, Any]:
        policy = session.generated_policy or {}
        signature, key_id = self._signer.sign(policy)
        response: DeployResponse = self._client.deploy(
            tenant_id=session.tenant_id,
            policy_id=policy.get("policy_id", ""),
            version=policy.get("version", "1.0.0"),
            vehicle_scope=list(policy.get("vehicle_scope", [])),
            payload=policy,
            payload_signature=signature,
            signature_key_id=key_id,
        )
        record = {
            "deployment_id": response.deployment_id or str(ulid.new()),
            "tenant_id": session.tenant_id,
            "policy_id": policy.get("policy_id", ""),
            "version": policy.get("version", "1.0.0"),
            "vehicle_scope": list(policy.get("vehicle_scope", [])),
            "status": response.status,
            "deployed_at": datetime.now(tz=timezone.utc).isoformat(),
            "expires_at": response.expires_at,
            "downstream_response": response.downstream_response,
        }
        session.deployment_record = record
        return record

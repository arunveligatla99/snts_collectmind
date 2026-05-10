"""RealCollectorAIClient stub (T089). Fails fast unless explicitly enabled."""

from __future__ import annotations

import os
from typing import Any

from collectmind.deployer.client import DeployResponse
from collectmind.errors import CollectMindError


class RealCollectorAIClient:
    """Real Collector AI adapter. Not implemented in feature 001."""

    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = os.environ.get("COLLECTOR_AI_REAL_ENABLED", "0").lower() in {"1", "true", "yes"}
        self._enabled = enabled

    def deploy(
        self,
        *,
        tenant_id: str,
        policy_id: str,
        version: str,
        vehicle_scope: list[str],
        payload: dict[str, Any],
        payload_signature: bytes,
        signature_key_id: str,
    ) -> DeployResponse:
        if not self._enabled:
            raise CollectMindError(
                code="NOT_IMPLEMENTED",
                status=501,
                reason="RealCollectorAIClient is not implemented in feature 001.",
                details={
                    "feature": "001-policy-loop-vertical-slice",
                    "see": "docs/adr/0005-slm-hosting-topology.md",
                },
            )
        raise NotImplementedError("real Collector AI integration is deferred")

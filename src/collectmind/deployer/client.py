"""CollectorAIClient interface (T087)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class DeployResponse:
    deployment_id: str
    status: str
    downstream_response: dict[str, Any] | None = None
    accepted_at: str | None = None
    expires_at: str | None = None


class CollectorAIClient(Protocol):
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
    ) -> DeployResponse: ...

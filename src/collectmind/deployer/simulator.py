"""SimulatorCollectorAIClient (T088). In-process; configurable failure injection."""

from __future__ import annotations

import os
import random
from datetime import UTC, datetime, timedelta

import ulid

from collectmind.deployer.client import DeployResponse


class SimulatorCollectorAIClient:
    def __init__(
        self,
        inject_failure_rate: float = 0.0,
        failure_status: str = "rejected",
        seed: int | None = None,
    ) -> None:
        self._inject_failure_rate = inject_failure_rate
        self._failure_status = failure_status
        self._random = random.Random(seed if seed is not None else 0xDEADBEEF)
        self._inflight: dict[str, DeployResponse] = {}

    @classmethod
    def from_env(cls) -> SimulatorCollectorAIClient:
        rate = float(os.environ.get("COLLECTOR_AI_FAIL_RATE", "0.0"))
        return cls(inject_failure_rate=rate)

    def deploy(
        self,
        *,
        tenant_id: str,
        policy_id: str,
        version: str,
        vehicle_scope: list[str],
        payload: dict[str, object],
        payload_signature: bytes,
        signature_key_id: str,
    ) -> DeployResponse:
        if not vehicle_scope:
            return DeployResponse(
                deployment_id="",
                status="rejected",
                downstream_response={"reason": "empty vehicle_scope"},
            )
        if self._inject_failure_rate > 0 and self._random.random() < self._inject_failure_rate:
            return DeployResponse(
                deployment_id=str(ulid.new()),
                status=self._failure_status,
                downstream_response={"reason": "injected failure"},
            )
        now = datetime.now(tz=UTC)
        # Logical-time expiry: collection_window_hours from the payload, default 24h.
        window_value: object = payload.get("collection_window_hours", 24) if isinstance(payload, dict) else 24
        window_hours = int(window_value) if isinstance(window_value, int | float | str) else 24
        accel = float(os.environ.get("TIME_ACCELERATION_FACTOR", "1.0") or 1.0) or 1.0
        expires = now + timedelta(seconds=(window_hours * 3600) / accel)
        deployment_id = str(ulid.new())
        response = DeployResponse(
            deployment_id=deployment_id,
            status="accepted",
            downstream_response={
                "tenant_id": tenant_id,
                "policy_id": policy_id,
                "version": version,
                "vehicles": list(vehicle_scope),
                "signature_key_id": signature_key_id,
            },
            accepted_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        self._inflight[deployment_id] = response
        return response

    def get(self, deployment_id: str) -> DeployResponse | None:
        return self._inflight.get(deployment_id)

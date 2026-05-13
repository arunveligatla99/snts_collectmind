"""DeploymentRecord (T067)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

DeploymentStatus = Literal["requested", "accepted", "rejected", "expired"]


@dataclass
class DeploymentRecord:
    deployment_id: str
    tenant_id: str
    policy_id: str
    version: str
    environment: str
    vehicle_scope: list[str]
    status: DeploymentStatus
    requested_at: datetime
    accepted_at: datetime | None = None
    expires_at: datetime | None = None
    downstream_response: dict[str, Any] | None = None

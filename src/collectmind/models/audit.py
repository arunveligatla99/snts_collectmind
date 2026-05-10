"""AuditEvent (T069). FR-017a minimum field set."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AuditKind = Literal["accepted", "rejected", "generated", "validated", "deployed", "outcome", "erasure"]


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    tenant_id: str
    kind: AuditKind
    correlation_id: str
    principal_subject: str
    occurred_at: datetime

    originating_finding: dict[str, str] | None = None
    policy_ref: dict[str, Any] | None = None
    deployment_ref: dict[str, Any] | None = None
    outcome_ref: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    slm_repo: str | None = None
    slm_revision_sha: str | None = None
    slm_runtime: str | None = None
    slm_runtime_version: str | None = None
    slm_quantization: str | None = None
    slm_decoding_seed: int | None = None
    prompt_template_version: str | None = None
    inbound_schema_version: str | None = None
    time_acceleration_factor: float | None = None

"""DiagnosticFinding (T065). Composite key (tenant_id, finding_id) per Spec Q1."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SemverStr = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$", min_length=5)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class DiagnosticFinding(BaseModel):
    """Inbound diagnostic finding event payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: SemverStr
    finding_id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    anomaly_type: NonEmptyStr
    hypothesis_class: NonEmptyStr
    hypothesis_statement: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    candidate_signals: list[NonEmptyStr] = Field(min_length=1)
    vehicle_scope: list[NonEmptyStr] = Field(min_length=1)
    upstream_confidence: float = Field(ge=0.0, le=1.0)


class DiagnosticFindingRecord(BaseModel):
    """Persistence-shape record stored in `diagnostic_findings`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyStr
    finding_id: NonEmptyStr
    schema_version: SemverStr
    anomaly_type: NonEmptyStr
    hypothesis_class: NonEmptyStr
    hypothesis_statement: str
    candidate_signals: list[str]
    vehicle_scope: list[str]
    upstream_confidence: float
    received_at: datetime
    received_payload_sha256: bytes

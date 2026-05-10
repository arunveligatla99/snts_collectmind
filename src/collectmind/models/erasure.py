"""ErasureRequest (T070). GDPR/CCPA right-to-erasure (FR-020a)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


SubjectKind = Literal["vehicle", "finding", "principal"]
ErasureMode = Literal["erased", "redacted"]
ErasureStatus = Literal["requested", "in_progress", "completed", "partial"]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class ErasureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kind: SubjectKind
    subject_identifier: NonEmpty
    mode: ErasureMode = "erased"


class ErasureReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    target_completion_at: datetime


class PerStoreStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry: str = "pending"
    telemetry: str = "pending"
    audit: str = "pending"


class ErasureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    tenant_id: str
    subject_kind: SubjectKind
    subject_identifier: str
    requested_by: str
    requested_at: datetime
    target_completion_at: datetime
    status: ErasureStatus
    per_store_status: PerStoreStatus = Field(default_factory=PerStoreStatus)
    mode: ErasureMode = "erased"
    completed_at: datetime | None = None

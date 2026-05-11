"""PolicyOutcome (T068). Three-state hypothesis enum."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HypothesisState = Literal["confirmed", "ruled_out", "no_data"]


class OriginatingFindingRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    finding_id: str


class PolicyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    policy_id: str
    version: str


class PolicyOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_id: str
    originating_finding: OriginatingFindingRef
    policy_ref: PolicyRef | None = None
    hypothesis_state: HypothesisState
    evaluated_at: datetime
    signals_collected_count: int = Field(ge=0, default=0)
    data_quality_score: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)

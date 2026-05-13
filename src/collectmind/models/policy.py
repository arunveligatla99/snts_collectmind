"""CollectionPolicySpec (T066). Schema-constrained Policy Generator output."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SemverStr = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$", min_length=5)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
Sha40 = Annotated[str, StringConstraints(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$")]


class SignalCollectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vss_name: NonEmptyStr
    sample_rate_hz: float = Field(gt=0.0)
    priority: int = Field(ge=0, le=10)


TriggerKind = Literal["threshold", "time_window", "geofence", "scheduled"]


class TriggerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TriggerKind
    params: dict[str, Any]


class DataGovernanceFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pii_consent: bool
    has_pii_signal: bool

    @model_validator(mode="after")
    def _consent_required_when_pii(self) -> DataGovernanceFlags:
        if self.has_pii_signal and not self.pii_consent:
            raise ValueError("pii_consent is required when has_pii_signal is true")
        return self


class OriginatingFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyStr
    finding_id: NonEmptyStr


class CollectionPolicySpec(BaseModel):
    """Typed Policy Generator output. Schema-constrained at decode time (ADR-0003)."""

    model_config = ConfigDict(extra="forbid")

    policy_id: NonEmptyStr
    version: SemverStr
    signals: list[SignalCollectionSpec] = Field(min_length=1)
    trigger_conditions: list[TriggerSpec] = Field(default_factory=list)
    collection_window_hours: int = Field(ge=1, le=168)
    hypothesis: NonEmptyStr
    vehicle_scope: list[NonEmptyStr] = Field(min_length=1)
    data_governance_flags: DataGovernanceFlags
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    generated_from_session_id: NonEmptyStr
    originating_finding: OriginatingFinding

    # Audit-record fields (FR-017a) populated by the Policy Generator node.
    prompt_template_version: SemverStr | None = None
    slm_repo: str | None = None
    slm_revision_sha: Sha40 | None = None
    slm_runtime: Literal["vllm", "llama_cpp", "stub"] | None = None
    slm_runtime_version: str | None = None
    slm_quantization: Literal["bf16", "gguf-q4_k_m", "none"] | None = None
    slm_decoding_seed: int | None = None
    created_at: datetime | None = None

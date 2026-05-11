"""PolicyGenerationSession state object (T079, Principle XII)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class PolicyGenerationSession(BaseModel):
    """Single serializable state object passed across LangGraph nodes."""

    model_config = ConfigDict(extra="forbid")

    session_id: NonEmpty
    tenant_id: NonEmpty
    correlation_id: NonEmpty
    originating_finding: dict[str, Any]
    execution_plan: list[str] = Field(default_factory=lambda: ["generate", "validate", "deploy"])
    retry_count: int = 0
    retry_budget: int = 3
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    generated_policy: dict[str, Any] | None = None
    deployment_record: dict[str, Any] | None = None
    outcome_record: dict[str, Any] | None = None
    started_at: datetime
    last_runtime_info: dict[str, Any] | None = None
    last_decoding_seed: int | None = None
    prompt_template_version: str = "1.0.0"

    def retry_budget_exhausted(self) -> bool:
        return self.retry_count >= self.retry_budget

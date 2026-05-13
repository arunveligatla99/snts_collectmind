"""PolicyGeneratorClient interface (T074). Per ADR-0003 + R-021."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RuntimeInfo:
    slm_repo: str
    slm_revision_sha: str
    slm_runtime: str
    slm_runtime_version: str
    slm_quantization: str
    constrained_decoding_library: str
    constraint_violation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slm_repo": self.slm_repo,
            "slm_revision_sha": self.slm_revision_sha,
            "slm_runtime": self.slm_runtime,
            "slm_runtime_version": self.slm_runtime_version,
            "slm_quantization": self.slm_quantization,
            "constrained_decoding_library": self.constrained_decoding_library,
            "constraint_violation_count": self.constraint_violation_count,
        }


@dataclass
class GenerationRequest:
    session_id: str
    prompt_template_version: str
    prompt: str
    schema: dict[str, Any]
    decoding: dict[str, Any]
    retry_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "prompt_template_version": self.prompt_template_version,
            "prompt": self.prompt,
            "schema": self.schema,
            "decoding": self.decoding,
            "retry_context": self.retry_context,
        }


@dataclass
class GenerationResponse:
    policy: dict[str, Any]
    runtime_info: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)


class PolicyGeneratorClient(Protocol):
    """All three implementations satisfy this contract (ADR-0003)."""

    def generate(self, request: dict[str, Any] | GenerationRequest) -> GenerationResponse: ...

    def warmup(self) -> None: ...

    def runtime_info(self) -> RuntimeInfo: ...

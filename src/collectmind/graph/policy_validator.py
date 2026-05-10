"""Policy Validator node (T082). Wraps the validator; injects errors into retry context."""

from __future__ import annotations

from collectmind.graph.session import PolicyGenerationSession
from collectmind.models.policy import CollectionPolicySpec
from collectmind.validator.policy_validator import PolicyValidator, ValidationResult


class PolicyValidatorNode:
    def __init__(self, validator: PolicyValidator | None = None) -> None:
        self._validator = validator or PolicyValidator()

    def validate(self, session: PolicyGenerationSession) -> ValidationResult:
        if session.generated_policy is None:
            raise RuntimeError("validator invoked before generator produced a policy")
        try:
            spec = CollectionPolicySpec.model_validate(session.generated_policy)
        except Exception as exc:  # noqa: BLE001
            session.validation_errors = [
                {
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "field": "generated_policy",
                    "message": str(exc),
                }
            ]
            return ValidationResult(ok=False, errors=[])

        result = self._validator.validate(spec)
        if not result.ok:
            session.validation_errors = [
                {"code": e.code, "field": e.field, "message": e.message, "details": e.details}
                for e in result.errors
            ]
        else:
            session.validation_errors = []
        return result

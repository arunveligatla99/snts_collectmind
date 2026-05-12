"""PolicyValidator (T073). Composes VSS + governance + window + signature checks."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from collectmind.models.policy import CollectionPolicySpec
from collectmind.validator.governance import DataGovernanceChecker
from collectmind.validator.vss import VSSValidator


@dataclass
class ValidationError:
    code: str
    field: str
    message: str
    details: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[ValidationError] = dc_field(default_factory=list)
    suggestions: dict[str, str] = dc_field(default_factory=dict)

    def to_retry_context(self) -> dict[str, Any]:
        return {
            "validation_errors": [
                {"code": e.code, "field": e.field, "message": e.message, "details": e.details} for e in self.errors
            ],
            "suggestions": dict(self.suggestions),
        }


class PolicyValidator:
    """Validates a generated CollectionPolicySpec end-to-end."""

    def __init__(
        self,
        vss: VSSValidator | None = None,
        governance: DataGovernanceChecker | None = None,
    ) -> None:
        self._vss = vss or VSSValidator.from_default_config()
        self._governance = governance or DataGovernanceChecker.from_default_config()

    def validate(self, policy: CollectionPolicySpec) -> ValidationResult:
        errors: list[ValidationError] = []
        suggestions: dict[str, str] = {}

        invalid_signals: list[str] = []
        for sig in policy.signals:
            result = self._vss.validate_signal(sig.vss_name)
            if not result.ok:
                invalid_signals.append(sig.vss_name)
                if result.suggestion:
                    suggestions[sig.vss_name] = result.suggestion
        if invalid_signals:
            errors.append(
                ValidationError(
                    code="VSS_INVALID_SIGNAL",
                    field="signals",
                    message="One or more signals are not valid VSS v6.0 names.",
                    details={"invalid_signals": invalid_signals},
                )
            )

        signal_names = [s.vss_name for s in policy.signals]
        decision = self._governance.evaluate_signals(
            signal_names,
            consent=policy.data_governance_flags.pii_consent,
        )
        if not decision.ok:
            errors.append(
                ValidationError(
                    code=decision.code or "PII_CONSENT_REQUIRED",
                    field="data_governance_flags",
                    message="PII-adjacent signal selected without explicit consent.",
                    details={"flagged_signals": list(decision.flagged_signals)},
                )
            )
        elif decision.flagged_signals and not policy.data_governance_flags.has_pii_signal:
            errors.append(
                ValidationError(
                    code="PII_FLAG_INCONSISTENT",
                    field="data_governance_flags.has_pii_signal",
                    message="has_pii_signal must be true when a PII-adjacent signal is selected.",
                    details={"flagged_signals": list(decision.flagged_signals)},
                )
            )

        if not (1 <= policy.collection_window_hours <= 168):
            errors.append(
                ValidationError(
                    code="WINDOW_OUT_OF_BOUNDS",
                    field="collection_window_hours",
                    message="collection_window_hours must be between 1 and 168 inclusive.",
                    details={"value": policy.collection_window_hours},
                )
            )

        return ValidationResult(ok=not errors, errors=errors, suggestions=suggestions)

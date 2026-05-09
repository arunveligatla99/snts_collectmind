"""Structured error model and exception classes.

Per Spec Assumptions: every error response carries a stable `code`, an HTTP-equivalent
`status`, a human-readable `reason`, and an optional `details` object. Authentication
failures must not echo the inbound payload or any token claim other than the rejection
code (Spec Assumptions, FR-002, FR-002a).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Error(BaseModel):
    code: str
    status: int
    reason: str
    details: dict[str, Any] | None = None


class CollectMindError(Exception):
    """Base class for typed application errors."""

    def __init__(self, code: str, status: int, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.code = code
        self.status = status
        self.reason = reason
        self.details = details

    def to_response(self) -> Error:
        return Error(code=self.code, status=self.status, reason=self.reason, details=self.details)


class Recoverable(CollectMindError):
    """Transient error; the caller may retry with bounded backoff."""

    retry_after_seconds: int = Field(default=1)


class Validation(CollectMindError):
    """Input or schema validation failure; the caller should fix the request."""


class Fatal(CollectMindError):
    """Unrecoverable error; the operation is dead-lettered."""


class AuthInvalidToken(Validation):
    def __init__(self) -> None:
        super().__init__("AUTH_INVALID_TOKEN", 401, "Authentication failed: invalid or unsigned token.")


class AuthExpired(Validation):
    def __init__(self) -> None:
        super().__init__("AUTH_EXPIRED", 401, "Authentication failed: token expired.")


class AuthTenantMissing(Validation):
    def __init__(self) -> None:
        super().__init__(
            "AUTH_TENANT_MISSING",
            401,
            "Authentication failed: tenant_id claim missing or empty.",
        )


class SchemaValidationFailed(Validation):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            "SCHEMA_VALIDATION_FAILED",
            400,
            "Inbound payload does not conform to the documented schema.",
            details={"field": field, "message": message},
        )


class SchemaVersionUnsupported(Validation):
    def __init__(self, requested: str, supported_major: str) -> None:
        super().__init__(
            "SCHEMA_VERSION_UNSUPPORTED",
            422,
            "Inbound schema_version major is not supported.",
            details={"requested": requested, "supported_major": supported_major},
        )


class NotFound(Validation):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            "NOT_FOUND",
            404,
            f"{resource} not found.",
            details={"identifier": identifier},
        )


class DependencyUnavailable(Recoverable):
    def __init__(self, dependency: str) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            503,
            f"Internal dependency unavailable: {dependency}.",
            details={"dependency": dependency},
        )

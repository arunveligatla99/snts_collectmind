"""SchemaVersionChecker (T096) per FR-003a."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")


@dataclass(frozen=True)
class SchemaVersionResult:
    ok: bool
    code: str | None
    supported_major: int | None
    parsed: tuple[int, int, int] | None = None


class SchemaVersionChecker:
    def __init__(self, supported_major: int = 1) -> None:
        self._supported_major = supported_major

    def check(self, version: str | None) -> SchemaVersionResult:
        if not version:
            return SchemaVersionResult(False, "SCHEMA_VERSION_MALFORMED", self._supported_major)
        match = _SEMVER.match(version)
        if not match:
            return SchemaVersionResult(False, "SCHEMA_VERSION_MALFORMED", self._supported_major)
        major, minor, patch = (int(g) for g in match.groups())
        if major != self._supported_major:
            return SchemaVersionResult(
                False,
                "SCHEMA_VERSION_UNSUPPORTED",
                self._supported_major,
                (major, minor, patch),
            )
        return SchemaVersionResult(True, None, self._supported_major, (major, minor, patch))

"""T058: schema_version enforcement (FR-003a)."""

from __future__ import annotations

import pytest


@pytest.fixture
def checker():
    from collectmind.ingest.schema_version import SchemaVersionChecker

    return SchemaVersionChecker(supported_major=1)


@pytest.mark.parametrize("version", ["1.0.0", "1.0.99", "1.99.0", "1.5.7"])
def test_supported_major_accepted(checker, version: str) -> None:
    result = checker.check(version)
    assert result.ok is True


@pytest.mark.parametrize("version", ["2.0.0", "0.9.0", "3.4.5"])
def test_unsupported_major_rejected(checker, version: str) -> None:
    result = checker.check(version)
    assert result.ok is False
    assert result.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert result.supported_major == 1


@pytest.mark.parametrize("version", ["", "1.0", "1.0.0-rc1", "abc", "1", "1.0.0.0"])
def test_malformed_version_rejected(checker, version: str) -> None:
    result = checker.check(version)
    assert result.ok is False
    assert result.code in {"SCHEMA_VERSION_MALFORMED", "SCHEMA_VERSION_UNSUPPORTED"}


def test_unknown_minor_or_patch_tolerated(checker) -> None:
    """Per FR-003a: unknown additive minor/patch fields are tolerated."""
    # Major is 1 (supported); minor/patch larger than what the system was built for is
    # still accepted, because additive minor/patch fields are tolerated and ignored.
    result = checker.check("1.999.999")
    assert result.ok is True

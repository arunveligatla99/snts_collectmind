"""Unit test for the OpenAPI dumper (T132 + T134)."""

from __future__ import annotations

import io
import sys

import yaml

from collectmind.openapi import dump


def test_main_writes_openapi_yaml_to_stdout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = dump.main()
    assert rc == 0
    parsed = yaml.safe_load(buf.getvalue())
    assert isinstance(parsed, dict)
    assert "paths" in parsed
    # Every router declared at app composition (T104) MUST appear.
    paths = parsed["paths"]
    assert "/api/v1/findings" in paths
    assert any("findings" in p and "outcome" in p for p in paths.keys())

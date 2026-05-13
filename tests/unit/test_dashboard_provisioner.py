"""Unit tests for observability/dashboard_provisioner.py (T134)."""

from __future__ import annotations

import json
from pathlib import Path

from collectmind.observability import dashboard_provisioner as dp


def test_declared_metric_names_contains_collectmind_prefix() -> None:
    names = dp.declared_metric_names()
    assert any(n.startswith("collectmind_") for n in names)


def test_referenced_metric_names_extracts_collectmind_tokens_only() -> None:
    targets = [
        {"expr": "sum(rate(collectmind_diagnostic_findings_received_total[1m]))"},
        {"expr": "sum(non_collectmind_metric)"},
        {},  # missing expr
    ]
    refs = dp.referenced_metric_names(targets)
    assert "collectmind_diagnostic_findings_received_total" in refs
    assert "non_collectmind_metric" not in refs


def test_validate_dashboard_on_real_dashboard_returns_empty_or_known_drift(tmp_path: Path) -> None:
    """The shipped dashboard JSON validates clean against the shipped metrics module."""
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / "observability" / "grafana" / "dashboards" / "collectmind-end-to-end.json"
    errors = dp.validate_dashboard(dashboard_path)
    # Phase 5 sweep aligned dashboard refs with declared names; expect no drift.
    assert errors == []


def test_validate_dashboard_flags_undeclared_metric(tmp_path: Path) -> None:
    """A synthetic dashboard JSON that references a non-existent metric must error."""
    bad = {
        "panels": [
            {
                "id": 99,
                "title": "synthetic",
                "targets": [{"expr": "sum(rate(collectmind_made_up_metric_total[1m]))"}],
            }
        ]
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    errors = dp.validate_dashboard(path)
    assert errors
    assert any("collectmind_made_up_metric_total" in e for e in errors)

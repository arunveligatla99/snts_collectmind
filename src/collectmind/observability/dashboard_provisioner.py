"""Validate Grafana dashboard JSON references only declared metrics."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

_METRIC_REF = re.compile(r"\b[a-z][a-z0-9_]*\b")
_SUFFIXES: tuple[str, ...] = ("", "_total", "_created", "_bucket", "_sum", "_count")


def declared_metric_names() -> set[str]:
    """Return every Prometheus series name declared by ``metrics.py``.

    `prometheus_client.Counter` strips the user-supplied ``_total`` suffix
    from the instance's ``_name`` attribute but exposes the series with the
    suffix. Histograms expose ``_bucket``, ``_sum``, and ``_count`` derived
    series. The declared set must include every derived suffix so a
    bidirectional dashboard-to-metrics check produces no false negatives.
    """
    from collectmind.observability import metrics

    names: set[str] = set()
    for attr_name in dir(metrics):
        attr = getattr(metrics, attr_name)
        prom_name = getattr(attr, "_name", None)
        if not isinstance(prom_name, str) or not prom_name.startswith("collectmind_"):
            continue
        for suffix in _SUFFIXES:
            names.add(f"{prom_name}{suffix}")
    return names


def referenced_metric_names(panel_targets: Iterable[dict[str, object]]) -> set[str]:
    refs: set[str] = set()
    for target in panel_targets:
        expr = target.get("expr")
        if isinstance(expr, str):
            for token in _METRIC_REF.findall(expr):
                if token.startswith("collectmind_"):
                    refs.add(token)
    return refs


def validate_dashboard(path: Path) -> list[str]:
    """Return a list of validation error strings; empty list means OK."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    declared = declared_metric_names()
    errors: list[str] = []
    for panel in doc.get("panels", []):
        targets = panel.get("targets", [])
        for ref in referenced_metric_names(targets):
            if declared and ref not in declared:
                errors.append(f"panel {panel.get('id')} references undeclared metric {ref}")
    return errors

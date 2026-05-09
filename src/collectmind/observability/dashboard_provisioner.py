"""Validate Grafana dashboard JSON references only declared metrics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


_METRIC_REF = re.compile(r"\b[a-z][a-z0-9_]*\b")


def declared_metric_names() -> set[str]:
    """Best-effort import of the names registered in collectmind.observability.metrics."""
    from collectmind.observability import metrics

    names: set[str] = set()
    for attr_name in dir(metrics):
        attr = getattr(metrics, attr_name)
        for prom_name_attr in ("_name", "_total"):
            value = getattr(attr, prom_name_attr, None)
            if isinstance(value, str):
                names.add(value)
    return {n for n in names if n}


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

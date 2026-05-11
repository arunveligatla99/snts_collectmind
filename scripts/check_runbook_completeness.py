#!/usr/bin/env python3
"""T113 — CI guard: every Prometheus alert MUST have a runbook entry.

Enforces FR-022. Reads `observability/prometheus/rules.yaml` and walks every
alert. For each alert:

  1. Asserts `annotations.runbook_url` and `annotations.summary` are present
     and non-empty.
  2. Resolves the runbook URL to an on-disk markdown file under
     `observability/runbooks/`.
  3. Asserts the resolved page contains the canonical sections (Symptoms,
     Dashboard, Mitigation, Escalation) at any heading level.

Exit code 0 on success; non-zero with a printed error list on failure.

Wired into `.github/workflows/ci.yaml` (T119) as a dedicated step so the build
fails on missing runbook coverage. Also runnable locally:

    python scripts/check_runbook_completeness.py

The script mirrors `tests/unit/test_alert_runbook_parity.py` so a developer
sees the same failure surface in pytest and in CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = REPO_ROOT / "observability" / "prometheus" / "rules.yaml"
RUNBOOK_DIR = REPO_ROOT / "observability" / "runbooks"

REQUIRED_SECTIONS = ("Symptoms", "Dashboard", "Mitigation", "Escalation")


def _resolve_runbook_target(runbook_url: str) -> Path:
    name = runbook_url
    if "://" in runbook_url:
        _, _, rest = runbook_url.partition("://")
        _, _, name = rest.partition("/")
        name = name.split("?", 1)[0].split("#", 1)[0]
    if "/" in name and not name.startswith("observability/runbooks/"):
        name = name.rsplit("/", 1)[-1]
    if name.startswith("observability/runbooks/"):
        return REPO_ROOT / name
    return RUNBOOK_DIR / name


def _iter_alerts(doc: dict) -> Iterable[tuple[str, str, dict]]:
    for group in doc.get("groups", []):
        group_name = group.get("name", "<unnamed>")
        for rule in group.get("rules", []):
            alert_name = rule.get("alert")
            if alert_name is None:
                continue
            yield group_name, alert_name, rule


def check() -> list[str]:
    errors: list[str] = []
    if not RULES_PATH.is_file():
        return [f"rules.yaml not found at {RULES_PATH}"]
    doc = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    if not doc.get("groups"):
        return ["rules.yaml declares no alert groups"]

    for group_name, alert_name, rule in _iter_alerts(doc):
        annotations = rule.get("annotations") or {}
        runbook_url = annotations.get("runbook_url")
        summary = annotations.get("summary")
        if not runbook_url:
            errors.append(f"{group_name}.{alert_name}: missing annotations.runbook_url")
            continue
        if not summary:
            errors.append(f"{group_name}.{alert_name}: missing annotations.summary")
        target = _resolve_runbook_target(runbook_url)
        if not target.is_file():
            errors.append(
                f"{group_name}.{alert_name}: runbook_url {runbook_url!r} resolves to "
                f"{target} which is missing"
            )
            continue
        body = target.read_text(encoding="utf-8")
        missing = [
            s for s in REQUIRED_SECTIONS
            if not re.search(rf"(?m)^#+\s*{re.escape(s)}\b", body)
        ]
        if missing:
            errors.append(f"{target.name}: missing required section(s) {missing}")
    return errors


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    errors = check()
    if errors:
        print("Runbook completeness check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Runbook completeness check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

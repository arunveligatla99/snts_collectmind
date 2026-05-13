#!/usr/bin/env python3
"""T113 + T283 — CI guard: bidirectional alert↔runbook completeness check.

Enforces FR-022 in BOTH directions:

  Forward (feature-001 T113):
    Every Prometheus alert in ``observability/prometheus/rules.yaml`` MUST link to a
    runbook page under ``observability/runbooks/`` AND the page MUST contain the four
    canonical sections (Symptoms / Dashboard / Mitigation / Escalation).

  Backward (feature-002 T283):
    Every Markdown runbook page under ``observability/runbooks/`` MUST be referenced
    by at least one alert's ``runbook_url`` annotation OR be listed in the
    operational-reference whitelist at ``observability/runbooks/.orphan-whitelist.yaml``.

Exit code 0 on success; non-zero with a printed error list on failure.

Wired into ``.github/workflows/ci.yaml``'s ``custom-guards`` job. Also runnable locally:

    python scripts/check_runbook_completeness.py

The script mirrors ``tests/unit/test_alert_runbook_parity.py`` and
``tests/unit/test_runbook_completeness_bidirectional.py`` so a developer sees the
same failure surface in pytest and in CI.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = REPO_ROOT / "observability" / "prometheus" / "rules.yaml"
RUNBOOK_DIR = REPO_ROOT / "observability" / "runbooks"
ORPHAN_WHITELIST_PATH = RUNBOOK_DIR / ".orphan-whitelist.yaml"

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


def _load_orphan_whitelist(path: Path = ORPHAN_WHITELIST_PATH) -> set[str]:
    """Read the orphan-runbook whitelist YAML file. Returns a set of basenames.

    Missing file returns an empty set (CI guard treats every runbook as alert-required).
    Malformed file raises — the guard runs only when the whitelist is well-formed.
    """
    if not path.is_file():
        return set()
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = doc.get("whitelist") or []
    return {str(entry) for entry in entries}


def find_orphan_runbooks(
    rules_doc: dict,
    runbook_dir: Path,
    whitelist: set[str] | None = None,
) -> list[str]:
    """Return basenames of runbook pages under ``runbook_dir`` that have NO alert.

    Takes a parsed ``rules.yaml`` doc, a runbook directory, and an optional whitelist
    set. Returns a sorted list of orphan basenames; empty list means the bidirectional
    invariant holds.

    A runbook is orphan when:
        - Its filename is not in the whitelist set, AND
        - No alert in ``rules_doc`` has ``annotations.runbook_url`` resolving to it.

    ``whitelist`` parameter contract:
        - ``None`` (default): load from ``<runbook_dir>/.orphan-whitelist.yaml`` if it
          exists; empty set otherwise. CI mode passes ``None`` so the canonical
          whitelist applies without per-invocation arguments.
        - Explicit ``set[str]``: caller-provided whitelist; the file is NOT consulted.
          Synthetic tests use this path.
    """
    if not runbook_dir.is_dir():
        return []
    if whitelist is None:
        whitelist = _load_orphan_whitelist(runbook_dir / ".orphan-whitelist.yaml")

    referenced: set[str] = set()
    for _group, _alert, rule in _iter_alerts(rules_doc):
        url = (rule.get("annotations") or {}).get("runbook_url")
        if not url:
            continue
        target = _resolve_runbook_target(url)
        referenced.add(target.name)

    orphans: list[str] = []
    for entry in sorted(runbook_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".md":
            continue
        if entry.name in whitelist:
            continue
        if entry.name in referenced:
            continue
        orphans.append(entry.name)
    return orphans


def check() -> list[str]:
    errors: list[str] = []
    if not RULES_PATH.is_file():
        return [f"rules.yaml not found at {RULES_PATH}"]
    doc = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    if not doc.get("groups"):
        return ["rules.yaml declares no alert groups"]

    # Forward direction: every alert MUST have a runbook page with canonical sections.
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
                f"{group_name}.{alert_name}: runbook_url {runbook_url!r} resolves to {target} which is missing"
            )
            continue
        body = target.read_text(encoding="utf-8")
        missing = [s for s in REQUIRED_SECTIONS if not re.search(rf"(?m)^#+\s*{re.escape(s)}\b", body)]
        if missing:
            errors.append(f"{target.name}: missing required section(s) {missing}")

    # Backward direction: every runbook MUST be alert-referenced OR whitelisted.
    whitelist = _load_orphan_whitelist()
    orphans = find_orphan_runbooks(doc, RUNBOOK_DIR, whitelist=whitelist)
    for orphan in orphans:
        errors.append(
            f"orphan runbook {orphan!r}: not referenced by any alert and not in "
            f"observability/runbooks/.orphan-whitelist.yaml"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
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

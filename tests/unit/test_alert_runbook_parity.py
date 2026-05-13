"""T106: Every Prometheus alert rule MUST have a corresponding runbook entry.

Encodes FR-022's "ship with a runbook entry for every alert" requirement as a
unit-tier check that the T113 CI guard (`scripts/check_runbook_completeness.py`)
must also enforce. Running the check in pytest as well lets a developer surface
the failure before opening a PR.

Loads `observability/prometheus/rules.yaml`, walks every alert in every group,
and asserts:

1. Each alert declares `annotations.runbook_url` and `annotations.summary`.
2. The `runbook_url` resolves to a markdown file that exists under
   `observability/runbooks/`. Both fully qualified file:// and bare relative
   paths are accepted; HTTP runbook URLs MUST end in a path component that
   matches an existing file (the CI guard is the source of truth for that
   mapping; the test mirrors it).
3. The runbook page itself contains the mandatory sections enumerated in
   `observability/runbooks/INDEX.md`: Symptoms, Dashboard, Mitigation,
   Escalation. (The INDEX lists "Related ADRs" and "Related FRs" too; they are
   highly recommended but not enforced here so a runbook can be authored
   without inventing an ADR cross-reference for every alert.)
4. The rule set covers one alert per binding SLO listed in T111: SC-001
   (latency), SC-002 (success rate), SC-003 (soak), SC-004 (query latency),
   SC-005 (recovery), SC-006 (dashboard lag), SC-010 (outcome write delay),
   SC-012 (availability). This pins the breadth of the alert surface.

Per FR-021 / Principle IV this test exists before T111 (rules YAML) and T112
(runbook pages) land. Until both land, the test fails at the rules.yaml load
step (red phase).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / "observability" / "prometheus" / "rules.yaml"
RUNBOOK_DIR = REPO_ROOT / "observability" / "runbooks"

REQUIRED_SECTIONS = ("Symptoms", "Dashboard", "Mitigation", "Escalation")

REQUIRED_SLO_TAGS: tuple[str, ...] = (
    "SC-001",
    "SC-002",
    "SC-003",
    "SC-004",
    "SC-005",
    "SC-006",
    "SC-010",
    "SC-012",
)


def _load_rules() -> dict:
    assert RULES_PATH.is_file(), f"alert rules YAML missing at {RULES_PATH} — T111 must author it before T106 passes"
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}


def _iter_alerts(doc: dict):
    for group in doc.get("groups", []):
        group_name = group.get("name", "<unnamed>")
        for rule in group.get("rules", []):
            alert_name = rule.get("alert")
            if alert_name is None:
                continue  # recording rule, not an alert
            yield group_name, alert_name, rule


def _resolve_runbook_target(runbook_url: str) -> Path:
    """Map a runbook URL or path to the on-disk markdown file expected.

    Accepted shapes:
      - relative path under `observability/runbooks/` (e.g. `slo-001-latency.md`)
      - `file://` URL pointing into the runbooks directory
      - HTTP(S) URL whose final path segment matches `<page>.md` under the
        runbooks directory
    """
    name = runbook_url
    if "://" in runbook_url:
        # strip scheme + host
        _, _, rest = runbook_url.partition("://")
        _, _, name = rest.partition("/")
        name = name.split("?", 1)[0].split("#", 1)[0]
    # collapse to final segment if a slash remains and the leading segments
    # are not "observability/runbooks/"
    if "/" in name and not name.startswith("observability/runbooks/"):
        name = name.rsplit("/", 1)[-1]
    if name.startswith("observability/runbooks/"):
        return REPO_ROOT / name
    return RUNBOOK_DIR / name


def test_rules_yaml_loads() -> None:
    doc = _load_rules()
    assert doc.get("groups"), "rules.yaml must declare at least one group"


def test_every_alert_declares_required_annotations() -> None:
    doc = _load_rules()
    missing: list[str] = []
    for group_name, alert_name, rule in _iter_alerts(doc):
        annotations = rule.get("annotations") or {}
        for key in ("runbook_url", "summary"):
            if not annotations.get(key):
                missing.append(f"{group_name}.{alert_name}: missing annotations.{key}")
    assert not missing, "alerts missing required annotations:\n  - " + "\n  - ".join(missing)


def test_every_alert_runbook_resolves_to_existing_page() -> None:
    doc = _load_rules()
    misses: list[str] = []
    for group_name, alert_name, rule in _iter_alerts(doc):
        url = (rule.get("annotations") or {}).get("runbook_url")
        if not url:
            continue  # covered by the annotations test above
        target = _resolve_runbook_target(url)
        if not target.is_file():
            misses.append(f"{group_name}.{alert_name}: runbook_url {url!r} resolves to {target} which is missing")
    assert not misses, "runbook pages missing for alert(s):\n  - " + "\n  - ".join(misses)


def test_every_alert_runbook_contains_required_sections() -> None:
    doc = _load_rules()
    failures: list[str] = []
    for group_name, alert_name, rule in _iter_alerts(doc):
        url = (rule.get("annotations") or {}).get("runbook_url")
        if not url:
            continue
        target = _resolve_runbook_target(url)
        if not target.is_file():
            continue  # covered by the previous test
        body = target.read_text(encoding="utf-8")
        missing_sections = [s for s in REQUIRED_SECTIONS if not re.search(rf"(?m)^#+\s*{re.escape(s)}\b", body)]
        if missing_sections:
            failures.append(f"{target.name}: missing sections {missing_sections}")
    assert not failures, "runbook page(s) missing required sections:\n  - " + "\n  - ".join(failures)


def test_rules_cover_every_binding_slo() -> None:
    """The alert surface MUST include one rule per binding SLO from T111."""
    doc = _load_rules()
    rendered = yaml.safe_dump(doc)
    missing = [tag for tag in REQUIRED_SLO_TAGS if tag not in rendered]
    assert not missing, (
        f"rules.yaml does not reference SLO tag(s) {missing}; T111 requires one alert per "
        f"binding SLO. Tag each alert by name, label, or annotation so this check finds it."
    )

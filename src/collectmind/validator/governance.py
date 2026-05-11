"""Data governance checker (T072). PII-adjacent flagging + consent enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _default_path() -> Path:
    here = Path(__file__).resolve()
    container = here.parent.parent.parent / "config" / "vss" / "v6.0" / "pii_signals.yaml"
    if container.exists():
        return container
    return here.parents[3] / "config" / "vss" / "v6.0" / "pii_signals.yaml"


_DEFAULT_PATH = _default_path()


@dataclass(frozen=True)
class GovernanceDecision:
    ok: bool
    code: str | None = None
    flagged_signals: tuple[str, ...] = ()


class DataGovernanceChecker:
    """Flags PII-adjacent signals; enforces explicit consent flag (FR-006, Principle X)."""

    def __init__(self, branches: tuple[str, ...], prefix_match: bool = True) -> None:
        self._branches = tuple(sorted(branches))
        self._prefix_match = prefix_match

    @classmethod
    @lru_cache(maxsize=1)
    def from_default_config(cls) -> DataGovernanceChecker:
        return cls.from_path(_DEFAULT_PATH)

    @classmethod
    def from_path(cls, path: Path) -> DataGovernanceChecker:
        doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        categories = doc.get("categories", {})
        branches: list[str] = []
        for category in categories.values():
            for branch in category.get("branches", []):
                branches.append(str(branch))
        return cls(branches=tuple(branches), prefix_match=bool(doc.get("prefix_match", True)))

    def is_pii(self, signal_name: str) -> bool:
        if signal_name in self._branches:
            return True
        if self._prefix_match:
            for branch in self._branches:
                if signal_name.startswith(branch + "."):
                    return True
        return False

    def evaluate_signals(self, signals: list[str], consent: bool) -> GovernanceDecision:
        flagged = tuple(sorted({s for s in signals if self.is_pii(s)}))
        if flagged and not consent:
            return GovernanceDecision(
                ok=False,
                code="PII_CONSENT_REQUIRED",
                flagged_signals=flagged,
            )
        return GovernanceDecision(ok=True, flagged_signals=flagged)

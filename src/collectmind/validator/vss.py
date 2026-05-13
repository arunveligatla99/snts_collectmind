"""VSS validator (T071). Loads config/vss/v6.0/signals.yaml; closest-name suggestion."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _default_path() -> Path:
    here = Path(__file__).resolve()
    # Container: /app/collectmind/validator/vss.py -> /app/config/vss/v6.0/signals.yaml
    container = here.parent.parent.parent / "config" / "vss" / "v6.0" / "signals.yaml"
    if container.exists():
        return container
    # Repo: src/collectmind/validator/vss.py -> repo_root/config/vss/v6.0/signals.yaml
    return here.parents[3] / "config" / "vss" / "v6.0" / "signals.yaml"


_DEFAULT_PATH = _default_path()


@dataclass(frozen=True)
class SignalValidationResult:
    ok: bool
    name: str
    code: str | None = None
    suggestion: str | None = None


class VSSValidator:
    """Looks up signal names against the pinned VSS v6.0 vocabulary (ADR-0001)."""

    def __init__(self, signals: dict[str, dict[str, Any]]) -> None:
        self._signals = signals
        self._names = tuple(signals.keys())

    @classmethod
    @lru_cache(maxsize=1)
    def from_default_config(cls) -> VSSValidator:
        return cls.from_path(_DEFAULT_PATH)

    @classmethod
    def from_path(cls, path: Path) -> VSSValidator:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        signals = doc.get("signals", {}) if isinstance(doc, dict) else {}
        return cls(signals=signals)

    def is_valid(self, name: str) -> bool:
        return name in self._signals

    def metadata(self, name: str) -> dict[str, Any] | None:
        return self._signals.get(name)

    def validate_signal(self, name: str) -> SignalValidationResult:
        if name in self._signals:
            return SignalValidationResult(ok=True, name=name)
        suggestion = self._closest(name)
        return SignalValidationResult(
            ok=False,
            name=name,
            code="VSS_INVALID_SIGNAL",
            suggestion=suggestion,
        )

    def _closest(self, name: str) -> str | None:
        if not name:
            return None
        matches = difflib.get_close_matches(name, self._names, n=1, cutoff=0.85)
        return matches[0] if matches else None

    def all_names(self) -> tuple[str, ...]:
        return self._names

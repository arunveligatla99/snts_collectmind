"""CI guard for Constitution Principle III: no TODO, FIXME, or deferred-work markers.

Enforces that the source tree carries no ``TODO``, ``FIXME``, ``XXX``, or
``@todo`` markers. Deferred concerns live in the spec, in an ADR, or as a
GitHub issue, never in the code.

Walks repo-managed source under ``src/``, ``tests/``, ``infra/``,
``observability/``, ``config/``, ``prompts/``, plus shell wrappers. Skips:

- Any path under any ``.venv*`` / ``venv`` directory (this script is also
  runnable outside CI, where the developer's local virtualenv lives in-tree).
- ``.git``, ``.hypothesis``, ``.mypy_cache``, ``.ruff_cache``,
  ``.pytest_cache``, ``__pycache__``, ``build``, ``dist``, ``node_modules``,
  ``models``.
- The directories whose role is to *describe* deferred work or ADRs:
  ``docs/``, ``specs/``, ``.specify``, ``.claude``.
- This script itself (so the regex literal doesn't trigger the regex).

Exit code 0 on pass; 1 on any hit. Hits print as ``path:lineno: line``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PATTERN = re.compile(r"\b(TODO|FIXME|XXX|@todo)\b", re.IGNORECASE)
_INCLUDE_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".toml", ".sh", ".dockerfile", ".tf"}
_EXCLUDE_PREFIXES = (
    ".git/",
    ".hypothesis/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
    ".specify/",
    ".claude/",
    "docs/",
    "specs/",
    "models/",
    "node_modules/",
    "build/",
    "dist/",
    "scripts/check_no_todo_fixme.py",  # self
    ".pre-commit-config.yaml",  # hook id "no-todo-fixme" mentions the marker words
)
_VENV_HINT = re.compile(r"(^|/)(\.?venv[^/]*)(/|$)")


def _excluded(rel_posix: str) -> bool:
    if any(rel_posix.startswith(prefix) for prefix in _EXCLUDE_PREFIXES):
        return True
    if "__pycache__" in rel_posix:
        return True
    if "/node_modules/" in rel_posix or rel_posix.endswith("/node_modules"):
        return True
    if "/coverage/" in rel_posix or "/dist/" in rel_posix:
        return True
    if _VENV_HINT.search(rel_posix):
        return True
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    violations: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel_posix = path.relative_to(repo_root).as_posix()
        if _excluded(rel_posix):
            continue
        if path.suffix.lower() not in _INCLUDE_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _PATTERN.search(line):
                violations.append(f"{rel_posix}:{lineno}: {line.strip()}")

    if violations:
        print("Principle III violations (no TODO/FIXME/XXX/@todo):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "Deferred work belongs in the spec, an ADR, or a GitHub issue, never the source tree.",
            file=sys.stderr,
        )
        return 1
    print("No TODO/FIXME/XXX/@todo markers in source tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

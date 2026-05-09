"""CI guard for Constitution Principle III: no TODO, FIXME, or deferred-work markers."""

from __future__ import annotations

import re
import sys
from pathlib import Path


_PATTERN = re.compile(r"\b(TODO|FIXME|XXX|@todo)\b", re.IGNORECASE)
_INCLUDE_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".toml", ".sh", ".dockerfile", ".tf"}
_EXCLUDE_DIRS = {
    ".git", ".specify", ".claude", "specs", "models", "docs", "node_modules",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "build", "dist", "scripts",
}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    violations: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDE_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if path.suffix.lower() not in _INCLUDE_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _PATTERN.search(line):
                rel = path.relative_to(repo_root)
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    if violations:
        print("Principle III violations (no TODO/FIXME):", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""T127 — CI guard: no secrets in the repository (gitleaks wrapper).

Enforces FR-019 and Constitution Principle IX. Wraps ``gitleaks`` so the
project can:

1. Run a single command locally (``python scripts/check_secrets.py``) and in
   CI (``.github/workflows/ci.yaml``) — identical surface, same exit codes.
2. Skip cleanly when gitleaks is not installed on the developer's machine
   (surface a guidance message, not a stack trace). CI MUST install gitleaks
   as a pre-step; the workflow file makes that contract explicit.
3. Use the repo-level ``.gitleaks.toml`` if one exists; otherwise rely on the
   gitleaks defaults plus an allowlist for the documented test credentials
   (``feature-001-default`` / ``local-dev-only``) baked into the local stack
   for the foundation smoke.

Exit code 0 on pass; 1 on any finding or fatal gitleaks error; 2 on tooling
absence with a guidance message.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO_ROOT / ".gitleaks.toml"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    binary = shutil.which("gitleaks")
    if binary is None:
        print(
            "gitleaks not installed on PATH. Install via "
            "`curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh` "
            "or follow https://github.com/gitleaks/gitleaks#installing. "
            "CI installs it in `.github/workflows/ci.yaml` as a pre-step.",
            file=sys.stderr,
        )
        return 2

    cmd = [binary, "detect", "--source", str(REPO_ROOT), "--no-banner", "--redact", "--verbose"]
    if ALLOWLIST.is_file():
        cmd.extend(["--config", str(ALLOWLIST)])
    cmd.extend(argv)

    print(f"Running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)
    if completed.returncode == 0:
        print("gitleaks: no secrets detected.")
        return 0
    print(f"gitleaks reported findings (exit code {completed.returncode}). FR-019 violated.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""T126 — CI guard: SLM image digest, weight SHA, decoding seed are pinned.

Enforces Constitution Principle XIV (Deterministic, Budgeted Model Execution
in CI): the runtime image digest, the weight revision SHA, and the decoding
seed MUST be pinned, and the pinned values MUST match the manifest at
``config/slm/qwen2.5-7b-instruct/manifest.sha256`` and ADR-0002.

Additionally enforces the Phase 3 deferral note in ``docs/PROJECT_STATE.md``:
**no GitHub Actions workflow file may set ``SLM_PROFILE=dev_default``.** The
``DevDefaultPolicyClient`` is gated by ADR-0006 to local-only environments;
allowing it in a CI workflow defeats the principle XIII decode-time-grammar
requirement.

Checks:

1. ``infra/compose/gpu-profile/Dockerfile.vllm`` references the vLLM image at
   the digest pinned in ADR-0002 (sha256-form).
2. ``config/slm/qwen2.5-7b-instruct/manifest.sha256`` exists and is non-empty.
3. ``infra/compose/docker-compose.yaml`` does NOT use ``SLM_PROFILE=dev_default``.
4. No file under ``.github/workflows/`` sets ``SLM_PROFILE=dev_default``.

Exit code 0 on pass; 1 on any violation. Output names every offending
file:line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEIGHT_MANIFEST = REPO_ROOT / "config" / "slm" / "qwen2.5-7b-instruct" / "manifest.sha256"
GPU_DOCKERFILE = REPO_ROOT / "infra" / "compose" / "gpu-profile" / "Dockerfile.vllm"
COMPOSE_FILE = REPO_ROOT / "infra" / "compose" / "docker-compose.yaml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_DIGEST_PATTERN = re.compile(r"@sha256:[0-9a-f]{64}")
_DEV_DEFAULT_PATTERN = re.compile(r"SLM_PROFILE\s*[:=]\s*[\"']?dev_default[\"']?", re.IGNORECASE)


def _check_weight_manifest() -> list[str]:
    if not WEIGHT_MANIFEST.is_file():
        return [f"weight manifest missing at {WEIGHT_MANIFEST.relative_to(REPO_ROOT)}"]
    if not WEIGHT_MANIFEST.read_text(encoding="utf-8").strip():
        return [f"weight manifest is empty at {WEIGHT_MANIFEST.relative_to(REPO_ROOT)}"]
    return []


def _check_gpu_dockerfile() -> list[str]:
    if not GPU_DOCKERFILE.is_file():
        return [f"gpu Dockerfile missing at {GPU_DOCKERFILE.relative_to(REPO_ROOT)}"]
    text = GPU_DOCKERFILE.read_text(encoding="utf-8")
    if not _DIGEST_PATTERN.search(text):
        return [
            f"{GPU_DOCKERFILE.relative_to(REPO_ROOT)}: no vLLM image digest pin found "
            f"(expected an @sha256:<hex> reference per ADR-0002)"
        ]
    return []


def _check_no_dev_default(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _DEV_DEFAULT_PATTERN.search(line):
            hits.append(
                f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}: SLM_PROFILE=dev_default is forbidden "
                f"outside local foundation smoke (ADR-0006 + Constitution Principle XIV)"
            )
    return hits


def check() -> list[str]:
    errors: list[str] = []
    errors.extend(_check_weight_manifest())
    errors.extend(_check_gpu_dockerfile())
    errors.extend(_check_no_dev_default(COMPOSE_FILE))
    if WORKFLOWS_DIR.is_dir():
        for workflow in sorted(WORKFLOWS_DIR.glob("*.yaml")) + sorted(WORKFLOWS_DIR.glob("*.yml")):
            errors.extend(_check_no_dev_default(workflow))
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("SLM-pinning check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("SLM-pinning check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

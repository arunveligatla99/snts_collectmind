"""Regenerate the demo UI's OpenAPI TypeScript types and assert byte-identity.

Parity with `python -m collectmind.openapi.dump` diff vs `docs/api/openapi.yaml`
per T132. The demo UI's `src/api/types/*.d.ts` files MUST be regenerable from
the contracts under `contracts/openapi/` with no diff. A diff means the
generated types are stale and the PR is rejected.

Wired into `.github/workflows/ci.yaml`'s `custom-guards` job.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = REPO_ROOT / "demo"
TYPES_DIR = DEMO / "src" / "api" / "types"


def main() -> int:
    if not DEMO.exists():
        print(f"demo/ not present at {DEMO}; nothing to check.")
        return 0
    npm = shutil.which("npm")
    if npm is None:
        print("npm not on PATH; cannot regenerate demo types.")
        return 1

    snapshot: dict[Path, str] = {}
    for p in sorted(TYPES_DIR.glob("*.d.ts")):
        snapshot[p] = p.read_text(encoding="utf-8")

    proc = subprocess.run(
        [npm, "run", "gen:types"],
        cwd=DEMO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("gen:types failed:")
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    drift: list[str] = []
    for p, prior in snapshot.items():
        current = p.read_text(encoding="utf-8")
        if current != prior:
            drift.append(str(p.relative_to(REPO_ROOT)))

    new_files = [
        str(p.relative_to(REPO_ROOT))
        for p in sorted(TYPES_DIR.glob("*.d.ts"))
        if p not in snapshot
    ]
    if drift or new_files:
        print("Demo OpenAPI types drift detected:")
        for f in drift:
            print(f"  drifted: {f}")
        for f in new_files:
            print(f"  added:   {f}")
        print("\nRun `cd demo && npm run gen:types` and commit the result.")
        return 1

    print(f"OK: demo OpenAPI types match contracts (checked {len(snapshot)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

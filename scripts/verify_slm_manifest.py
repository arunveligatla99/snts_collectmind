"""Verify SLM weight artifacts against the SHA-256 manifest (Principle IX, ADR-0002)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main(weights_root: str, manifest_path: str) -> int:
    root = Path(weights_root)
    manifest = Path(manifest_path)
    if not manifest.exists():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        return 1
    failures = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            expected, relative = line.split(maxsplit=1)
        except ValueError:
            print(f"manifest line malformed: {line!r}", file=sys.stderr)
            failures += 1
            continue
        target = root / relative.strip()
        if not target.exists():
            print(f"missing artifact: {target}", file=sys.stderr)
            failures += 1
            continue
        actual = _sha256_file(target)
        if actual != expected:
            print(f"sha256 mismatch: {target} expected={expected} actual={actual}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: verify_slm_manifest.py <weights_root> <manifest>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))

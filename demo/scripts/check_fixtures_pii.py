"""PII gate over demo/public/recordings/ — parity with scripts/check_log_pii.py.

Refuses any fixture whose JSON body matches:
- email     ([^\\s@]+@[^\\s@]+\\.[^\\s@]+)
- E.164     (\\+\\d{8,15})
- US SSN    (\\b\\d{3}-\\d{2}-\\d{4}\\b)
- decimal lat/long pair within plausible bounds

Run via: python demo/scripts/check_fixtures_pii.py demo/public/recordings/

Wired into record_fixtures.sh and into the demo's CI step.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
PHONE_RE = re.compile(r"\+\d{8,15}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
LATLONG_RE = re.compile(
    r"-?(?:[1-8]?\d(?:\.\d{4,})|90(?:\.0+)?)"
    r"\s*,\s*"
    r"-?(?:1[0-7]\d(?:\.\d{4,})|[1-9]?\d(?:\.\d{4,})|180(?:\.0+)?)"
)


def scan_text(blob: str) -> list[str]:
    hits: list[str] = []
    for name, regex in (
        ("email", EMAIL_RE),
        ("phone_e164", PHONE_RE),
        ("us_ssn", SSN_RE),
        ("lat_long_pair", LATLONG_RE),
    ):
        for m in regex.findall(blob):
            hits.append(f"{name}: {m!r}")
    return hits


def walk(node: Any, sink: list[str]) -> None:
    if isinstance(node, str):
        sink.extend(scan_text(node))
    elif isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                sink.extend(scan_text(k))
            walk(v, sink)
    elif isinstance(node, list):
        for item in node:
            walk(item, sink)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_fixtures_pii.py <recordings-dir>", file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 2
    failures: dict[str, list[str]] = {}
    files = sorted(root.rglob("*.json"))
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            failures[str(f)] = [f"unparsable JSON: {e}"]
            continue
        hits: list[str] = []
        walk(data, hits)
        if hits:
            failures[str(f.relative_to(root))] = hits
    if failures:
        print("PII gate FAIL on demo fixtures:")
        for f, hits in failures.items():
            print(f"  {f}")
            for h in hits:
                print(f"    - {h}")
        return 1
    print(f"PII gate PASS over {len(files)} fixture(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

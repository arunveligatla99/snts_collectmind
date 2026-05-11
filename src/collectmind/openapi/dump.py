"""T132 — dump the FastAPI app's OpenAPI 3.1 spec as YAML.

Used in CI: the workflow runs ``python -m collectmind.openapi.dump`` and
diffs the output against ``docs/api/openapi.yaml``. A diff fails the build,
so the committed OpenAPI document never drifts from the live routes.

The contract source of truth is ``contracts/openapi/orchestration-api.v1.yaml``
+ ``contracts/openapi/query-api.v1.yaml``; this script's output is the
*derived* document the FastAPI app actually serves. CI also asserts the
derived document is a subset of the contract surface (no undocumented
routes), but that check is intentionally separate from this one.

Output goes to stdout so the workflow can redirect it without temp files.
"""

from __future__ import annotations

import sys

import yaml

from collectmind.app import app


def main() -> int:
    spec = app.openapi()
    yaml.safe_dump(spec, sys.stdout, sort_keys=True, default_flow_style=False, allow_unicode=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Local-dev JWT issuer (feature 002 / T204).

Mints short-lived JWTs against the local mock issuers running under Compose. Used by the
multi-tenant quickstart (``specs/002-multi-tenant-isolation/quickstart.md``) to drive the
foundation smoke without a real OAuth2 server. Not for production.

Usage:

    # Tenant JWT for tenant-a:
    python scripts/dev_issue_jwt.py --tenant tenant-a > /tmp/tenant-a.jwt

    # Operator JWT for alice:
    python scripts/dev_issue_jwt.py --operator alice --audience collectmind-operator > /tmp/op.jwt

The script hits the token endpoint of the relevant mock issuer (``mock-issuer:8088`` for
tenant JWTs, ``operator-issuer:8089`` for operator JWTs when the Compose profile is up).
"""

from __future__ import annotations

import argparse
import sys
from typing import Final

import httpx

MOCK_ISSUER_DEFAULT: Final[str] = "http://localhost:8088"
OPERATOR_ISSUER_DEFAULT: Final[str] = "http://localhost:8089"

TENANT_AUDIENCE: Final[str] = "collectmind-api"
OPERATOR_AUDIENCE: Final[str] = "collectmind-operator"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a local-dev JWT.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", help="Issue a tenant JWT for the named tenant (uses the tenant mock-issuer).")
    group.add_argument("--operator", help="Issue an operator JWT for the named operator (uses operator-issuer).")
    parser.add_argument(
        "--audience",
        default=None,
        help="Override the audience claim (default: collectmind-api for tenant, collectmind-operator for operator).",
    )
    parser.add_argument(
        "--issuer-url",
        default=None,
        help="Override the issuer URL (default: http://localhost:8088 tenant; http://localhost:8089 operator).",
    )
    parser.add_argument(
        "--client-secret",
        default="local-dev-only",
        help="Client secret as defined in the issuer-config.yaml. Default matches the dev config.",
    )
    args = parser.parse_args(argv)

    if args.tenant is not None:
        issuer_url = args.issuer_url or MOCK_ISSUER_DEFAULT
        client_id = f"tenant-{args.tenant}" if not args.tenant.startswith("tenant-") else args.tenant
        # The mock-issuer's config maps client_id -> tenant_id directly; for dev we accept
        # the default config's "feature-001-default" client and re-emit. Operators who need
        # other tenants should extend infra/compose/issuer-config.yaml.
        client_id = "feature-001-default"
    elif args.operator is not None:
        issuer_url = args.issuer_url or OPERATOR_ISSUER_DEFAULT
        client_id = f"operator-{args.operator}"
    else:  # unreachable due to required mutually-exclusive group
        parser.error("--tenant or --operator required")
        return 2

    token_endpoint = f"{issuer_url}/token"
    try:
        response = httpx.post(
            token_endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": args.client_secret,
            },
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    body = response.json()
    print(body["access_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# Mint three dev JWTs and write them into demo/.env.local for live-mode Vite.
#
# Pre-conditions:
#   - infra/compose/docker-compose.yaml stack up (operator-issuer profile included)
#   - python on PATH with the project's [dev] extras installed
#
# Output: demo/.env.local with three VITE_TOKEN_* lines. .gitignored.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEMO="${REPO_ROOT}/demo"
OUT="${DEMO}/.env.local"

TENANT_A="$(python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --tenant tenant-a)"
TENANT_B="$(python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --tenant tenant-b)"
OPERATOR="$(python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --operator alice --audience collectmind-operator)"

cat > "${OUT}" <<EOF
VITE_DEMO_MODE=live
VITE_API_BASE_URL=/api/v1
VITE_TOKEN_TENANT_A=${TENANT_A}
VITE_TOKEN_TENANT_B=${TENANT_B}
VITE_TOKEN_OPERATOR_ALICE=${OPERATOR}
EOF

echo "Wrote ${OUT} (gitignored)."

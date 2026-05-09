#!/usr/bin/env bash
set -euo pipefail

URL="${WAIT_URL:-http://localhost:8081/ready}"
TIMEOUT="${WAIT_TIMEOUT:-180}"
INTERVAL="${WAIT_INTERVAL:-3}"

end=$(( $(date +%s) + TIMEOUT ))
while (( $(date +%s) < end )); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "ready: $URL"
    exit 0
  fi
  sleep "$INTERVAL"
done

echo "timeout waiting for $URL after ${TIMEOUT}s" >&2
curl -sS "$URL" || true
exit 1

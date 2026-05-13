#!/usr/bin/env bash
# Record CollectMind golden-path fixtures for the demo UI's recorded mode.
#
# Boots the local Compose stack, mints two tenant JWTs + one operator JWT via
# scripts/dev_issue_jwt.py, drives the end-to-end loop against tenant-a + tenant-b,
# captures every response into demo/public/recordings/, and writes the index file.
#
# Outputs every fixture in the shape consumed by demo/src/api/fixtures.ts:
#   { "METHOD /path principal optional-body-json": { status, body, headers?, retryAfterSeconds? } }
#
# Usage (from repo root):
#   bash demo/scripts/record_fixtures.sh
#
# Pre-conditions:
#   - Docker Desktop running
#   - python on PATH with the project's [dev] extras installed
#   - jq on PATH (Windows: choco install jq)
#
# Post-conditions:
#   - demo/public/recordings/index.json populated
#   - demo/public/recordings/<endpoint>/<key>.json per response
#   - demo/scripts/check_fixtures_pii.py PASS

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEMO_RECORDINGS="${REPO_ROOT}/demo/public/recordings"
TOKEN_DIR="${REPO_ROOT}/.demo-tokens"
ORCH="http://localhost:8081/api/v1"

mkdir -p "${DEMO_RECORDINGS}" "${TOKEN_DIR}"

echo "==> Compose up"
docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yaml" --profile operator-issuer up -d

echo "==> Wait for /ready"
until curl -fsS "${ORCH%/api/v1}/ready" >/dev/null 2>&1; do sleep 2; done
echo "READY"

echo "==> Mint tokens"
python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --tenant tenant-a > "${TOKEN_DIR}/tenant-a.jwt"
python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --tenant tenant-b > "${TOKEN_DIR}/tenant-b.jwt"
python "${REPO_ROOT}/scripts/dev_issue_jwt.py" --operator alice --audience collectmind-operator > "${TOKEN_DIR}/operator-alice.jwt"
TA="$(cat "${TOKEN_DIR}/tenant-a.jwt")"
TB="$(cat "${TOKEN_DIR}/tenant-b.jwt")"
OP="$(cat "${TOKEN_DIR}/operator-alice.jwt")"

echo "==> Seed tenants and vehicle assignments"
# (Idempotent inserts; the feature 002 quickstart documents the same wires.)
psql "${POSTGRES_URL:-postgresql://collectmind:collectmind@localhost:5432/collectmind}" -c "
  INSERT INTO tenants(tenant_id, created_at)
    VALUES ('tenant-a', now()), ('tenant-b', now())
    ON CONFLICT DO NOTHING;
  INSERT INTO tenant_vehicles(vehicle_id, tenant_id, assigned_at, assigned_by_subject, reason_code)
    VALUES ('VIN-AAAA-0001', 'tenant-a', now(), 'service-principal://record_fixtures.sh', 'initial_provisioning'),
           ('VIN-BBBB-0001', 'tenant-b', now(), 'service-principal://record_fixtures.sh', 'initial_provisioning')
    ON CONFLICT DO NOTHING;
"

INDEX="{}"

record() {
  local method="$1" path="$2" principal="$3" body="$4" outfile="$5"
  local key="${method} ${path} ${principal} ${body}"
  local response status headers
  local hdr
  hdr="$(mktemp)"
  local token
  case "${principal}" in
    tenant-a)        token="${TA}";;
    tenant-b)        token="${TB}";;
    operator-alice)  token="${OP}";;
    *) token="";;
  esac
  if [ -n "${body}" ]; then
    response="$(curl -sS -o /tmp/resp.json -w "%{http_code}" -X "${method}" "${ORCH}${path}" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -D "${hdr}" \
      --data "${body}")" || true
  else
    response="$(curl -sS -o /tmp/resp.json -w "%{http_code}" -X "${method}" "${ORCH}${path}" \
      -H "Authorization: Bearer ${token}" \
      -D "${hdr}")" || true
  fi
  status="${response}"
  mkdir -p "$(dirname "${DEMO_RECORDINGS}/${outfile}")"
  cp /tmp/resp.json "${DEMO_RECORDINGS}/${outfile}"
  local retry_after
  retry_after="$(awk 'tolower($1)=="retry-after:" {print $2}' "${hdr}" | tr -d $'\r\n')"
  INDEX="$(jq --arg k "${key// /·}" \
              --argjson s "${status}" \
              --slurpfile b "${DEMO_RECORDINGS}/${outfile}" \
              --arg ra "${retry_after}" '
       .[$k] = {
         status: $s,
         body: $b[0],
         retryAfterSeconds: (if $ra == "" then null else ($ra|tonumber) end)
       } | with_entries(if .value.retryAfterSeconds == null then .value |= del(.retryAfterSeconds) else . end)
    ' <<<"${INDEX}")"
  rm -f "${hdr}"
}

# --- Golden path: tenant-a submits brake-wear, audit chain materializes ---
FINDING_A_BODY='{"schema_version":"1.0.0","finding_id":"f-tenant-a-001","anomaly_type":"brake_wear_early_stage","hypothesis_class":"BrakeWearHypothesisRule","hypothesis_statement":"Front-left pad wear approaching threshold","candidate_signals":["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear","Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature"],"vehicle_scope":["VIN-AAAA-0001"],"upstream_confidence":0.86}'
record POST "/findings" tenant-a "${FINDING_A_BODY}" "findings/tenant-a-001.json"

# Poll audit chain until 5 events (accepted + generated + validated + deployed + outcome)
sleep 10
CID_A="$(jq -r '."POST·/findings·tenant-a·'"${FINDING_A_BODY//\"/\\\"}"'"' <<<"${INDEX}" | jq -r '.body.correlation_id')"
record GET "/audit/${CID_A}" tenant-a "" "audit/cid-tenant-a-001.json"
record GET "/findings/f-tenant-a-001/outcome" tenant-a "" "outcomes/finding-tenant-a-001.json"

# --- Tenant-b submits brake-wear; symmetric path ---
FINDING_B_BODY='{"schema_version":"1.0.0","finding_id":"f-tenant-b-001","anomaly_type":"brake_wear_early_stage","hypothesis_class":"BrakeWearHypothesisRule","hypothesis_statement":"Rear-right pad wear approaching threshold","candidate_signals":["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear","Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature"],"vehicle_scope":["VIN-BBBB-0001"],"upstream_confidence":0.79}'
record POST "/findings" tenant-b "${FINDING_B_BODY}" "findings/tenant-b-001.json"
sleep 10
CID_B="$(jq -r '."POST·/findings·tenant-b·'"${FINDING_B_BODY//\"/\\\"}"'"' <<<"${INDEX}" | jq -r '.body.correlation_id')"
record GET "/audit/${CID_B}" tenant-b "" "audit/cid-tenant-b-001.json"

# --- Cross-tenant 404: tenant-b reads tenant-a's policy ---
POLICY_ID_A="$(jq -r '."GET·/audit/'"${CID_A}"'·tenant-a·"' <<<"${INDEX}" | jq -r '.body[] | select(.kind=="generated") | .policy_ref.policy_id')"
record GET "/policies/${POLICY_ID_A}" tenant-a "" "policies/pol-tenant-a.json"
record GET "/policies/${POLICY_ID_A}" tenant-b "" "policies/pol-tenant-a-as-b-404.json"

# --- Tenant-config self for each tenant ---
record GET "/tenant-config/self" tenant-a "" "tenant-config/tenant-a-self.json"
record GET "/tenant-config/self" tenant-b "" "tenant-config/tenant-b-self.json"

# --- Operator break-glass against tenant-a's audit chain ---
BREAK_GLASS_BODY='{"tenant_scope":"tenant-a","correlation_id":"'"${CID_A}"'","reason_code":"incident_response"}'
record POST "/audit/break-glass/query" operator-alice "${BREAK_GLASS_BODY}" "break-glass/operator-alice-incident.json"

# --- Erasure example (tenant-a) ---
ERASURE_BODY='{"subject_kind":"vehicle","subject_identifier":"VIN-AAAA-0001","mode":"erased"}'
record POST "/erasure-requests" tenant-a "${ERASURE_BODY}" "erasure/erasure-receipt-tenant-a.json"

# --- Replace the placeholder keys with real space-separated ones in the index ---
INDEX="$(jq 'with_entries(.key |= gsub("·"; " "))' <<<"${INDEX}")"

echo "${INDEX}" | jq . > "${DEMO_RECORDINGS}/index.json"

echo "==> Run PII gate over fixtures"
python "${REPO_ROOT}/demo/scripts/check_fixtures_pii.py" "${DEMO_RECORDINGS}"

echo "==> Recorded $(jq 'length' "${DEMO_RECORDINGS}/index.json") fixtures."

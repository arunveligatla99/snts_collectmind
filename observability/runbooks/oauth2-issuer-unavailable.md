# OAuth2 issuer or JWKS endpoint unreachable

## Symptoms

- 5xx responses from the auth dependency on every inbound request.
- `collectmind_authentication_failure_total{reason="jwks_unreachable"}` increments.

## Dashboard

- Grafana → CollectMind End-to-End → "Authentication-failure rate" (panel 8).

## Mitigation

1. Verify the issuer URL configured at `OAUTH2_ISSUER_URL`.
2. Curl `${OAUTH2_ISSUER_URL}/.well-known/openid-configuration` from inside the orchestration-api container.
3. If the issuer is genuinely down, fail over to the documented stand-by issuer (per `docs/security/threat-model.md`).
4. JWKS cache TTL is 5 minutes; brief blips during issuer maintenance should self-resolve.

## Escalation

Page the security on-call. An issuer outage blocks every authenticated request.

## Related ADRs

- (none.)

## Related FRs

- FR-002, FR-002a — authentication contract.

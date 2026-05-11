# Docker Desktop daemon unreachable (local dev)

## Symptoms

- `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` on local dev.
- Compose commands return non-zero.

## Dashboard

- N/A; this is a local-dev failure mode.

## Mitigation

1. Restart Docker Desktop from the system tray.
2. Wait for the engine to report ready: `docker info`.
3. Re-run `docker compose -f infra/compose/docker-compose.yaml up -d`.
4. Wait for `/ready`: `until curl -fsS http://localhost:8081/ready >/dev/null 2>&1; do sleep 2; done`.

## Escalation

Local-dev only; no on-call paging path.

## Related ADRs

- (none.)

## Related FRs

- SC-008 — 10-minute quickstart on a clean machine.

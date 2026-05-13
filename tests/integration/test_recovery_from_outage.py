"""T109: a one-minute internal-dependency outage drains within five minutes of
recovery and no event is lost.

Asserts US2 Acceptance Scenario 4 / SC-005 / FR-022a. The outage is simulated
by stopping a single internal dependency container via `docker compose`,
publishing a batch of findings during the outage, then restarting the
dependency and waiting for every finding to produce an outcome record within
the five-minute recovery budget.

Choice of dependency: Redis. Stopping the Kafka broker would also exercise the
recovery path but is heavyweight (broker shutdown and rebalance take noticeable
wall time on KRaft single-broker mode). Redis is the hot feature store and the
feedback worker reads from it; an outage there exercises the downstream path
the spec cares about (FR-022a names "any single internal dependency").

Why this can fail in red phase:

- The feedback worker may not retry on Redis ConnectionRefused. T093 wires the
  worker; resilience hardening lands as part of Phase 4 closure (or earlier if
  this test surfaces it first). The red signal here is real.
- The compose Postgres pool may not reconnect cleanly if the orchestration API
  was mid-transaction when Redis was stopped (unlikely on the foundation
  smoke path but in scope for SC-005).

Logical-time note: this test must NOT collapse to seconds via the
`TIME_ACCELERATION_FACTOR`. SC-005's recovery budget is wall-clock; the test
uses a real 60 s outage and a real 5 min drain budget. Findings whose
collection windows would otherwise exceed the test deadline rely on the same
time-acceleration factor that the smoke path uses, so the outcome records
arrive within the same wall budget as the ingest replay.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.conftest import (
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    MOCK_ISSUER_URL,
    ORCHESTRATION_BASE_URL,
    QUERY_BASE_URL,
    require_local_stack,
)

pytestmark = pytest.mark.integration


COMPOSE_FILE = Path(__file__).resolve().parents[2] / "infra" / "compose" / "docker-compose.yaml"
DEPENDENCY_SERVICE = os.environ.get("OUTAGE_DEPENDENCY_SERVICE", "redis")
OUTAGE_SECONDS = 60.0  # SC-005 / FR-022a: "of up to one minute"
DRAIN_BUDGET_SECONDS = 5 * 60.0  # SC-005: "within five minutes of recovery"
FINDING_COUNT = 5
POLL_INTERVAL_SECONDS = 2.0


def _require_docker_compose() -> str:
    """Return the `docker compose` invocation (binary + first arg) or skip."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI not available on PATH; cannot orchestrate outage")
    return docker


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    docker = _require_docker_compose()
    cmd = [docker, "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=120.0)


def _mint() -> str:
    response = httpx.post(
        f"{MOCK_ISSUER_URL}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": DEFAULT_TENANT,
            "client_secret": DEFAULT_CLIENT_SECRET,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _publish(finding_id: str, token: str) -> httpx.Response:
    return httpx.post(
        f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
        json={
            "schema_version": "1.0.0",
            "finding_id": finding_id,
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursion correlation (outage)",
            "candidate_signals": [
                "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
                "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
            ],
            "vehicle_scope": ["VIN-O-1"],
            "upstream_confidence": 0.78,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def _outcome_visible(finding_id: str, token: str) -> bool:
    response = httpx.get(
        f"{QUERY_BASE_URL}/api/v1/findings/{finding_id}/outcome",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    return response.status_code == 200


def test_one_minute_dependency_outage_drains_within_five_minutes_no_loss() -> None:
    require_local_stack()
    _require_docker_compose()
    token = _mint()
    finding_ids = [f"F-outage-{uuid.uuid4().hex[:8]}-{i}" for i in range(FINDING_COUNT)]

    # 1. Stop the dependency. Compose `stop` keeps the container so volumes /
    #    state survive; `start` brings it back without re-creating.
    stop = _compose("stop", DEPENDENCY_SERVICE)
    if stop.returncode != 0:
        pytest.skip(
            f"`docker compose stop {DEPENDENCY_SERVICE}` failed (returncode "
            f"{stop.returncode}); cannot exercise SC-005. stderr: {stop.stderr.strip()}"
        )

    outage_start = time.monotonic()
    accept_responses: list[int] = []
    try:
        # 2. Publish findings while the dependency is down. The orchestration
        #    API SHOULD still accept (return 202) because ingest enqueues to
        #    Kafka and the dependency outage manifests downstream of accept.
        for fid in finding_ids:
            try:
                resp = _publish(fid, token)
                accept_responses.append(resp.status_code)
            except httpx.HTTPError:
                # Network-level refusal is acceptable here; what matters is
                # whether the system replays after recovery. Mark and continue.
                accept_responses.append(0)
            time.sleep(1.0)

        # 3. Hold the outage for the full 60-second window.
        remaining = OUTAGE_SECONDS - (time.monotonic() - outage_start)
        if remaining > 0:
            time.sleep(remaining)
    finally:
        # 4. Restart the dependency.
        start = _compose("start", DEPENDENCY_SERVICE)
        assert start.returncode == 0, f"failed to restart {DEPENDENCY_SERVICE}: stderr: {start.stderr.strip()}"

    recovery_started_at = time.monotonic()

    # 5. Inside the SC-005 drain budget, every finding MUST produce an outcome.
    pending = set(finding_ids)
    while pending and (time.monotonic() - recovery_started_at) < DRAIN_BUDGET_SECONDS:
        for fid in list(pending):
            if _outcome_visible(fid, token):
                pending.discard(fid)
        if pending:
            time.sleep(POLL_INTERVAL_SECONDS)

    elapsed = time.monotonic() - recovery_started_at
    assert not pending, (
        f"SC-005 / FR-022a breach: {len(pending)} finding(s) did not drain within "
        f"{DRAIN_BUDGET_SECONDS}s of recovery (elapsed {elapsed:.1f}s); pending={sorted(pending)}; "
        f"accept_responses={accept_responses}"
    )

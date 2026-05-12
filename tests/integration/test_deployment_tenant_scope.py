"""T272: deployment-client tenant-scope check integration test (Phase 12 US4).

Walks every Acceptance Scenario under US4 in
[spec.md](../../specs/002-multi-tenant-isolation/spec.md):

    AS-1 (matching tenant): ``policy.tenant_id`` matches the target vehicle's owner;
        the deployer's scope-check passes and the outbound deploy proceeds.
    AS-2 (mismatched tenant): policy declares tenant-a but the target vehicle is owned by
        tenant-b; the deployer raises Fatal ``TenantVehicleMismatch``; the outbound
        ``CollectorAIClient.deploy`` is never invoked; an immutable ``kind=deployment_rejected``
        audit row lands carrying the FR-023 minimum field set
        (``policy_ref``, ``target_vehicle_id``, ``policy_declared_tenant_id``,
        ``vehicle_owning_tenant_id``).
    AS-3 (Fatal supersedes Recoverable retry): a downstream collector that would normally
        raise ``Recoverable`` (transient backoff path) is paired with a tenant-mismatched
        policy; the Fatal scope-check fires BEFORE any outbound attempt; the Recoverable
        retry path never runs.

Red phase: Phase 12.b (T276 + T277) has not landed. The imports of
``validate_tenant_scope``, ``TenantVehicleMismatch``, and the deployer-node wrapper
raise ``ImportError`` — the canonical TDD red signal (mirrors the Phase 11 idiom for
``LegacyKeyShapeError`` in ``tests/integration/test_hot_store_legacy_refused.py``). The
ownership pre-seed via ``tenant_vehicles`` runs regardless so the data-side gate is
exercised independently of the application-side gate.

Anchors: FR-021 / FR-022 / FR-023 / SC-012 / ADR-0009 Part 6 / Principle X / Principle XVII
/ Principle IV.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from typing import Any

import pytest

from tests.conftest import require_local_stack

pytestmark = pytest.mark.integration

PG_CONTAINER = "collectmind-postgres"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            PG_CONTAINER,
            "psql",
            "-U",
            "collectmind",
            "-d",
            "collectmind",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _assign_vehicle_to(vehicle_id: str, tenant_id: str) -> None:
    """Seed ``tenant_vehicles`` so the named tenant owns the vehicle.

    Uses ``ON CONFLICT (vehicle_id) DO UPDATE`` so repeated runs are idempotent. The
    underlying ``tenant_vehicles_audit_trigger`` fires a ``kind=vehicle_assignment_change``
    audit row on every transition; that row is unrelated to this test's assertion target
    (``kind=deployment_rejected``).
    """
    result = _psql(
        f"""
        INSERT INTO tenant_vehicles (vehicle_id, tenant_id, assigned_by_subject, reason_code)
        VALUES ('{vehicle_id}', '{tenant_id}', 'test-seed', 'initial_provisioning')
        ON CONFLICT (vehicle_id) DO UPDATE SET
          tenant_id = EXCLUDED.tenant_id,
          assigned_by_subject = EXCLUDED.assigned_by_subject,
          reason_code = EXCLUDED.reason_code;
        """
    )
    if result.returncode != 0:
        pytest.skip(
            f"could not seed tenant_vehicles for test (returncode={result.returncode}, "
            f"stderr={result.stderr.strip()}); skipping. Migration 015 + Phase 9.b T240 must "
            f"have applied."
        )


def _deployment_rejected_payloads_for(correlation_id: str) -> list[dict[str, Any]]:
    """Return the ``originating_finding`` JSON for every ``kind=deployment_rejected`` row
    matching the correlation_id. The audit writer (T209) stores the per-kind minimum field
    set inside ``originating_finding`` per the feature-001 Flag-10 ``_extras`` convention."""
    result = _psql(
        f"""
        \\pset format unaligned
        \\pset tuples_only on
        SELECT originating_finding::text
          FROM audit_events
         WHERE kind='deployment_rejected'
           AND correlation_id='{correlation_id}';
        """
    )
    payloads: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payloads.append(json.loads(stripped))
    return payloads


class _CountingCollector:
    """Test double for ``CollectorAIClient`` that records every ``deploy()`` invocation.

    FR-022 says the Fatal class MUST NOT trigger a retry; this double asserts the stronger
    property that the outbound deploy is not invoked at all on a mismatch (the scope-check
    fires before any outbound call per ADR-0009 Part 6).
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def deploy(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        from collectmind.deployer.client import DeployResponse

        return DeployResponse(deployment_id=str(uuid.uuid4()), status="accepted")


class _AlwaysRecoverableCollector:
    """Test double whose ``deploy`` always raises ``Recoverable`` (transient backoff path).

    Used by AS-3 to prove the Fatal scope-check fires BEFORE the Recoverable retry path
    can run. If it ever runs, ``calls > 0`` and FR-022 is violated.
    """

    def __init__(self) -> None:
        self.calls: int = 0

    def deploy(self, **_: Any) -> Any:
        self.calls += 1
        from collectmind.errors import DependencyUnavailable

        raise DependencyUnavailable("collector-ai")


@pytest.mark.asyncio
async def test_as1_matching_tenant_scope_check_passes() -> None:
    """US4 AS-1: ``policy.tenant_id`` matches the vehicle's owning tenant.

    The deployer's scope-check returns without raising; the outbound call would proceed.
    Test pre-seeds the vehicle as owned by tenant-a and calls ``validate_tenant_scope``
    with a policy declaring tenant-a; no exception expected.
    """
    require_local_stack()
    vid = f"VIN-{uuid.uuid4().hex[:12]}"
    _assign_vehicle_to(vid, TENANT_A)

    try:
        from collectmind.deployer.tenant_scope_check import validate_tenant_scope
    except ImportError:
        pytest.fail(
            "Phase 12.b T276 has not landed: validate_tenant_scope missing from "
            "collectmind.deployer.tenant_scope_check (FR-021 / ADR-0009 Part 6)."
        )

    await validate_tenant_scope(
        policy={
            "policy_id": f"p-{uuid.uuid4().hex[:8]}",
            "version": "1.0.0",
            "tenant_id": TENANT_A,
            "vehicle_scope": [vid],
        },
    )


@pytest.mark.asyncio
async def test_as2_mismatched_tenant_raises_fatal_no_outbound_audited() -> None:
    """US4 AS-2: Fatal TenantVehicleMismatch + no outbound deploy + audit row landed.

    Three properties asserted in one test:
      - The deployer raises ``TenantVehicleMismatch`` (Fatal class per FR-022 + ADR-0009).
      - The ``CollectorAIClient.deploy`` outbound call is NEVER invoked.
      - Exactly one ``kind=deployment_rejected`` row lands in ``audit_events`` for the
        correlation_id, carrying the FR-023 minimum field set
        (``policy_ref`` / ``target_vehicle_id`` / ``policy_declared_tenant_id``
        / ``vehicle_owning_tenant_id``).
    """
    require_local_stack()
    vid = f"VIN-{uuid.uuid4().hex[:12]}"
    cid = f"cid-mismatch-{uuid.uuid4().hex}"
    _assign_vehicle_to(vid, TENANT_B)

    try:
        from collectmind.deployer.node import deploy_with_tenant_scope_check
        from collectmind.deployer.tenant_scope_check import TenantVehicleMismatch
    except ImportError:
        pytest.fail(
            "Phase 12.b T276 + T277 have not landed: deploy_with_tenant_scope_check "
            "and/or TenantVehicleMismatch missing (FR-021 / FR-022 / FR-023 / "
            "ADR-0009 Part 6)."
        )

    collector = _CountingCollector()
    policy = {
        "policy_id": f"p-{uuid.uuid4().hex[:8]}",
        "version": "1.0.0",
        "tenant_id": TENANT_A,
        "vehicle_scope": [vid],
    }

    with pytest.raises(TenantVehicleMismatch):
        await deploy_with_tenant_scope_check(
            policy=policy,
            tenant_id=TENANT_A,
            correlation_id=cid,
            collector=collector,
        )

    # FR-022: no outbound deploy attempted on a Fatal scope-check failure.
    assert collector.calls == [], (
        f"FR-022 violation: outbound deploy invoked despite Fatal class; calls={collector.calls}"
    )

    # FR-023: exactly one kind=deployment_rejected row with the full minimum field set.
    payloads = _deployment_rejected_payloads_for(cid)
    assert len(payloads) == 1, (
        f"FR-023 violation: expected exactly 1 kind=deployment_rejected row for cid={cid}; "
        f"got {len(payloads)}. Rows: {payloads}"
    )
    payload = payloads[0]
    assert payload.get("policy_ref"), f"FR-023: missing policy_ref in {payload}"
    assert payload.get("target_vehicle_id") == vid, f"FR-023: wrong target_vehicle_id in {payload}"
    assert payload.get("policy_declared_tenant_id") == TENANT_A, f"FR-023: wrong policy_declared_tenant_id in {payload}"
    assert payload.get("vehicle_owning_tenant_id") == TENANT_B, f"FR-023: wrong vehicle_owning_tenant_id in {payload}"


@pytest.mark.asyncio
async def test_as3_fatal_supersedes_recoverable_retry() -> None:
    """US4 AS-3: a Recoverable-prone collector paired with a mismatched policy.

    The Fatal scope-check fires BEFORE the outbound call is attempted, so the Recoverable
    retry path never runs. Test passes when ``collector.calls == 0`` after the Fatal
    propagates (the scope-check short-circuited the outbound entirely).
    """
    require_local_stack()
    vid = f"VIN-{uuid.uuid4().hex[:12]}"
    cid = f"cid-supersede-{uuid.uuid4().hex}"
    _assign_vehicle_to(vid, TENANT_B)

    try:
        from collectmind.deployer.node import deploy_with_tenant_scope_check
        from collectmind.deployer.tenant_scope_check import TenantVehicleMismatch
    except ImportError:
        pytest.fail("Phase 12.b T276 + T277 have not landed (FR-022).")

    collector = _AlwaysRecoverableCollector()

    with pytest.raises(TenantVehicleMismatch):
        await deploy_with_tenant_scope_check(
            policy={
                "policy_id": f"p-{uuid.uuid4().hex[:8]}",
                "version": "1.0.0",
                "tenant_id": TENANT_A,
                "vehicle_scope": [vid],
            },
            tenant_id=TENANT_A,
            correlation_id=cid,
            collector=collector,
        )

    # FR-022 strong form: Fatal class supersedes Recoverable retry; collector never invoked.
    assert collector.calls == 0, (
        f"FR-022 violation: Fatal class did not supersede Recoverable retry; collector invoked {collector.calls} times"
    )

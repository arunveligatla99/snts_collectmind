"""Shared helpers for Locust load scenarios (T116-T118).

The three load scenarios (smoke, full, soak) share the same brake-wear finding
payload shape and the same OAuth2 token-minting code. Centralizing both here
keeps drift impossible: a change to the smoke payload propagates to full and
soak without a manual sync.

All three scenarios assume:

- The orchestration API is reachable at ``ORCHESTRATION_BASE_URL`` (default
  http://localhost:8081).
- The mock OAuth2 issuer is reachable at ``MOCK_ISSUER_URL`` (default
  http://localhost:8088).
- The SLM client is selected by ``SLM_PROFILE`` env var on the
  orchestration-api service: ``stub`` for the deterministic fingerprint stub
  (smoke / PR tier), ``vllm`` or ``cpu`` for the real model (full / soak via
  workflow_dispatch and the nightly schedule).

Per Constitution Principle XIV the smoke profile MUST use the deterministic
fingerprint stub (ADR-0004); the full and soak profiles run against the real
SLM and are gated to workflow_dispatch + the nightly schedule.
"""

from __future__ import annotations

import os
import uuid

import httpx

ORCHESTRATION_BASE_URL = os.environ.get("ORCHESTRATION_BASE_URL", "http://localhost:8081")
MOCK_ISSUER_URL = os.environ.get("MOCK_ISSUER_URL", "http://localhost:8088")
DEFAULT_TENANT = os.environ.get("LOAD_TENANT_ID", "feature-001-default")
DEFAULT_CLIENT_SECRET = os.environ.get("LOAD_CLIENT_SECRET", "local-dev-only")


def mint_token() -> str:
    """Mint a JWT against the mock issuer. Used by every Locust user as setup.

    Real production load against the cloud stack uses a long-lived service
    credential supplied via Secrets Manager; the mock issuer mirrors that
    surface so the load-test traffic shape is identical to production traffic
    shape (a Bearer token on every request)."""
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


def finding_payload(finding_id: str | None = None) -> dict:
    """Return a brake-wear diagnostic finding with a unique finding_id.

    The candidate signals are the canonical VSS v6.0 leaf names used across
    every integration test in the suite, so the load profile exercises the
    same validator path as the integration tier."""
    return {
        "schema_version": "1.0.0",
        "finding_id": finding_id or f"F-load-{uuid.uuid4().hex[:12]}",
        "anomaly_type": "brake_wear_early_stage",
        "hypothesis_class": "brake_wear",
        "hypothesis_statement": "rotor temperature excursion correlation",
        "candidate_signals": [
            "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
            "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
        ],
        "vehicle_scope": ["VIN-LOAD-1"],
        "upstream_confidence": 0.78,
    }

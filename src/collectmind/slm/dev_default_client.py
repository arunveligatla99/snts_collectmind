"""DevDefaultPolicyClient.

Returns a deterministic, schema-valid CollectionPolicySpec parameterized by the
session's originating finding. Used only when SLM_PROFILE=dev_default; it does NOT
satisfy ADR-0003's decode-time grammar requirement and MUST NOT be enabled in CI
or production. The CI guard at scripts/check_slm_pinning.py refuses any pipeline
that references this client.

This client exists so that the foundation smoke test and the local quickstart can
exercise the LangGraph end-to-end without bringing the 14 GB SLM container up.
"""

from __future__ import annotations

import os
import re
from typing import Any

from collectmind.slm.client import GenerationRequest, GenerationResponse, RuntimeInfo

_RUNTIME_INFO = RuntimeInfo(
    slm_repo="dev/default",
    slm_revision_sha="0" * 40,
    slm_runtime="stub",
    slm_runtime_version="dev-default",
    slm_quantization="none",
    constrained_decoding_library="none",
)

_DEFAULT_BRAKE_SIGNALS = [
    {"vss_name": "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear", "sample_rate_hz": 1.0, "priority": 5},
    {"vss_name": "Vehicle.Chassis.Axle.Row1.Wheel.Right.Brake.PadWear", "sample_rate_hz": 1.0, "priority": 5},
    {
        "vss_name": "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
        "sample_rate_hz": 2.0,
        "priority": 4,
    },
]


def _extract_finding_from_prompt(prompt: str) -> dict[str, Any]:
    """Pull tenant_id, finding_id, vehicle_scope, etc. out of the rendered prompt."""

    def _match(pat: str) -> str | None:
        m = re.search(pat, prompt)
        return m.group(1) if m else None

    finding_id = _match(r"Finding:\s*([^\s]+)") or "F-default-001"
    tenant_id = _match(r"Tenant:\s*([^\s]+)") or os.environ.get("DEV_DEFAULT_TENANT", "feature-001-default")
    vehicle_scope_raw = _match(r"Vehicle scope:\s*(\[[^\]]*\])")
    vehicle_scope: list[str]
    if vehicle_scope_raw:
        try:
            import json as _json

            vehicle_scope = list(_json.loads(vehicle_scope_raw))
        except Exception:
            vehicle_scope = ["VIN-default-001"]
    else:
        vehicle_scope = ["VIN-default-001"]
    confidence_raw = _match(r"Upstream confidence:\s*([0-9.]+)") or "0.7"
    try:
        confidence = float(confidence_raw)
    except ValueError:
        confidence = 0.7
    session_id = _match(r"Sets `generated_from_session_id` to `\"([^\"]+)\"`") or "session-default-001"
    candidate_raw = _match(r"Candidate signals \(optional hints\):\s*(\[[^\]]*\])")
    candidate_signals: list[str] = []
    if candidate_raw:
        try:
            import json as _json

            candidate_signals = [str(s) for s in _json.loads(candidate_raw)]
        except Exception:
            candidate_signals = []
    return {
        "tenant_id": tenant_id,
        "finding_id": finding_id,
        "vehicle_scope": vehicle_scope,
        "confidence": confidence,
        "session_id": session_id,
        "candidate_signals": candidate_signals,
    }


def _build_policy(prompt: str) -> dict[str, Any]:
    extracted = _extract_finding_from_prompt(prompt)
    candidate = extracted.get("candidate_signals") or []
    if candidate:
        signals = [{"vss_name": s, "sample_rate_hz": 1.0, "priority": 5} for s in candidate]
    else:
        signals = list(_DEFAULT_BRAKE_SIGNALS)
    return {
        "policy_id": f"policy-{extracted['finding_id']}",
        "version": "1.0.0",
        "signals": signals,
        "trigger_conditions": [{"kind": "time_window", "params": {"window_hours": 72}}],
        "collection_window_hours": 72,
        "hypothesis": "rotor temperature excursions correlated with mileage",
        "vehicle_scope": list(extracted["vehicle_scope"]),
        "data_governance_flags": {"pii_consent": False, "has_pii_signal": False},
        "confidence_threshold": max(0.0, min(1.0, extracted["confidence"] - 0.1)),
        "generated_from_session_id": extracted["session_id"],
        "originating_finding": {
            "tenant_id": extracted["tenant_id"],
            "finding_id": extracted["finding_id"],
        },
    }


class DevDefaultPolicyClient:
    """Schema-valid policy generator with no SLM dependency. Dev-only."""

    def warmup(self) -> None:
        return None

    def runtime_info(self) -> RuntimeInfo:
        return _RUNTIME_INFO

    def generate(self, request: dict[str, Any] | GenerationRequest) -> GenerationResponse:
        body = request.to_dict() if isinstance(request, GenerationRequest) else dict(request)
        policy = _build_policy(body["prompt"])
        return GenerationResponse(
            policy=policy,
            runtime_info=_RUNTIME_INFO.to_dict(),
            usage={"input_tokens": 0, "output_tokens": 0, "generation_latency_ms": 0},
        )

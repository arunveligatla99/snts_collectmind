"""T050: Contract test for policy-generator-client.v1.yaml across all three clients.

Per ADR-0003 + ADR-0004 the contract test asserts that `VLLMClient`, `LlamaCppClient`,
and `FingerprintStubClient` produce schema-valid `CollectionPolicySpec` outputs that
parse identically (canonical-JSON byte equality) for a fixed input fingerprint under
deterministic decoding (`temperature=0`, fixed seed).

Per FR-022 / R-020 the per-test wall budget is 60 seconds for the warm path only;
cold start (image pull, weight load, FSM compilation) is bounded separately by the
readiness-probe timeout. This module enforces the warm-path budget via a session-
scoped warm-up fixture.

Until T074-T077 (the three clients) and T103 (the corpus) land, the imports fail and
the tests are reported as collection errors. That is the test's red phase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.conftest import require_slm


CORPUS_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "policy_corpus"
WARM_PATH_BUDGET_SECONDS = 60.0


@pytest.fixture(scope="session")
def warmed_clients():
    """Warm vLLM, llama.cpp, and the deterministic stub once per session.

    Cold start (image pull, FSM compilation, first inference) is excluded from the
    warm-path budget. The budget covers only the post-warmup assertion phase.
    """
    require_slm()
    from collectmind.slm.client import PolicyGeneratorClient
    from collectmind.slm.llamacpp_client import LlamaCppClient
    from collectmind.slm.stub_client import FingerprintStubClient
    from collectmind.slm.vllm_client import VLLMClient

    clients: dict[str, PolicyGeneratorClient] = {
        "vllm": VLLMClient.from_env(),
        "llama_cpp": LlamaCppClient.from_env(),
        "stub": FingerprintStubClient(corpus_root=CORPUS_ROOT),
    }
    for name, client in clients.items():
        # Discardable warm-up generation against a non-corpus fixture fingerprint.
        client.warmup()
    return clients


def _fixed_fingerprint_request() -> dict[str, object]:
    """Return the single fixed `GenerationRequest` exercised by the PR-tier contract test."""
    fixtures = json.loads((CORPUS_ROOT / "_fixed.json").read_text(encoding="utf-8"))
    return fixtures["request"]


def test_three_clients_agree_on_fixed_fingerprint(warmed_clients) -> None:
    """All three PolicyGeneratorClient implementations must produce byte-equal output."""
    request = _fixed_fingerprint_request()
    start = time.perf_counter()
    outputs: dict[str, str] = {}
    for name, client in warmed_clients.items():
        response = client.generate(request)
        outputs[name] = json.dumps(response.policy, sort_keys=True, separators=(",", ":"))
    elapsed = time.perf_counter() - start
    assert elapsed < WARM_PATH_BUDGET_SECONDS, (
        f"warm-path wall time {elapsed:.1f}s exceeded {WARM_PATH_BUDGET_SECONDS}s budget"
    )
    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "PolicyGeneratorClient implementations disagreed on the fixed fingerprint:\n"
        + "\n".join(f"{n}: {outputs[n]}" for n in outputs)
    )


def test_constraint_violation_count_is_zero(warmed_clients) -> None:
    """Schema mask must hold; zero constraint violations on the fixed fingerprint."""
    request = _fixed_fingerprint_request()
    for name, client in warmed_clients.items():
        response = client.generate(request)
        violations = response.runtime_info.get("constraint_violation_count", 0)
        assert violations == 0, f"{name} reported {violations} constraint violations"


def test_runtime_info_carries_pinned_revision_sha(warmed_clients) -> None:
    """Per ADR-0002, every audit-bound RuntimeInfo MUST carry a 40-char weight SHA."""
    request = _fixed_fingerprint_request()
    for name, client in warmed_clients.items():
        response = client.generate(request)
        sha = response.runtime_info.get("slm_revision_sha")
        assert isinstance(sha, str)
        assert len(sha) == 40, f"{name} slm_revision_sha length != 40: {sha!r}"


def test_stub_signals_synthetic_revision_sha() -> None:
    """Per ADR-0004, the stub MUST report `slm_revision_sha = '0' * 40`."""
    from collectmind.slm.stub_client import FingerprintStubClient

    stub = FingerprintStubClient(corpus_root=CORPUS_ROOT)
    response = stub.generate(_fixed_fingerprint_request())
    assert response.runtime_info["slm_runtime"] == "stub"
    assert response.runtime_info["slm_revision_sha"] == "0" * 40

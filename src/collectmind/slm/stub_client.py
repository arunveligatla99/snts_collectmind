"""FingerprintStubClient (T077). Deterministic substitute per ADR-0004.

SHA-256 over canonical-JSON of (prompt_template_version, decoding params, schema,
prompt). On miss -> MissingFingerprint. Audit-record convention: slm_runtime='stub',
slm_revision_sha='0'*40, slm_quantization='none'.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from collectmind.slm.client import GenerationRequest, GenerationResponse, RuntimeInfo


class MissingFingerprint(KeyError):
    def __init__(self, fingerprint: str, corpus_root: Path, request: dict[str, Any]) -> None:
        super().__init__(fingerprint)
        self.fingerprint = fingerprint
        self.corpus_root = corpus_root
        self.request = request


def _normalize(request: dict[str, Any] | GenerationRequest) -> dict[str, Any]:
    if isinstance(request, GenerationRequest):
        return request.to_dict()
    return dict(request)


def compute_fingerprint(request: dict[str, Any] | GenerationRequest) -> str:
    """SHA-256 over canonical-JSON of the semantically meaningful request fields."""
    body = _normalize(request)
    decoding = dict(body.get("decoding") or {})
    payload = {
        "prompt_template_version": body.get("prompt_template_version"),
        "temperature": decoding.get("temperature"),
        "top_p": decoding.get("top_p"),
        "top_k": decoding.get("top_k"),
        "seed": decoding.get("seed"),
        "schema": body.get("schema"),
        "prompt": body.get("prompt"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_RUNTIME_INFO = RuntimeInfo(
    slm_repo="Qwen/Qwen2.5-7B-Instruct",
    slm_revision_sha="0" * 40,
    slm_runtime="stub",
    slm_runtime_version="adr-0004",
    slm_quantization="none",
    constrained_decoding_library="outlines==1.2.13",
    constraint_violation_count=0,
)


class FingerprintStubClient:
    def __init__(self, corpus_root: Path) -> None:
        self._corpus_root = Path(corpus_root)

    def warmup(self) -> None:
        # Stub is in-process; no warm-up needed.
        return None

    def runtime_info(self) -> RuntimeInfo:
        return _RUNTIME_INFO

    def generate(self, request: dict[str, Any] | GenerationRequest) -> GenerationResponse:
        body = _normalize(request)
        fingerprint = compute_fingerprint(body)
        target = self._corpus_root / fingerprint
        if not target.exists():
            raise MissingFingerprint(fingerprint, self._corpus_root, body)
        policy = json.loads((target / "output.json").read_text(encoding="utf-8"))
        usage_path = target / "usage.json"
        usage: dict[str, Any] = (
            json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {}
        )
        return GenerationResponse(
            policy=policy,
            runtime_info=_RUNTIME_INFO.to_dict(),
            usage=usage,
        )

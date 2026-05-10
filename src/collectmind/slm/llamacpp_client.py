"""LlamaCppClient adapter (T076). CPU fallback per ADR-0002."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from collectmind.slm.client import GenerationRequest, GenerationResponse, RuntimeInfo


_REPO = "Qwen/Qwen2.5-7B-Instruct"
_REVISION_SHA = "a09a35458c702b33eeacc393d103063234e8bc28"


class LlamaCppClient:
    def __init__(
        self,
        base_url: str,
        runtime_version: str = "b9090",
        constrained_decoding_library: str = "outlines==1.2.13",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._runtime_version = runtime_version
        self._timeout = timeout
        self._http = httpx.Client(timeout=timeout)
        self._runtime_info = RuntimeInfo(
            slm_repo=_REPO,
            slm_revision_sha=_REVISION_SHA,
            slm_runtime="llama_cpp",
            slm_runtime_version=runtime_version,
            slm_quantization="gguf-q4_k_m",
            constrained_decoding_library=constrained_decoding_library,
        )

    @classmethod
    def from_env(cls) -> "LlamaCppClient":
        return cls(base_url=os.environ.get("SLM_BASE_URL", "http://slm-inference:8000"))

    def warmup(self) -> None:
        self._http.get(f"{self._base_url}/health", timeout=self._timeout)

    def runtime_info(self) -> RuntimeInfo:
        return self._runtime_info

    def generate(self, request: dict[str, Any] | GenerationRequest) -> GenerationResponse:
        body = request.to_dict() if isinstance(request, GenerationRequest) else dict(request)
        decoding = body.get("decoding") or {}
        payload = {
            "messages": [{"role": "user", "content": body["prompt"]}],
            "temperature": decoding.get("temperature", 0.0),
            "top_p": decoding.get("top_p", 1.0),
            "seed": decoding.get("seed", 0),
            "max_tokens": decoding.get("max_tokens", 2048),
            "response_format": {"type": "json_object", "schema": body["schema"]},
        }
        response = self._http.post(f"{self._base_url}/v1/chat/completions", json=payload)
        response.raise_for_status()
        completion = response.json()
        message = completion["choices"][0]["message"]["content"]
        policy = json.loads(message)
        usage = completion.get("usage", {})
        return GenerationResponse(
            policy=policy,
            runtime_info=self._runtime_info.to_dict(),
            usage=dict(usage),
        )

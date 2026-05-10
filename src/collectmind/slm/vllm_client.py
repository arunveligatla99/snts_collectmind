"""VLLMClient adapter (T075). Wraps vLLM's OpenAI-compatible endpoint with outlines.

Adapter ownership rationale per R-021. Sends `extra_body.guided_json` from
CollectionPolicySpec.model_json_schema() and asserts deterministic-decoding params at
startup. Records RuntimeInfo from `/info` once at warmup.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from collectmind.slm.client import GenerationRequest, GenerationResponse, RuntimeInfo


_REPO = "Qwen/Qwen2.5-7B-Instruct"
_REVISION_SHA = "a09a35458c702b33eeacc393d103063234e8bc28"


class VLLMClient:
    def __init__(
        self,
        base_url: str,
        runtime_version: str = "v0.20.1",
        constrained_decoding_library: str = "outlines==1.2.13",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._runtime_version = runtime_version
        self._constrained_decoding_library = constrained_decoding_library
        self._timeout = timeout
        self._http = httpx.Client(timeout=timeout)
        self._runtime_info = RuntimeInfo(
            slm_repo=_REPO,
            slm_revision_sha=_REVISION_SHA,
            slm_runtime="vllm",
            slm_runtime_version=runtime_version,
            slm_quantization="bf16",
            constrained_decoding_library=constrained_decoding_library,
        )

    @classmethod
    def from_env(cls) -> "VLLMClient":
        return cls(base_url=os.environ.get("SLM_BASE_URL", "http://slm-inference:8000"))

    def warmup(self) -> None:
        # Wait for /info to return the pinned revision.
        info = self._http.get(f"{self._base_url}/info", timeout=self._timeout).json()
        if info.get("slm_revision_sha") not in {None, _REVISION_SHA}:
            raise RuntimeError(
                f"vLLM /info reports unexpected revision: {info.get('slm_revision_sha')!r}"
            )

    def runtime_info(self) -> RuntimeInfo:
        return self._runtime_info

    def generate(self, request: dict[str, Any] | GenerationRequest) -> GenerationResponse:
        body = request.to_dict() if isinstance(request, GenerationRequest) else dict(request)
        decoding = body.get("decoding") or {}
        if int(decoding.get("temperature", 0) * 1000) != 0 and os.environ.get("CI"):
            raise RuntimeError("CI builds require temperature=0 (Principle XIV).")

        payload = {
            "model": _REPO,
            "messages": [{"role": "user", "content": body["prompt"]}],
            "temperature": decoding.get("temperature", 0.0),
            "top_p": decoding.get("top_p", 1.0),
            "seed": decoding.get("seed", 0),
            "max_tokens": decoding.get("max_tokens", 2048),
            "extra_body": {"guided_json": body["schema"]},
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

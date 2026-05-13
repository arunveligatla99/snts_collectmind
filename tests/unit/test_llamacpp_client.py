"""Unit tests for LlamaCppClient (T134). httpx-mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from collectmind.slm.llamacpp_client import LlamaCppClient

BASE = "http://slm:8000"


@respx.mock
def test_warmup_hits_health_endpoint() -> None:
    route = respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    client = LlamaCppClient(base_url=BASE)
    client.warmup()
    assert route.called


@respx.mock
def test_generate_returns_parsed_policy() -> None:
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"policy_id": "p-cpu", "version": "1.0.0"}'}}],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        )
    )
    client = LlamaCppClient(base_url=BASE)
    response = client.generate(
        {
            "session_id": "s",
            "prompt_template_version": "v1",
            "prompt": "hello",
            "schema": {"type": "object"},
            "decoding": {},
        }
    )
    assert response.policy["policy_id"] == "p-cpu"
    assert response.runtime_info["slm_runtime"] == "llama_cpp"
    assert response.runtime_info["slm_quantization"] == "gguf-q4_k_m"


def test_runtime_info_uses_cpu_runtime_pin() -> None:
    info = LlamaCppClient(base_url=BASE).runtime_info()
    assert info.slm_runtime == "llama_cpp"
    assert info.slm_runtime_version == "b9090"


def test_from_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLM_BASE_URL", raising=False)
    client = LlamaCppClient.from_env()
    assert client.runtime_info().slm_runtime == "llama_cpp"

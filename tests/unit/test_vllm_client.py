"""Unit tests for VLLMClient (T134 coverage). httpx-mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from collectmind.slm.vllm_client import VLLMClient

BASE = "http://slm:8000"


def _ok_completion(policy_json: str) -> dict:
    return {
        "choices": [{"message": {"content": policy_json}}],
        "usage": {"input_tokens": 12, "output_tokens": 34},
    }


@respx.mock
def test_warmup_succeeds_when_revision_matches() -> None:
    respx.get(f"{BASE}/info").mock(
        return_value=httpx.Response(
            200,
            json={"slm_revision_sha": "a09a35458c702b33eeacc393d103063234e8bc28"},
        )
    )
    client = VLLMClient(base_url=BASE)
    client.warmup()  # must not raise


@respx.mock
def test_warmup_succeeds_when_revision_absent_in_info() -> None:
    respx.get(f"{BASE}/info").mock(return_value=httpx.Response(200, json={}))
    client = VLLMClient(base_url=BASE)
    client.warmup()


@respx.mock
def test_warmup_raises_on_revision_mismatch() -> None:
    respx.get(f"{BASE}/info").mock(return_value=httpx.Response(200, json={"slm_revision_sha": "deadbeef"}))
    client = VLLMClient(base_url=BASE)
    with pytest.raises(RuntimeError, match="unexpected revision"):
        client.warmup()


@respx.mock
def test_generate_returns_parsed_policy() -> None:
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=_ok_completion('{"policy_id": "p-1", "version": "1.0.0", "signals": []}'),
        )
    )
    client = VLLMClient(base_url=BASE)
    response = client.generate(
        {
            "session_id": "s",
            "prompt_template_version": "v1",
            "prompt": "hello",
            "schema": {"type": "object"},
            "decoding": {"temperature": 0.0, "top_p": 1.0, "seed": 0, "max_tokens": 128},
        }
    )
    assert response.policy["policy_id"] == "p-1"
    assert response.runtime_info["slm_repo"] == "Qwen/Qwen2.5-7B-Instruct"
    assert response.usage["input_tokens"] == 12


def test_runtime_info_is_pinned_values() -> None:
    client = VLLMClient(base_url=BASE)
    info = client.runtime_info()
    assert info.slm_repo == "Qwen/Qwen2.5-7B-Instruct"
    assert info.slm_revision_sha == "a09a35458c702b33eeacc393d103063234e8bc28"
    assert info.slm_runtime == "vllm"
    assert info.slm_quantization == "bf16"


def test_from_env_uses_default_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLM_BASE_URL", raising=False)
    client = VLLMClient.from_env()
    assert client.runtime_info().slm_runtime == "vllm"


@respx.mock
def test_ci_guard_rejects_non_zero_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(200, json=_ok_completion("{}")))
    client = VLLMClient(base_url=BASE)
    with pytest.raises(RuntimeError, match="deterministic decoding"):
        client.generate(
            {
                "session_id": "s",
                "prompt_template_version": "v1",
                "prompt": "hello",
                "schema": {},
                "decoding": {"temperature": 0.5, "top_p": 1.0, "seed": 0},
            }
        )


@respx.mock
def test_ci_guard_rejects_non_one_top_p(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(200, json=_ok_completion("{}")))
    client = VLLMClient(base_url=BASE)
    with pytest.raises(RuntimeError, match="deterministic decoding"):
        client.generate(
            {
                "session_id": "s",
                "prompt_template_version": "v1",
                "prompt": "hello",
                "schema": {},
                "decoding": {"temperature": 0.0, "top_p": 0.9, "seed": 0},
            }
        )

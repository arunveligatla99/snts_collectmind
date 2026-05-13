"""Unit tests for FingerprintStubClient (T134)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from collectmind.slm.client import GenerationRequest
from collectmind.slm.stub_client import (
    FingerprintStubClient,
    MissingFingerprint,
    compute_fingerprint,
)


def _request_kwargs(prompt: str = "p") -> dict:
    return {
        "session_id": "s",
        "prompt_template_version": "v1",
        "prompt": prompt,
        "schema": {"type": "object"},
        "decoding": {"temperature": 0.0, "top_p": 1.0, "top_k": -1, "seed": 0},
    }


def test_compute_fingerprint_deterministic() -> None:
    a = compute_fingerprint(_request_kwargs())
    b = compute_fingerprint(_request_kwargs())
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_compute_fingerprint_changes_on_prompt() -> None:
    a = compute_fingerprint(_request_kwargs("p1"))
    b = compute_fingerprint(_request_kwargs("p2"))
    assert a != b


def test_compute_fingerprint_accepts_dataclass() -> None:
    req = GenerationRequest(
        session_id="s",
        prompt_template_version="v1",
        prompt="p",
        schema={"type": "object"},
        decoding={"temperature": 0.0, "top_p": 1.0, "top_k": -1, "seed": 0},
    )
    fp_from_dc = compute_fingerprint(req)
    fp_from_dict = compute_fingerprint(_request_kwargs())
    assert fp_from_dc == fp_from_dict


def test_generate_reads_corpus_entry(tmp_path: Path) -> None:
    req = _request_kwargs("read-me")
    fp = compute_fingerprint(req)
    corpus_dir = tmp_path / fp
    corpus_dir.mkdir()
    policy = {"policy_id": "p-stub", "version": "1.0.0"}
    (corpus_dir / "output.json").write_text(json.dumps(policy), encoding="utf-8")
    (corpus_dir / "usage.json").write_text(json.dumps({"input_tokens": 5, "output_tokens": 10}), encoding="utf-8")

    client = FingerprintStubClient(corpus_root=tmp_path)
    response = client.generate(req)
    assert response.policy["policy_id"] == "p-stub"
    assert response.usage["input_tokens"] == 5


def test_generate_without_usage_json_returns_empty_usage(tmp_path: Path) -> None:
    req = _request_kwargs("no-usage")
    fp = compute_fingerprint(req)
    corpus_dir = tmp_path / fp
    corpus_dir.mkdir()
    (corpus_dir / "output.json").write_text(json.dumps({"policy_id": "p"}), encoding="utf-8")

    response = FingerprintStubClient(corpus_root=tmp_path).generate(req)
    assert response.usage == {}


def test_generate_missing_fingerprint_raises(tmp_path: Path) -> None:
    client = FingerprintStubClient(corpus_root=tmp_path)
    with pytest.raises(MissingFingerprint) as excinfo:
        client.generate(_request_kwargs("no-corpus"))
    assert isinstance(excinfo.value.fingerprint, str)
    assert excinfo.value.corpus_root == tmp_path


def test_warmup_and_runtime_info(tmp_path: Path) -> None:
    client = FingerprintStubClient(corpus_root=tmp_path)
    assert client.warmup() is None
    info = client.runtime_info()
    assert info.slm_runtime == "stub"
    assert info.slm_revision_sha == "0" * 40

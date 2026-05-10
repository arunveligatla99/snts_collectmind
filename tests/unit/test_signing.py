"""T057: Payload signing and verification (per R-018, FR-007).

Covers: signing produces a non-empty signature; verification accepts a valid
signature; verification rejects a tampered payload, a tampered signature, and
an unknown key id.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def signer():
    from collectmind.deployer.signing import LocalKeySigner

    return LocalKeySigner.generate_for_tests(key_id="dev-key-1")


def test_signing_produces_signature(signer) -> None:
    payload = {"policy_id": "policy-1", "version": "1.0.0"}
    signature, key_id = signer.sign(payload)
    assert isinstance(signature, bytes) and len(signature) > 0
    assert key_id == "dev-key-1"


def test_verify_accepts_valid_signature(signer) -> None:
    payload = {"policy_id": "policy-1", "version": "1.0.0"}
    signature, key_id = signer.sign(payload)
    assert signer.verify(payload, signature, key_id) is True


def test_verify_rejects_tampered_payload(signer) -> None:
    payload = {"policy_id": "policy-1", "version": "1.0.0"}
    signature, key_id = signer.sign(payload)
    tampered = {"policy_id": "policy-1", "version": "1.0.1"}
    assert signer.verify(tampered, signature, key_id) is False


def test_verify_rejects_tampered_signature(signer) -> None:
    payload = {"policy_id": "policy-1", "version": "1.0.0"}
    signature, key_id = signer.sign(payload)
    bad = bytearray(signature)
    bad[0] ^= 0xFF
    assert signer.verify(payload, bytes(bad), key_id) is False


def test_verify_rejects_unknown_key_id(signer) -> None:
    payload = {"policy_id": "policy-1", "version": "1.0.0"}
    signature, _ = signer.sign(payload)
    assert signer.verify(payload, signature, "unknown-key") is False


def test_canonical_form_stable_across_dict_orders(signer) -> None:
    """Signature must be over the canonical-JSON form so dict-order does not matter."""
    p1 = {"policy_id": "policy-1", "version": "1.0.0", "extra": [1, 2, 3]}
    p2 = {"extra": [1, 2, 3], "version": "1.0.0", "policy_id": "policy-1"}
    sig1, _ = signer.sign(p1)
    sig2, _ = signer.sign(p2)
    assert sig1 == sig2

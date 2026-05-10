"""Code-signing of policy payloads (T090). Per R-018, FR-007.

Ed25519 by default. Local-key in dev (LocalKeySigner). KMS-backed signers land in
feature 002 production deploy when AWS KMS is wired in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class LocalKeySigner:
    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        public_key: Ed25519PublicKey,
        key_id: str,
    ) -> None:
        self._private = private_key
        self._public = public_key
        self._key_id = key_id

    @classmethod
    def generate_for_tests(cls, key_id: str = "dev-key-1") -> "LocalKeySigner":
        sk = Ed25519PrivateKey.generate()
        return cls(private_key=sk, public_key=sk.public_key(), key_id=key_id)

    @classmethod
    def from_path(cls, path: Path, key_id: str) -> "LocalKeySigner":
        if path.exists():
            sk = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            sk = Ed25519PrivateKey.generate()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                sk.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        if not isinstance(sk, Ed25519PrivateKey):
            raise RuntimeError(f"unexpected private key type at {path}: {type(sk)!r}")
        return cls(private_key=sk, public_key=sk.public_key(), key_id=key_id)

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        signature = self._private.sign(canonical_payload(payload))
        return signature, self._key_id

    def verify(self, payload: dict[str, Any], signature: bytes, key_id: str) -> bool:
        if key_id != self._key_id:
            return False
        try:
            self._public.verify(signature, canonical_payload(payload))
        except InvalidSignature:
            return False
        return True

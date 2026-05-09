"""Mock OAuth2 issuer for local development.

Issues short-lived JWTs under the client-credentials grant. The signing key is generated
fresh on each container start; the public key is exposed at /.well-known/jwks.json.

This is a development convenience only. Not for production.
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from typing import Any

import jwt
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse


CONFIG_PATH = Path("/app/issuer-config.yaml")
TOKEN_TTL_SECONDS = 3600


def _load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _generate_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _public_key_to_jwk(public: rsa.RSAPublicKey, kid: str) -> dict[str, str]:
    numbers = public.public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": base64.urlsafe_b64encode(n).rstrip(b"=").decode("ascii"),
        "e": base64.urlsafe_b64encode(e).rstrip(b"=").decode("ascii"),
    }


config = _load_config()
private_key, public_key = _generate_key_pair()
kid = config["key_id"]
clients_by_id = {c["client_id"]: c for c in config["clients"]}

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

app = FastAPI(title="CollectMind Mock OAuth2 Issuer", version="0.1.0")


@app.get("/.well-known/openid-configuration")
def openid_configuration() -> dict[str, Any]:
    return {
        "issuer": config["issuer"],
        "token_endpoint": f"{config['issuer']}/token",
        "jwks_uri": f"{config['issuer']}/.well-known/jwks.json",
        "grant_types_supported": ["client_credentials"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@app.get("/.well-known/jwks.json")
def jwks() -> dict[str, list[dict[str, str]]]:
    return {"keys": [_public_key_to_jwk(public_key, kid)]}


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str | None = Form(None),
) -> JSONResponse:
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail={"error": "unsupported_grant_type"})

    client = clients_by_id.get(client_id)
    if client is None or client["client_secret"] != client_secret:
        raise HTTPException(status_code=401, detail={"error": "invalid_client"})

    now = int(time.time())
    payload = {
        "iss": config["issuer"],
        "aud": config["audience"],
        "sub": client_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
        "tenant_id": client["tenant_id"],
        "scope": scope or " ".join(client.get("scopes", [])),
    }
    encoded = jwt.encode(
        payload,
        private_pem,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )
    return JSONResponse(
        {
            "access_token": encoded,
            "token_type": "Bearer",
            "expires_in": TOKEN_TTL_SECONDS,
            "scope": payload["scope"],
        }
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

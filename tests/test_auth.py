from __future__ import annotations

import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.auth import TrimbleTokenVerifier


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    async def get(self, _: str) -> _FakeResponse:
        return _FakeResponse(self._payload)

    async def aclose(self) -> None:
        return None


def _build_rsa_material(kid: str) -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk_json = jwt.algorithms.RSAAlgorithm.to_jwk(public_key)
    jwk_dict = json.loads(jwk_json)
    jwk_dict["kid"] = kid
    return private_key, jwk_dict


@pytest.mark.anyio
async def test_trimble_token_verifier_accepts_valid_token() -> None:
    issuer = "https://stage.id.trimblecloud.com"
    private_key, jwk = _build_rsa_material("kid-valid")

    verifier = TrimbleTokenVerifier(
        issuer=issuer,
        jwks_url=f"{issuer}/.well-known/jwks.json",
        required_scopes=["agents"],
        audience="vista-api",
    )
    verifier._client = _FakeAsyncClient({"keys": [jwk]})  # type: ignore[assignment]

    token = jwt.encode(
        {
            "iss": issuer,
            "sub": "user-123",
            "aud": ["vista-api"],
            "scope": "kb agents",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "kid-valid"},
    )

    result = await verifier.verify_token(token)
    assert result is not None
    assert result.client_id == "user-123"
    assert "agents" in result.scopes


@pytest.mark.anyio
async def test_trimble_token_verifier_rejects_missing_scope() -> None:
    issuer = "https://stage.id.trimblecloud.com"
    private_key, jwk = _build_rsa_material("kid-scope")

    verifier = TrimbleTokenVerifier(
        issuer=issuer,
        jwks_url=f"{issuer}/.well-known/jwks.json",
        required_scopes=["agents"],
    )
    verifier._client = _FakeAsyncClient({"keys": [jwk]})  # type: ignore[assignment]

    token = jwt.encode(
        {
            "iss": issuer,
            "sub": "user-123",
            "scope": "kb models",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "kid-scope"},
    )

    result = await verifier.verify_token(token)
    assert result is None

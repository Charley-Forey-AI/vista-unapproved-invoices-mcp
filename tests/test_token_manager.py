from __future__ import annotations

import time
from typing import Any

import jwt
import pytest

from server.token_manager import TidTokenManager, _extract_exp


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = Exception("request")
            raise Exception(request)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls = 0
        self.last_bodies: list[dict[str, Any]] = []

    async def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.last_bodies.append(dict(kwargs.get("data", {})))
        return _FakeResponse(200, self.payload)

    async def aclose(self) -> None:
        return None


def _token_with_exp(offset_seconds: int) -> str:
    return jwt.encode({"exp": int(time.time()) + offset_seconds}, "secret", algorithm="HS256")


def test_extract_exp_from_jwt() -> None:
    token = _token_with_exp(300)
    exp = _extract_exp(token)
    assert exp is not None
    assert exp > time.time()


@pytest.mark.anyio
async def test_tid_token_manager_refreshes_when_expired() -> None:
    refreshed_token = _token_with_exp(3600)
    manager = TidTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        access_token=_token_with_exp(-60),
        scope="openid vista_agent",
    )
    fake_client = _FakeAsyncClient({"access_token": refreshed_token, "refresh_token": "new-refresh-token"})
    manager._client = fake_client  # type: ignore[assignment]

    token = await manager.get_access_token()
    assert token == refreshed_token
    assert fake_client.calls == 1

    await manager.close()


class _SequenceFakeAsyncClient:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = responses
        self.calls = 0
        self.last_bodies: list[dict[str, Any]] = []

    async def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.last_bodies.append(dict(kwargs.get("data", {})))
        index = self.calls - 1
        return self.responses[index]

    async def aclose(self) -> None:
        return None


@pytest.mark.anyio
async def test_tid_token_manager_uses_existing_token_when_valid() -> None:
    current_token = _token_with_exp(3600)
    manager = TidTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        access_token=current_token,
        scope="openid vista_agent",
    )
    fake_client = _FakeAsyncClient({"access_token": _token_with_exp(3600)})
    manager._client = fake_client  # type: ignore[assignment]

    token = await manager.get_access_token()
    assert token == current_token
    assert fake_client.calls == 0

    await manager.close()


@pytest.mark.anyio
async def test_tid_token_manager_retries_without_scope_on_invalid_scope_error() -> None:
    refreshed_token = _token_with_exp(3600)
    manager = TidTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        access_token=_token_with_exp(-60),
        scope="openid vista_agent",
    )
    fake_client = _SequenceFakeAsyncClient(
        [
            _FakeResponse(
                400,
                {
                    "error": "invalid_request",
                    "error_description": "Scope invalid for this refresh token",
                },
            ),
            _FakeResponse(200, {"access_token": refreshed_token, "refresh_token": "new-refresh-token"}),
        ]
    )
    manager._client = fake_client  # type: ignore[assignment]

    token = await manager.get_access_token()
    assert token == refreshed_token
    assert fake_client.calls == 2
    assert fake_client.last_bodies[0].get("scope") == "openid vista_agent"
    assert "scope" not in fake_client.last_bodies[1]

    await manager.close()

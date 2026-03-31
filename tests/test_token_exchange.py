from __future__ import annotations

import asyncio
import time

import httpx
import jwt
import pytest

from server.token_exchange import TokenExchangeProvider


@pytest.mark.anyio
async def test_token_exchange_provider_posts_expected_body() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        audience="vista-api",
        scope="vista_agent",
    )

    seen: dict[str, object] = {}

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen["url"] = args[0]
        seen["data"] = kwargs.get("data")
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        return httpx.Response(200, json={"access_token": "vista-token"}, request=request)

    provider._client.post = _post  # type: ignore[method-assign]
    token = await provider.exchange("actor-token")
    assert token == "vista-token"
    assert seen["url"] == "https://stage.id.trimblecloud.com/oauth/token"
    assert seen["data"] == {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": "client-id",
        "subject_token": "actor-token",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "audience": "vista-api",
        "scope": "vista_agent",
    }

    await provider.close()


@pytest.mark.anyio
async def test_token_exchange_provider_raises_on_http_error() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
    )

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        return httpx.Response(
            400,
            json={"error": "invalid_scope", "error_description": "scope invalid"},
            request=request,
        )

    provider._client.post = _post  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="OAuth error: invalid_scope - scope invalid"):
        await provider.exchange("actor-token")
    await provider.close()


@pytest.mark.anyio
async def test_token_exchange_provider_retries_without_token_type_fields() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        scope="vista_agent openid",
    )

    seen_bodies: list[dict[str, str]] = []

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        body = dict(kwargs.get("data", {}))
        seen_bodies.append(body)
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        if len(seen_bodies) == 1:
            return httpx.Response(
                400,
                json={
                    "error": "invalid_request",
                    "error_description": "subject_token type 'urn:ietf:params:oauth:token-type:jwt' not supported.",
                },
                request=request,
            )
        return httpx.Response(200, json={"access_token": "fallback-token"}, request=request)

    provider._client.post = _post  # type: ignore[method-assign]
    token = await provider.exchange("actor-token")
    assert token == "fallback-token"
    assert "subject_token_type" in seen_bodies[0]
    assert "requested_token_type" in seen_bodies[0]
    assert "subject_token_type" not in seen_bodies[1]
    assert "requested_token_type" not in seen_bodies[1]
    await provider.close()


@pytest.mark.anyio
async def test_token_exchange_provider_retries_with_jwt_requested_token_type() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        scope="vista_agent openid",
    )

    seen_bodies: list[dict[str, str]] = []

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        body = dict(kwargs.get("data", {}))
        seen_bodies.append(body)
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        if len(seen_bodies) == 1:
            return httpx.Response(
                400,
                json={
                    "error": "invalid_request",
                    "error_description": (
                        'request_token_type "urn:ietf:params:oauth:token-type:access_token" '
                        "not supported. Only urn:ietf:params:oauth:token-type:jwt is supported."
                    ),
                },
                request=request,
            )
        return httpx.Response(200, json={"access_token": "jwt-requested-token"}, request=request)

    provider._client.post = _post  # type: ignore[method-assign]
    token = await provider.exchange("actor-token")
    assert token == "jwt-requested-token"
    assert seen_bodies[0]["requested_token_type"] == "urn:ietf:params:oauth:token-type:access_token"
    assert seen_bodies[1]["requested_token_type"] == "urn:ietf:params:oauth:token-type:jwt"
    await provider.close()


@pytest.mark.anyio
async def test_token_exchange_provider_uses_cache_for_repeated_subject_token() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        cache_ttl_seconds=600,
    )

    call_count = 0

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        return httpx.Response(200, json={"access_token": "cached-token", "expires_in": 300}, request=request)

    provider._client.post = _post  # type: ignore[method-assign]
    first = await provider.exchange("actor-token")
    second = await provider.exchange("actor-token")

    assert first == "cached-token"
    assert second == "cached-token"
    assert call_count == 1
    await provider.close()


@pytest.mark.anyio
async def test_token_exchange_provider_refreshes_after_expiry() -> None:
    provider = TokenExchangeProvider(
        token_url="https://stage.id.trimblecloud.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        cache_ttl_seconds=600,
        refresh_skew_seconds=0,
    )

    call_count = 0

    async def _post(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        request = httpx.Request("POST", "https://stage.id.trimblecloud.com/oauth/token")
        exp = int(time.time()) + 1
        token = jwt.encode({"exp": exp}, "super-secret-key-with-32-plus-bytes", algorithm="HS256")
        return httpx.Response(200, json={"access_token": token}, request=request)

    provider._client.post = _post  # type: ignore[method-assign]
    await provider.exchange("actor-token")
    await asyncio.sleep(1.2)
    await provider.exchange("actor-token")
    assert call_count >= 2
    await provider.close()

from __future__ import annotations

import httpx
import pytest

from server.api import VistaApiClient
from server.config import VistaSettings


def test_validate_startup_requires_static_auth() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="static",
    )
    with pytest.raises(ValueError, match="VISTA_AUTH_MODE=static"):
        settings.validate_startup()


def test_validate_startup_requires_delegated_settings() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
    )
    with pytest.raises(ValueError, match="Missing delegated auth settings"):
        settings.validate_startup()


def test_validate_startup_accepts_delegated_streamable_http() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        auth_jwks_url="https://stage.id.trimblecloud.com/.well-known/jwks.json",
        auth_resource_server_url="https://mcp.example.com/mcp",
    )
    settings.validate_startup()


def test_validate_startup_requires_server_managed_settings() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="server-managed",
        mcp_transport="streamable-http",
    )
    with pytest.raises(ValueError, match="Missing server-managed auth settings"):
        settings.validate_startup()


def test_validate_startup_accepts_server_managed_settings() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="server-managed",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
    )
    settings.validate_startup()


def test_normalized_scope_removes_quotes_and_extra_spaces() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        scope=' "openid   vista_agent" ',
    )
    assert settings.normalized_scope() == "openid vista_agent"


@pytest.mark.anyio
async def test_api_client_prefers_request_bearer_over_static_token() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    token = client.set_request_bearer_token("delegated-token")
    try:
        headers, _ = await client._build_headers(require_auth=True)  # noqa: SLF001
    finally:
        client.reset_request_bearer_token(token)
        await client.close()

    assert headers["Authorization"] == "Bearer delegated-token"


@pytest.mark.anyio
async def test_api_client_skips_auth_header_when_auth_not_required() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    headers, auth_source = await client._build_headers(require_auth=False)  # noqa: SLF001
    assert "Authorization" not in headers
    assert auth_source is None

    await client.close()


@pytest.mark.anyio
async def test_api_client_sanitizes_auth_failure_message() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request("GET", "https://api.example.com/api/v1/123")
        return httpx.Response(401, text="contains-secret-token", request=request)

    client._client.request = _request  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="authentication failed"):
        await client._request("GET", "/api/v1/123")

    with pytest.raises(RuntimeError) as exc_info:
        await client._request("GET", "/api/v1/123")
    assert "contains-secret-token" not in str(exc_info.value)

    await client.close()


@pytest.mark.anyio
async def test_api_client_retries_once_after_server_managed_refresh() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="server-managed",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
    )

    class _FakeTokenManager:
        def __init__(self) -> None:
            self.force_refresh_count = 0
            self.current_token = "old-token"

        async def get_access_token(self, *, force_refresh: bool = False) -> str:
            if force_refresh:
                self.force_refresh_count += 1
                self.current_token = "new-token"
            return self.current_token

    token_manager = _FakeTokenManager()
    client = VistaApiClient(settings, token_manager=token_manager)  # type: ignore[arg-type]

    calls: list[str] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        auth_header = kwargs["headers"]["Authorization"]
        calls.append(auth_header)
        request = httpx.Request("GET", "https://api.example.com/api/v1/123")
        if len(calls) == 1:
            return httpx.Response(401, json={"error": "expired"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client._request("GET", "/api/v1/123")
    assert payload == {"ok": True}
    assert calls == ["Bearer old-token", "Bearer new-token"]
    assert token_manager.force_refresh_count == 1

    await client.close()

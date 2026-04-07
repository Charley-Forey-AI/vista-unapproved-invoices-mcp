from __future__ import annotations

import httpx
import pytest

from server.api import VistaApiClient
from server.config import VistaSettings
from server.endpoint_registry import ENDPOINTS_BY_TOOL


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


def test_required_scopes_and_audience_are_normalized() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_required_scopes=' "vista_agent, kb" ',
        auth_audience="aud-one, aud-two",
    )
    assert settings.required_scopes() == ["vista_agent", "kb"]
    assert settings.normalized_auth_audience() == ["aud-one", "aud-two"]


def test_write_domain_normalization_and_batch_size_override() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        write_enabled_domains="ap, po jc",
        max_bulk_items=50,
        max_batch_size=10,
    )
    assert settings.normalized_write_domains() == {"ap", "po", "jc"}
    assert settings.effective_max_batch_size() == 10


def test_validate_startup_rejects_required_scopes_not_in_scope() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        auth_jwks_url="https://stage.id.trimblecloud.com/.well-known/jwks.json",
        auth_resource_server_url="https://mcp.example.com/mcp",
        auth_required_scopes="vista_agent",
        scope="openid",
    )
    with pytest.raises(ValueError, match="Delegated scope alignment failed"):
        settings.validate_startup()


def test_validate_startup_requires_token_exchange_settings() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        auth_strategy="token_exchange",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        auth_jwks_url="https://stage.id.trimblecloud.com/.well-known/jwks.json",
        auth_resource_server_url="https://mcp.example.com/mcp",
    )
    with pytest.raises(ValueError, match="Missing token exchange settings"):
        settings.validate_startup()


def test_validate_startup_requires_redis_url_for_redis_analysis_cache() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="static",
        bearer_token="token",
        analysis_cache_backend="redis",
        redis_url=None,
    )
    with pytest.raises(ValueError, match="VISTA_REDIS_URL"):
        settings.validate_startup()


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
async def test_api_client_delegated_mode_requires_actor_token() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)
    with pytest.raises(RuntimeError, match="Delegated actor token missing"):
        await client._build_headers(require_auth=True)  # noqa: SLF001
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
    message = str(exc_info.value)
    assert "contains-secret-token" not in message
    assert "auth_source=static-bearer" in message

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


@pytest.mark.anyio
async def test_api_client_403_message_includes_auth_source() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request("POST", "https://api.example.com/api/v1/enterprise")
        return httpx.Response(403, json={"error": "forbidden"}, request=request)

    client._client.request = _request  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="auth_source=static-bearer"):
        await client._request("POST", "/api/v1/enterprise")
    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_builds_list_params_and_body() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    request_log: list[dict[str, object]] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        request_log.append(
            {
                "method": args[0],
                "path": args[1],
                "params": kwargs.get("params"),
                "body": kwargs.get("json"),
            }
        )
        request = httpx.Request("POST", "https://api.example.com/api/v1/100/vendor")
        return httpx.Response(200, json={"items": [], "pageSize": 50, "currentPage": 1}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["list_vendors"],
        path_params={"enterpriseId": 100},
        query_body={"filters": []},
        order_by="name",
        order_by_asc=True,
        limit=50,
        page=1,
        includes="alternateAddresses",
    )

    assert payload["pageSize"] == 50
    assert request_log[0]["method"] == "POST"
    assert request_log[0]["path"] == "/api/v1/100/vendor"
    assert request_log[0]["params"] == {
        "orderBy": "name",
        "orderByAsc": True,
        "limit": 50,
        "page": 1,
        "includes": "alternateAddresses",
    }
    assert request_log[0]["body"] == {"filters": []}

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_uses_health_client_without_auth() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
        health_base_url="https://health.example.com",
    )
    client = VistaApiClient(settings)

    calls: list[str] = []

    async def _health_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs.get("headers", {}).get("Authorization", "missing"))
        request = httpx.Request("GET", "https://health.example.com/health/ready")
        return httpx.Response(200, json={"Status": "Healthy"}, request=request)

    client._health_client.request = _health_request  # type: ignore[method-assign]

    payload = await client.call_endpoint(ENDPOINTS_BY_TOOL["health_ready"])
    assert payload["Status"] == "Healthy"
    assert calls == ["missing"]

    await client.close()


@pytest.mark.anyio
async def test_health_base_url_strips_api_v1_suffix() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com/api/v1",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)
    assert client._health_base_url == "https://api.example.com"  # noqa: SLF001
    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_builds_get_path_with_id_and_includes() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    path_calls: list[tuple[str, dict[str, object] | None]] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        path_calls.append((args[1], kwargs.get("params")))
        request = httpx.Request("GET", "https://api.example.com/api/v1/33/company/abc")
        return httpx.Response(200, json={"item": {"id": "abc"}}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["get_company"],
        path_params={"enterpriseId": 33, "id": "abc"},
        includes="details",
    )

    assert payload["item"]["id"] == "abc"
    assert path_calls == [("/api/v1/33/company/abc", {"includes": "details"})]

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_builds_bulk_body_for_unapproved_invoices() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    bodies: list[dict[str, object] | None] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        bodies.append(kwargs.get("json"))
        request = httpx.Request("POST", "https://api.example.com/api/v1/10/ap/unapprovedinvoice")
        return httpx.Response(200, json={"items": []}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["create_unapproved_invoices"],
        path_params={"enterpriseId": 10},
        bulk_items=[{"invoiceNumber": "INV-1"}],
    )

    assert payload["items"] == []
    assert bodies == [{"items": [{"invoiceNumber": "INV-1"}]}]

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_retries_transient_503_for_get() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    calls = 0

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://api.example.com/api/v1/33/company/abc")
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"}, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"item": {"id": "abc"}}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["get_company"],
        path_params={"enterpriseId": 33, "id": "abc"},
    )

    assert payload["item"]["id"] == "abc"
    assert calls == 2

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_retries_transient_502_for_get() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
        transient_retry_attempts=1,
        transient_retry_base_seconds=0.0,
        transient_retry_max_seconds=0.0,
        transient_retry_jitter_seconds=0.0,
    )
    client = VistaApiClient(settings)

    calls = 0

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://api.example.com/api/v1/33/company/abc")
        if calls == 1:
            return httpx.Response(502, json={"error": "bad gateway"}, request=request)
        return httpx.Response(200, json={"item": {"id": "abc"}}, request=request)

    client._client.request = _request  # type: ignore[method-assign]
    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["get_company"],
        path_params={"enterpriseId": 33, "id": "abc"},
    )
    assert payload["item"]["id"] == "abc"
    assert calls == 2

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_retries_network_error_for_get() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
        transient_retry_attempts=1,
        transient_retry_base_seconds=0.0,
        transient_retry_max_seconds=0.0,
    )
    client = VistaApiClient(settings)

    calls = 0

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://api.example.com/api/v1/33/company/abc")
        if calls == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"item": {"id": "abc"}}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["get_company"],
        path_params={"enterpriseId": 33, "id": "abc"},
    )

    assert payload["item"]["id"] == "abc"
    assert calls == 2

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_falls_back_to_get_without_includes_on_400() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    calls: list[dict[str, object | None]] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"path": args[1], "params": kwargs.get("params")})
        request = httpx.Request("GET", "https://api.example.com/api/v1/33/company/abc")
        if len(calls) == 1:
            return httpx.Response(400, json={"error": "invalid includes"}, request=request)
        return httpx.Response(200, json={"item": {"id": "abc"}}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["get_company"],
        path_params={"enterpriseId": 33, "id": "abc"},
        includes="details",
    )

    assert payload["item"]["id"] == "abc"
    assert calls == [
        {"path": "/api/v1/33/company/abc", "params": {"includes": "details"}},
        {"path": "/api/v1/33/company/abc", "params": None},
    ]

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_falls_back_to_list_with_smaller_limit_on_400() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    calls: list[dict[str, object | None]] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"path": args[1], "params": kwargs.get("params")})
        request = httpx.Request("POST", "https://api.example.com/api/v1/33/vendor")
        if len(calls) == 1:
            return httpx.Response(400, json={"error": "limit too high"}, request=request)
        return httpx.Response(200, json={"items": [], "pageSize": 100, "currentPage": 1}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(
        ENDPOINTS_BY_TOOL["list_vendors"],
        path_params={"enterpriseId": 33},
        query_body={"filters": []},
        limit=500,
    )

    assert payload["pageSize"] == 100
    assert calls == [
        {"path": "/api/v1/33/vendor", "params": {"limit": 500}},
        {"path": "/api/v1/33/vendor", "params": {"limit": 100}},
    ]

    await client.close()


@pytest.mark.anyio
async def test_call_endpoint_recovers_from_closed_health_client_runtime_error() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
        transient_retry_attempts=1,
        transient_retry_base_seconds=0.0,
        transient_retry_max_seconds=0.0,
    )
    client = VistaApiClient(settings)

    calls = 0

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        request = httpx.Request("GET", "https://api.example.com/health/ready")
        return httpx.Response(200, json={"Status": "Healthy"}, request=request)

    client._health_client.request = _request  # type: ignore[method-assign]

    payload = await client.call_endpoint(ENDPOINTS_BY_TOOL["health_ready"])
    assert payload["Status"] == "Healthy"
    assert calls == 2

    await client.close()


@pytest.mark.anyio
async def test_collect_list_pages_fetches_until_short_page() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    pages = [
        httpx.Response(
            200,
            json={"items": [{"id": "1"}, {"id": "2"}], "pageSize": 2, "currentPage": 1},
            request=httpx.Request("POST", "https://api.example.com/api/v1/33/vendor"),
        ),
        httpx.Response(
            200,
            json={"items": [{"id": "3"}], "pageSize": 2, "currentPage": 2},
            request=httpx.Request("POST", "https://api.example.com/api/v1/33/vendor"),
        ),
    ]
    call_count = 0

    seen_params: list[dict[str, object] | None] = []

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        seen_params.append(kwargs.get("params"))
        response = pages[call_count]
        call_count += 1
        return response

    client._client.request = _request  # type: ignore[method-assign]

    result = await client.collect_list_pages(
        ENDPOINTS_BY_TOOL["list_vendors"],
        path_params={"enterpriseId": 33},
        query_body={"filters": []},
        order_by="lastUpdateDateUtc",
        order_by_asc=False,
        page_size=2,
        max_pages=5,
    )

    assert result["pagesFetched"] == 2
    assert result["partial"] is False
    assert len(result["items"]) == 3
    assert seen_params[0] == {"orderBy": "lastUpdateDateUtc", "orderByAsc": False, "limit": 2, "page": 1}

    await client.close()


@pytest.mark.anyio
async def test_collect_list_pages_returns_partial_on_runtime_error() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="static-token",
    )
    client = VistaApiClient(settings)

    calls = 0

    async def _request(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request("POST", "https://api.example.com/api/v1/33/vendor")
            return httpx.Response(200, json={"items": [{"id": "1"}]}, request=request)
        request = httpx.Request("POST", "https://api.example.com/api/v1/33/vendor")
        return httpx.Response(503, json={"error": "busy"}, request=request)

    client._client.request = _request  # type: ignore[method-assign]

    result = await client.collect_list_pages(
        ENDPOINTS_BY_TOOL["list_vendors"],
        path_params={"enterpriseId": 33},
        query_body={"filters": []},
        page_size=1,
        max_pages=3,
    )

    assert result["pagesFetched"] == 1
    assert result["partial"] is True
    assert len(result["errors"]) == 1
    assert len(result["items"]) == 1

    await client.close()

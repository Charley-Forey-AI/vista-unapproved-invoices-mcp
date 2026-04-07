"""Vista MCP server entrypoint."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from .api import VistaApiClient
from .auth import TrimbleTokenVerifier
from .config import VistaSettings
from .prompts import register_prompts
from .resources import register_resources
from .tool_factory import close_tool_factory_resources, register_endpoint_tools
from .token_exchange import TokenExchangeProvider
from .token_manager import TidTokenManager

logger = logging.getLogger(__name__)


def create_server(settings: VistaSettings) -> FastMCP:
    """Create and configure the Vista MCP server instance."""

    token_manager: TidTokenManager | None = None
    token_exchange_provider: TokenExchangeProvider | None = None
    if settings.auth_mode == "server-managed":
        assert settings.client_id is not None
        assert settings.client_secret is not None
        assert settings.refresh_token is not None
        token_url = settings.token_url
        if not token_url:
            assert settings.auth_issuer is not None
            token_url = f"{settings.auth_issuer.rstrip('/')}/oauth/token"
        token_manager = TidTokenManager(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            refresh_token=settings.refresh_token,
            token_url=token_url,
            access_token=settings.access_token,
            scope=settings.normalized_scope(),
            timeout_seconds=settings.token_http_timeout_seconds,
            retry_attempts=settings.transient_retry_attempts,
            retry_base_seconds=settings.transient_retry_base_seconds,
            retry_max_seconds=settings.transient_retry_max_seconds,
            retry_jitter_seconds=settings.transient_retry_jitter_seconds,
            retry_status_codes=settings.retry_status_codes(),
        )

    if settings.auth_strategy == "token_exchange":
        assert settings.client_id is not None
        assert settings.client_secret is not None
        exchange_token_url = settings.token_exchange_token_url or settings.token_url
        if not exchange_token_url:
            assert settings.auth_issuer is not None
            exchange_token_url = f"{settings.auth_issuer.rstrip('/')}/oauth/token"
        token_exchange_provider = TokenExchangeProvider(
            token_url=exchange_token_url,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            audience=settings.normalized_token_exchange_audience(),
            scope=settings.normalized_token_exchange_scope() or settings.normalized_scope(),
            subject_token_type=settings.token_exchange_subject_token_type,
            requested_token_type=settings.token_exchange_requested_token_type,
            timeout_seconds=settings.token_http_timeout_seconds,
            retry_attempts=settings.transient_retry_attempts,
            retry_base_seconds=settings.transient_retry_base_seconds,
            retry_max_seconds=settings.transient_retry_max_seconds,
            retry_jitter_seconds=settings.transient_retry_jitter_seconds,
            retry_status_codes=settings.retry_status_codes(),
            cache_ttl_seconds=settings.token_exchange_cache_ttl_seconds,
            refresh_skew_seconds=settings.token_exchange_refresh_skew_seconds,
        )

    api = VistaApiClient(
        settings,
        token_manager=token_manager,
        token_exchange_provider=token_exchange_provider,
    )
    token_verifier: TrimbleTokenVerifier | None = None
    auth_settings: AuthSettings | None = None
    delegated_mode = settings.auth_mode in {"delegated", "hybrid"}

    if delegated_mode:
        assert settings.auth_issuer is not None
        assert settings.auth_jwks_url is not None
        assert settings.auth_resource_server_url is not None
        required_scopes = settings.required_scopes()
        auth_settings = AuthSettings(
            issuer_url=settings.auth_issuer,
            required_scopes=required_scopes,
            resource_server_url=settings.auth_resource_server_url,
        )
        token_verifier = TrimbleTokenVerifier(
            issuer=settings.auth_issuer,
            jwks_url=settings.auth_jwks_url,
            audience=settings.normalized_auth_audience(),
            required_scopes=required_scopes,
            jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
            jwt_leeway_seconds=settings.auth_jwt_leeway_seconds,
            timeout_seconds=settings.auth_jwks_timeout_seconds,
        )

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        try:
            yield
        finally:
            await close_tool_factory_resources()
            await api.close()
            if token_manager is not None:
                await token_manager.close()
            if token_verifier is not None:
                await token_verifier.close()

    mcp = FastMCP(
        name="vista",
        instructions=(
            "Tools for Enterprise, Company, Contract, Customer, Project, Equipment, PO, AP, Vendor, and Health Vista APIs. "
            "Use list/query tools to discover IDs and pagination state, then pass IDs to get/action tools. "
            "For complex tasks, read vista://guides/dependencies, vista://guides/workflows, "
            "vista://guides/response-interpretation, vista://guides/filters, and "
            "vista://guides/errors-and-edge-cases."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_streamable_http_path,
        json_response=settings.mcp_json_response,
        stateless_http=settings.mcp_stateless_http,
        auth=auth_settings,
        token_verifier=token_verifier,
        lifespan=lifespan,
    )

    # Compatibility route: some MCP clients attempt path-based OAuth metadata
    # discovery on the MCP host (/.well-known/oauth-authorization-server/mcp).
    # In delegated/hybrid mode we are a resource server, so return metadata that
    # points clients to the external Trimble authorization server.
    if delegated_mode:
        assert settings.auth_issuer is not None
        issuer = settings.auth_issuer.rstrip("/")
        metadata_payload: dict[str, Any] = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "jwks_uri": settings.auth_jwks_url,
            "scopes_supported": settings.required_scopes() or None,
            "response_types_supported": ["code", "token", "id_token"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "client_credentials",
                "urn:ietf:params:oauth:grant-type:token-exchange",
            ],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        }
        metadata_payload = {k: v for k, v in metadata_payload.items() if v is not None}

        async def oauth_authorization_server_metadata(_: Request) -> Response:
            return Response(
                content=json.dumps(metadata_payload),
                media_type="application/json",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                },
            )

        @mcp.custom_route("/.well-known/oauth-authorization-server/mcp", methods=["GET", "OPTIONS"])
        async def oauth_authorization_server_metadata_path(request: Request) -> Response:
            if request.method == "OPTIONS":
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    },
                )
            return await oauth_authorization_server_metadata(request)

        @mcp.custom_route("/.well-known/openid-configuration/mcp", methods=["GET", "OPTIONS"])
        async def oidc_metadata_path(request: Request) -> Response:
            if request.method == "OPTIONS":
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    },
                )
            return await oauth_authorization_server_metadata(request)

    def resolve_enterprise_id(enterprise_id: int | None) -> int:
        effective = enterprise_id if enterprise_id is not None else settings.enterprise_id
        if effective is None:
            raise ValueError(
                "enterprise_id is required for this tool. Pass enterprise_id explicitly or set VISTA_ENTERPRISE_ID."
            )
        return effective

    def get_request_token() -> str | None:
        access_token = get_access_token()
        return access_token.token if access_token else None

    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,
        delegated_mode=delegated_mode,
        require_request_token=settings.auth_mode == "delegated",
        get_request_token=get_request_token,
        resolve_enterprise_id=resolve_enterprise_id,
    )

    register_prompts(mcp)
    register_resources(mcp, settings)
    return mcp


def main() -> None:
    """Run the Vista MCP server over the configured transport."""

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    try:
        settings = VistaSettings()
        settings.validate_startup()
        server = create_server(settings)
    except (ValidationError, ValueError):
        logger.exception("Startup validation failed. Set VISTA_API_BASE_URL and auth values; see .env.example.")
        sys.exit(1)

    if settings.mcp_transport == "streamable-http":
        server.run(transport="streamable-http")
        return

    server.run(transport="stdio")


if __name__ == "__main__":
    main()

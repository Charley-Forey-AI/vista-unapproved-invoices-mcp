"""Configuration for the Vista MCP server."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VistaSettings(BaseSettings):
    """Environment-backed runtime settings for the Vista MCP server."""

    model_config = SettingsConfigDict(
        env_prefix="VISTA_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    api_base_url: str = Field(description="Base URL for the Vista API, for example https://api.example.com")
    bearer_token: str | None = Field(default=None, description="Optional Bearer token for Authorization header")
    api_key: str | None = Field(default=None, description="Optional API key value")
    api_key_header: str = Field(default="x-api-key", description="Header name used when api_key is configured")
    enterprise_id: int | None = Field(default=None, description="Default enterprise ID for scoped tools")
    correlation_id: str | None = Field(default=None, description="Optional default x-correlation-id value")
    request_timeout_seconds: float = Field(default=30.0, description="HTTP request timeout in seconds")
    health_base_url: str | None = Field(
        default=None,
        description="Optional dedicated base URL for health endpoints",
    )
    include_test_enterprise_tool: bool = Field(
        default=True,
        description="Expose test_list_enterprises tool for /api/v1/test/enterprise",
    )
    include_health_alive_tool: bool = Field(
        default=True,
        description="Expose health_alive tool for /health/alive endpoint",
    )
    mcp_transport: Literal["stdio", "streamable-http"] = Field(
        default="stdio",
        description="MCP transport mode.",
    )
    mcp_host: str = Field(default="127.0.0.1", description="Host for streamable-http transport.")
    mcp_port: int = Field(default=8000, description="Port for streamable-http transport.")
    mcp_streamable_http_path: str = Field(default="/mcp", description="Route path for streamable-http endpoint.")
    mcp_json_response: bool = Field(
        default=False,
        description="Whether streamable-http mode should force JSON responses.",
    )
    mcp_stateless_http: bool = Field(
        default=False,
        description="Whether streamable-http mode should run in stateless mode.",
    )
    auth_mode: Literal["static", "delegated", "hybrid", "server-managed"] = Field(
        default="static",
        description=(
            "Auth mode: static uses env credentials, delegated requires per-request bearer validation, "
            "hybrid prefers per-request bearer with static fallback, server-managed refreshes TID tokens."
        ),
    )
    client_id: str | None = Field(default=None, description="Trimble Identity OAuth client id.")
    client_secret: str | None = Field(default=None, description="Trimble Identity OAuth client secret.")
    scope: str | None = Field(
        default=None,
        description="Trimble Identity OAuth scope string. Use space-delimited values (no wrapping quotes).",
    )
    access_token: str | None = Field(default=None, description="Initial OAuth access token.")
    refresh_token: str | None = Field(default=None, description="OAuth refresh token.")
    token_url: str | None = Field(
        default=None,
        description="Optional OAuth token endpoint override; defaults to <VISTA_AUTH_ISSUER>/oauth/token.",
    )
    auth_issuer: str | None = Field(
        default=None,
        description="Expected issuer for delegated bearer tokens, e.g. https://stage.id.trimblecloud.com",
    )
    auth_jwks_url: str | None = Field(
        default=None,
        description="JWKS URL used to validate delegated bearer tokens.",
    )
    auth_audience: str | None = Field(
        default=None,
        description="Optional expected audience for delegated bearer tokens.",
    )
    auth_required_scopes: str | None = Field(
        default=None,
        description="Required delegated scopes as space- or comma-delimited values.",
    )
    auth_jwks_cache_ttl_seconds: int = Field(
        default=300,
        description="Seconds to cache JWKS before refresh.",
    )
    auth_jwt_leeway_seconds: int = Field(
        default=60,
        description="Clock-skew leeway when validating exp/nbf/iat claims.",
    )
    auth_resource_server_url: str | None = Field(
        default=None,
        description="Public URL of this MCP resource server used in WWW-Authenticate metadata.",
    )

    def has_auth(self) -> bool:
        """Return True when either bearer token or API key authentication is configured."""

        return bool(self.bearer_token or self.api_key)

    def required_scopes(self) -> list[str]:
        """Return normalized required scope names for delegated validation."""

        if not self.auth_required_scopes:
            return []

        normalized = self.auth_required_scopes.replace(",", " ")
        return [scope for scope in normalized.split() if scope]

    def normalized_scope(self) -> str | None:
        """Return a normalized OAuth scope string."""

        if not self.scope:
            return None
        normalized = self.scope.strip()
        if (
            len(normalized) >= 2
            and normalized[0] == normalized[-1]
            and normalized[0] in {'"', "'"}
        ):
            normalized = normalized[1:-1]
        normalized = normalized.replace(",", " ")
        scopes = [scope for scope in normalized.split() if scope]
        if not scopes:
            return None
        return " ".join(scopes)

    def validate_startup(self) -> None:
        """Validate auth and transport settings before server startup."""

        if self.auth_mode == "static":
            if not self.has_auth():
                raise ValueError(
                    "VISTA_AUTH_MODE=static requires VISTA_BEARER_TOKEN or VISTA_API_KEY."
                )
            return

        if self.auth_mode == "server-managed":
            if self.mcp_transport != "streamable-http":
                raise ValueError(
                    "VISTA_AUTH_MODE=server-managed requires VISTA_MCP_TRANSPORT=streamable-http."
                )
            missing = []
            if not self.client_id:
                missing.append("VISTA_CLIENT_ID")
            if not self.client_secret:
                missing.append("VISTA_CLIENT_SECRET")
            if not self.refresh_token:
                missing.append("VISTA_REFRESH_TOKEN")
            issuer = self.auth_issuer
            token_url = self.token_url
            if not issuer and not token_url:
                missing.append("VISTA_TOKEN_URL (or VISTA_AUTH_ISSUER)")
            if missing:
                joined = ", ".join(missing)
                raise ValueError(f"Missing server-managed auth settings: {joined}")
            return

        if self.mcp_transport != "streamable-http":
            raise ValueError(
                f"VISTA_AUTH_MODE={self.auth_mode} requires VISTA_MCP_TRANSPORT=streamable-http."
            )

        missing = []
        if not self.auth_issuer:
            missing.append("VISTA_AUTH_ISSUER")
        if not self.auth_jwks_url:
            missing.append("VISTA_AUTH_JWKS_URL")
        if not self.auth_resource_server_url:
            missing.append("VISTA_AUTH_RESOURCE_SERVER_URL")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing delegated auth settings: {joined}")

        if self.auth_mode == "hybrid" and not self.has_auth():
            raise ValueError(
                "VISTA_AUTH_MODE=hybrid requires static fallback auth: set VISTA_BEARER_TOKEN or VISTA_API_KEY."
            )


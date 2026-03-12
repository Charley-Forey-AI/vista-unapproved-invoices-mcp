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

    def has_auth(self) -> bool:
        """Return True when either bearer token or API key authentication is configured."""

        return bool(self.bearer_token or self.api_key)


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
    request_timeout_seconds: float = Field(
        default=45.0,
        description="Legacy total HTTP request timeout in seconds (used as fallback when granular timeouts are unset).",
    )
    request_connect_timeout_seconds: float | None = Field(
        default=10.0,
        description="Connect timeout for Vista API requests in seconds.",
    )
    request_read_timeout_seconds: float | None = Field(
        default=45.0,
        description="Read timeout for Vista API requests in seconds.",
    )
    request_write_timeout_seconds: float | None = Field(
        default=30.0,
        description="Write timeout for Vista API requests in seconds.",
    )
    request_pool_timeout_seconds: float | None = Field(
        default=10.0,
        description="Pool acquisition timeout for Vista API requests in seconds.",
    )
    request_max_connections: int = Field(
        default=100,
        description="Max concurrent connections for Vista API HTTP client.",
    )
    request_max_keepalive_connections: int = Field(
        default=40,
        description="Max keepalive connections for Vista API HTTP client.",
    )
    max_concurrent_requests: int = Field(
        default=32,
        description="In-process bulkhead cap for concurrent outbound Vista requests.",
    )
    max_concurrent_analysis_runs: int = Field(
        default=4,
        description="In-process bulkhead cap for concurrent analysis runs.",
    )
    max_bulk_items: int = Field(
        default=100,
        description="Maximum number of items allowed in a single bulk create request.",
    )
    max_batch_size: int | None = Field(
        default=None,
        description="Optional override for maximum bulk request items. If set, takes precedence over max_bulk_items.",
    )
    read_only_mode: bool = Field(
        default=False,
        description="When true, write/bulk tools are disabled.",
    )
    write_enabled_domains: str | None = Field(
        default=None,
        description="Optional comma- or space-delimited write domains allowed (e.g. ap,po,jc).",
    )
    transient_retry_attempts: int = Field(
        default=3,
        description="Number of transient retries for idempotent operations (429/503/network).",
    )
    transient_retry_base_seconds: float = Field(
        default=0.75,
        description="Base delay for transient retries.",
    )
    transient_retry_max_seconds: float = Field(
        default=8.0,
        description="Maximum delay between transient retries.",
    )
    transient_retry_jitter_seconds: float = Field(
        default=0.25,
        description="Random jitter added to transient retry backoff in seconds.",
    )
    transient_retry_status_codes: str = Field(
        default="429,500,502,503,504",
        description="Comma- or space-delimited HTTP status codes retried for idempotent operations.",
    )
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
    analysis_default_window_days: int = Field(
        default=365,
        description="Default lookback window for unapproved invoice analysis.",
    )
    analysis_default_top_n: int = Field(
        default=5,
        description="Default number of top-risk invoices returned in analysis.",
    )
    analysis_page_size: int = Field(
        default=100,
        description="Page size used for read-only unapproved invoice analysis collection.",
    )
    analysis_max_pages: int = Field(
        default=10,
        description="Maximum pages to collect during unapproved invoice analysis.",
    )
    analysis_stale_days: int = Field(
        default=30,
        description="Invoice age threshold (days) for stale invoice findings.",
    )
    analysis_high_amount_threshold: float = Field(
        default=50000.0,
        description="Amount threshold for high-risk invoice findings.",
    )
    analysis_duplicate_amount_delta: float = Field(
        default=0.01,
        description="Allowed amount delta when detecting potential duplicate invoices.",
    )
    analysis_policy_profile: Literal["standard", "strict", "lenient"] = Field(
        default="standard",
        description="Default analysis policy profile used for scoring and thresholds.",
    )
    analysis_cache_ttl_seconds: int = Field(
        default=180,
        description="TTL for cached analysis snapshots used by queue-first tools.",
    )
    analysis_cache_backend: Literal["memory", "redis"] = Field(
        default="memory",
        description="Backend used for analysis cache snapshots.",
    )
    analysis_cache_prefix: str = Field(
        default="vista:analysis",
        description="Redis key prefix used for analysis cache when backend=redis.",
    )
    redis_url: str | None = Field(
        default=None,
        description="Redis connection URL (required when analysis_cache_backend=redis).",
    )
    analysis_fail_on_partial: bool = Field(
        default=False,
        description="When true, analysis tools fail instead of returning partial collections.",
    )
    token_http_timeout_seconds: float = Field(
        default=20.0,
        description="HTTP timeout used for OAuth token refresh/exchange requests.",
    )
    auth_jwks_timeout_seconds: float = Field(
        default=15.0,
        description="HTTP timeout used when refreshing delegated auth JWKS.",
    )
    token_exchange_cache_ttl_seconds: int = Field(
        default=300,
        description="Fallback token-exchange cache TTL (seconds) when token expiry cannot be inferred.",
    )
    token_exchange_refresh_skew_seconds: int = Field(
        default=30,
        description="Seconds before expiry when cached exchanged tokens should be refreshed.",
    )
    reliability_canary_enabled: bool = Field(
        default=False,
        description="Enable canary metadata markers for rollout visibility.",
    )
    reliability_canary_sample_rate: float = Field(
        default=0.1,
        description="Canary sample rate (0.0-1.0) used for reliability experiments.",
    )
    reliability_rollback_error_rate_threshold: float = Field(
        default=0.05,
        description="Rollback threshold for error-rate regression during canary rollout.",
    )
    reliability_rollback_p95_ms_threshold: int = Field(
        default=4000,
        description="Rollback threshold for p95 latency regression during canary rollout.",
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
    auth_strategy: Literal["delegated_passthrough", "token_exchange"] = Field(
        default="delegated_passthrough",
        description=(
            "Delegated auth strategy. delegated_passthrough forwards actor token directly to Vista. "
            "token_exchange performs OAuth token exchange before Vista calls."
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
    token_exchange_token_url: str | None = Field(
        default=None,
        description="Optional token exchange endpoint override; defaults to token_url or <VISTA_AUTH_ISSUER>/oauth/token.",
    )
    token_exchange_scope: str | None = Field(
        default=None,
        description="Optional scope requested when exchanging actor tokens for Vista API tokens.",
    )
    token_exchange_subject_token_type: str = Field(
        default="urn:ietf:params:oauth:token-type:jwt",
        description=(
            "OAuth token exchange subject_token_type. "
            "Use jwt for JWT actor tokens unless your IdP requires another type."
        ),
    )
    token_exchange_requested_token_type: str | None = Field(
        default="urn:ietf:params:oauth:token-type:access_token",
        description="Optional requested_token_type for OAuth token exchange.",
    )
    token_exchange_audience: str | None = Field(
        default=None,
        description="Optional audience requested in token exchange requests.",
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

        return _normalize_scope_values(self.auth_required_scopes)

    def normalized_scope(self) -> str | None:
        """Return a normalized OAuth scope string."""

        if not self.scope:
            return None
        scopes = _normalize_scope_values(self.scope)
        if not scopes:
            return None
        return " ".join(scopes)

    def normalized_auth_audience(self) -> str | list[str] | None:
        """Return normalized delegated audience value(s) for JWT validation."""

        if not self.auth_audience:
            return None
        audience_values = _normalize_scope_values(self.auth_audience)
        if not audience_values:
            return None
        if len(audience_values) == 1:
            return audience_values[0]
        return audience_values

    def normalized_token_exchange_scope(self) -> str | None:
        """Return normalized token exchange scope string."""

        if not self.token_exchange_scope:
            return None
        scopes = _normalize_scope_values(self.token_exchange_scope)
        if not scopes:
            return None
        return " ".join(scopes)

    def normalized_token_exchange_audience(self) -> str | None:
        """Return normalized token exchange audience value."""

        if not self.token_exchange_audience:
            return None
        audience_values = _normalize_scope_values(self.token_exchange_audience)
        if not audience_values:
            return None
        return " ".join(audience_values)

    def validate_startup(self) -> None:
        """Validate auth and transport settings before server startup."""
        if self.analysis_cache_backend == "redis" and not self.redis_url:
            raise ValueError("VISTA_REDIS_URL is required when VISTA_ANALYSIS_CACHE_BACKEND=redis.")

        if self.auth_strategy == "token_exchange" and self.auth_mode not in {"delegated", "hybrid"}:
            raise ValueError(
                "VISTA_AUTH_STRATEGY=token_exchange requires VISTA_AUTH_MODE=delegated or hybrid."
            )

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

        required_scopes = self.required_scopes()
        if self.auth_required_scopes and not required_scopes:
            raise ValueError("VISTA_AUTH_REQUIRED_SCOPES is set but no valid scope values were parsed.")

        normalized_scope = self.normalized_scope()
        if normalized_scope and required_scopes:
            available_scope_set = set(normalized_scope.split())
            missing_required = [scope for scope in required_scopes if scope not in available_scope_set]
            if missing_required:
                raise ValueError(
                    "Delegated scope alignment failed: VISTA_AUTH_REQUIRED_SCOPES must be present in VISTA_SCOPE. "
                    f"Missing from VISTA_SCOPE: {', '.join(missing_required)}"
                )

        if self.auth_strategy == "token_exchange":
            missing_exchange = []
            if not self.client_id:
                missing_exchange.append("VISTA_CLIENT_ID")
            if not self.client_secret:
                missing_exchange.append("VISTA_CLIENT_SECRET")
            if not (self.token_exchange_token_url or self.token_url or self.auth_issuer):
                missing_exchange.append("VISTA_TOKEN_EXCHANGE_TOKEN_URL (or VISTA_TOKEN_URL or VISTA_AUTH_ISSUER)")
            if missing_exchange:
                joined = ", ".join(missing_exchange)
                raise ValueError(f"Missing token exchange settings: {joined}")

        if self.auth_mode == "hybrid" and not self.has_auth():
            raise ValueError(
                "VISTA_AUTH_MODE=hybrid requires static fallback auth: set VISTA_BEARER_TOKEN or VISTA_API_KEY."
            )

    def effective_max_batch_size(self) -> int:
        """Return configured max batch size with compatibility fallback."""

        if self.max_batch_size is not None:
            return self.max_batch_size
        return self.max_bulk_items

    def normalized_write_domains(self) -> set[str]:
        """Return normalized allowed write domains."""

        if not self.write_enabled_domains:
            return set()
        normalized = self.write_enabled_domains.replace(",", " ")
        return {value.strip().lower() for value in normalized.split() if value.strip()}

    def retry_status_codes(self) -> set[int]:
        """Return normalized transient retry status codes."""

        normalized = self.transient_retry_status_codes.replace(",", " ")
        values: set[int] = set()
        for raw in normalized.split():
            raw = raw.strip()
            if not raw:
                continue
            try:
                code = int(raw)
            except ValueError:
                continue
            if 100 <= code <= 599:
                values.add(code)
        if not values:
            return {429, 500, 502, 503, 504}
        return values


def _normalize_scope_values(raw_value: str) -> list[str]:
    normalized = raw_value.strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {'"', "'"}
    ):
        normalized = normalized[1:-1]
    normalized = normalized.replace(",", " ")
    return [scope for scope in normalized.split() if scope]


"""Vista MCP server entrypoint."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from pydantic import Field, ValidationError
from starlette.requests import Request
from starlette.responses import Response

from .api import VistaApiClient
from .auth import TrimbleTokenVerifier
from .config import VistaSettings
from .models import (
    EnterpriseGetResponse,
    EnterpriseListResponse,
    HealthResponse,
    ProjectGetResponse,
    ProjectListResponse,
    QueryFilter,
    QueryRequest,
    UnapprovedInvoiceCreateItem,
    UnapprovedInvoiceCreateRequest,
    UnapprovedInvoiceCreateResponse,
    UnapprovedInvoiceGetResponse,
    UnapprovedInvoiceQueryResponse,
    VendorGetResponse,
    VendorListResponse,
)
from .prompts import register_prompts
from .resources import register_resources
from .token_manager import TidTokenManager

logger = logging.getLogger(__name__)


def _to_json(data: object) -> str:
    return json.dumps(data, indent=2, default=str)


def create_server(settings: VistaSettings) -> MCPServer:
    """Create and configure the Vista MCP server instance."""

    token_manager: TidTokenManager | None = None
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
        )

    api = VistaApiClient(settings, token_manager=token_manager)
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
            audience=settings.auth_audience,
            required_scopes=required_scopes,
            jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
            jwt_leeway_seconds=settings.auth_jwt_leeway_seconds,
        )

    @asynccontextmanager
    async def lifespan(_: MCPServer):
        try:
            yield
        finally:
            await api.close()
            if token_manager is not None:
                await token_manager.close()
            if token_verifier is not None:
                await token_verifier.close()

    mcp = MCPServer(
        name="vista",
        title="Vista API MCP Server",
        description=(
            "Tools for Enterprise, Unapproved Invoice, Project, Vendor, and Health APIs. "
            "Tool descriptions include dependency guidance and response interpretation hints so IDs can be "
            "discovered and reused with follow-up tools. For complex tasks, read vista://guides/dependencies, "
            "vista://guides/workflows, vista://guides/response-interpretation, vista://guides/filters, and "
            "vista://guides/errors-and-edge-cases."
        ),
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
            "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
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

    def _normalize_filter_values(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, list):
            return [str(value) for value in values if value is not None]
        return [str(values)]

    def _normalize_filter_item(filter_item: QueryFilter | dict[str, Any]) -> QueryFilter:
        if isinstance(filter_item, QueryFilter):
            return filter_item
        if not isinstance(filter_item, dict):
            raise ValueError("Each filter must be an object with field/operator/values.")

        normalized_filter = dict(filter_item)
        normalized_filter["values"] = _normalize_filter_values(normalized_filter.get("values"))
        return QueryFilter.model_validate(normalized_filter)

    def build_query(
        filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None,
    ) -> QueryRequest:
        if filters is None:
            return QueryRequest(filters=[])

        raw_filters: list[QueryFilter | dict[str, Any]]
        if isinstance(filters, list):
            raw_filters = filters
        else:
            raw_filters = [filters]

        normalized_filters = [_normalize_filter_item(filter_item) for filter_item in raw_filters]
        return QueryRequest(filters=normalized_filters)

    def normalize_invoice_items(
        items: list[UnapprovedInvoiceCreateItem | dict[str, Any]] | dict[str, Any],
    ) -> list[UnapprovedInvoiceCreateItem]:
        raw_items: list[UnapprovedInvoiceCreateItem | dict[str, Any]]
        if isinstance(items, list):
            raw_items = items
        else:
            raw_items = [items]

        normalized_items: list[UnapprovedInvoiceCreateItem] = []
        for item in raw_items:
            if isinstance(item, UnapprovedInvoiceCreateItem):
                normalized_items.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError("Each invoice item must be an object.")

            normalized_item = dict(item)
            files = normalized_item.get("files")
            if files is None:
                normalized_item["files"] = []
            elif not isinstance(files, list):
                normalized_item["files"] = [files]

            normalized_items.append(UnapprovedInvoiceCreateItem.model_validate(normalized_item))

        return normalized_items

    async def with_tool_error_logging(
        tool_name: str,
        operation: Callable[[], Awaitable[str]],
    ) -> str:
        request_token = None
        if delegated_mode:
            access_token = get_access_token()
            request_token = access_token.token if access_token else None
        reset_token = api.set_request_bearer_token(request_token)
        try:
            return await operation()
        except (ValueError, RuntimeError, ValidationError):
            logger.exception("Tool failed: %s", tool_name)
            raise
        finally:
            api.reset_request_bearer_token(reset_token)

    @mcp.tool(
        description=(
            "Get one Enterprise by ID when you need enterprise/company context for scoped tools. "
            "Response contains one item (item.id, item.name, and related metadata). Reuse item.id as "
            "enterprise_id in get_vendor, get_project, query_unapproved_invoices, and create_unapproved_invoices."
        )
    )
    async def get_enterprise(
        enterprise_id: int | None = Field(
            default=None,
            description=(
                "Enterprise id to fetch. Optional when VISTA_ENTERPRISE_ID is configured. "
                "Use list_enterprises to discover IDs."
            ),
        ),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            payload = await api.get_enterprise(resolve_enterprise_id(enterprise_id), includes, correlation_id)
            parsed = EnterpriseGetResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("get_enterprise", run)

    @mcp.tool(
        description=(
            "List enterprises with optional filters when enterprise_id is unknown. "
            "Response includes items plus pageSize/currentPage for pagination. "
            "Extract items[].id for downstream enterprise-scoped tools."
        )
    )
    async def list_enterprises(
        filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
            default=None,
            description=(
                "Optional filters: [{field, operator, values[]}]. "
                "Field/operator are entity-specific. See vista://guides/filters for examples."
            ),
        ),
        order_by: str | None = Field(default=None, description="Optional orderBy query value."),
        order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
        limit: int | None = Field(
            default=None,
            description="Optional page size. Response includes pageSize/currentPage.",
        ),
        page: int | None = Field(default=None, description="Optional page index. Use with limit for pagination."),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            query = build_query(filters)
            payload = await api.list_enterprises(
                query.model_dump(by_alias=True, exclude_none=True),
                order_by=order_by,
                order_by_asc=order_by_asc,
                limit=limit,
                page=page,
                includes=includes,
                correlation_id=correlation_id,
            )
            parsed = EnterpriseListResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("list_enterprises", run)

    if settings.include_test_enterprise_tool:

        @mcp.tool(
            description=(
                "List enterprises using the test endpoint /api/v1/test/enterprise. "
                "Useful for sandbox validation workflows. Response includes items plus pageSize/currentPage."
            )
        )
        async def test_list_enterprises(
            filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
                default=None,
                description=(
                    "Optional filters: [{field, operator, values[]}]. "
                    "See vista://guides/filters for examples."
                ),
            ),
            order_by: str | None = Field(default=None, description="Optional orderBy query value."),
            order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
            limit: int | None = Field(
                default=None,
                description="Optional page size. Response includes pageSize/currentPage.",
            ),
            page: int | None = Field(default=None, description="Optional page index. Use with limit for pagination."),
            includes: str | None = Field(default=None, description="Optional includes query value."),
            correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
        ) -> str:
            async def run() -> str:
                query = build_query(filters)
                payload = await api.test_list_enterprises(
                    query.model_dump(by_alias=True, exclude_none=True),
                    order_by=order_by,
                    order_by_asc=order_by_asc,
                    limit=limit,
                    page=page,
                    includes=includes,
                    correlation_id=correlation_id,
                )
                parsed = EnterpriseListResponse.model_validate(payload)
                return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

            return await with_tool_error_logging("test_list_enterprises", run)

    @mcp.tool(
        description=(
            "Create unapproved AP invoices in bulk. Dependencies: each item needs companyId and vendorId. "
            "Use get_enterprise/list_enterprises for enterprise/company context, get_vendor/list_vendors for "
            "vendorId and vendorAlternateAddressId, and get_project/list_projects for project context. "
            "Response is per-item with statusCode/action/message/item, so partial success is possible and each "
            "result should be inspected."
        )
    )
    async def create_unapproved_invoices(
        items: list[UnapprovedInvoiceCreateItem | dict[str, Any]] | dict[str, Any] = Field(
            description=(
                "Invoice create items. Required fields include companyId, vendorId, invoiceNumber, "
                "invoiceAmount, invoiceDate, monthYear, enteredBy. Optional fields include purchaseOrderId, "
                "subcontractId, vendorAlternateAddressId, salesTax, valueAddedTax, invoiceDescription. "
                "Dates should be ISO 8601. Use get_vendor/list_vendors and get_enterprise/list_enterprises "
                "to resolve required IDs."
            )
        ),
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            items_models = normalize_invoice_items(items)
            body = UnapprovedInvoiceCreateRequest(items=items_models)
            payload = await api.create_unapproved_invoices(
                resolve_enterprise_id(enterprise_id),
                body.model_dump(by_alias=True, exclude_none=True),
                correlation_id,
            )
            parsed = UnapprovedInvoiceCreateResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("create_unapproved_invoices", run)

    @mcp.tool(
        description=(
            "Get one unapproved invoice by UUID. Use this to retrieve vendorId/project context before calling "
            "related vendor/project tools. Response contains one item with vendorId, companyId, purchaseOrderId, "
            "subcontractId, invoiceNumber, amounts, and dates that can drive downstream lookups."
        )
    )
    async def get_unapproved_invoice(
        id: UUID = Field(description="Unapproved invoice UUID. Use query_unapproved_invoices to discover IDs."),
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            payload = await api.get_unapproved_invoice(
                resolve_enterprise_id(enterprise_id),
                str(id),
                includes,
                correlation_id,
            )
            parsed = UnapprovedInvoiceGetResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("get_unapproved_invoice", run)

    @mcp.tool(
        description=(
            "Get unapproved invoice action detail by UUID. Use when action-level metadata is required for "
            "workflow or troubleshooting. Use this when you need action status/message context in addition to "
            "invoice fields."
        )
    )
    async def get_unapproved_invoice_action(
        id: UUID = Field(description="Unapproved invoice UUID. Use query_unapproved_invoices to discover IDs."),
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            payload = await api.get_unapproved_invoice_action(
                resolve_enterprise_id(enterprise_id),
                str(id),
                includes,
                correlation_id,
            )
            parsed = UnapprovedInvoiceGetResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("get_unapproved_invoice_action", run)

    @mcp.tool(
        description=(
            "List unapproved invoices (paged). Use filters to narrow records, then call get_vendor/get_project "
            "for enrichment of selected results. Response includes items plus pageSize/currentPage; reuse "
            "items[].id for get_unapproved_invoice and items[].vendorId for get_vendor."
        )
    )
    async def query_unapproved_invoices(
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
            default=None,
            description=(
                "Optional filters: [{field, operator, values[]}]. "
                "Common invoice filters include invoiceNumber and vendorId. See vista://guides/filters."
            ),
        ),
        order_by: str | None = Field(default=None, description="Optional orderBy query value."),
        order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
        limit: int | None = Field(
            default=None,
            description="Optional page size. Response includes pageSize/currentPage.",
        ),
        page: int | None = Field(default=None, description="Optional page index. Use with limit for pagination."),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            query = build_query(filters)
            payload = await api.query_unapproved_invoices(
                resolve_enterprise_id(enterprise_id),
                query.model_dump(by_alias=True, exclude_none=True),
                order_by=order_by,
                order_by_asc=order_by_asc,
                limit=limit,
                page=page,
                includes=includes,
                correlation_id=correlation_id,
            )
            parsed = UnapprovedInvoiceQueryResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("query_unapproved_invoices", run)

    @mcp.tool(
        description=(
            "Get a project (job) by UUID when you need project/contract context before invoice work. "
            "Response item includes id, job, description, and contracts[] details."
        )
    )
    async def get_project(
        id: UUID = Field(description="Project UUID. Use list_projects to discover IDs."),
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            payload = await api.get_project(resolve_enterprise_id(enterprise_id), str(id), includes, correlation_id)
            parsed = ProjectGetResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("get_project", run)

    @mcp.tool(
        description=(
            "List projects (jobs) with optional filters for project lookup before invoice creation. "
            "Response includes items plus pageSize/currentPage."
        )
    )
    async def list_projects(
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
            default=None,
            description=(
                "Optional filters: [{field, operator, values[]}]. "
                "Common project filters include job and companyCode. See vista://guides/filters."
            ),
        ),
        order_by: str | None = Field(default=None, description="Optional orderBy query value."),
        order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
        limit: int | None = Field(
            default=None,
            description="Optional page size. Response includes pageSize/currentPage.",
        ),
        page: int | None = Field(default=None, description="Optional page index. Use with limit for pagination."),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            query = build_query(filters)
            payload = await api.list_projects(
                resolve_enterprise_id(enterprise_id),
                query.model_dump(by_alias=True, exclude_none=True),
                order_by=order_by,
                order_by_asc=order_by_asc,
                limit=limit,
                page=page,
                includes=includes,
                correlation_id=correlation_id,
            )
            parsed = ProjectListResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("list_projects", run)

    @mcp.tool(
        description=(
            "Get a vendor by UUID. Use this to retrieve vendorId and vendorAlternateAddressId dependencies "
            "for create_unapproved_invoices. Response item includes id and alternateAddresses[].id "
            "for vendorAlternateAddressId."
        )
    )
    async def get_vendor(
        id: UUID = Field(description="Vendor UUID. Use list_vendors to discover IDs."),
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            payload = await api.get_vendor(resolve_enterprise_id(enterprise_id), str(id), includes, correlation_id)
            parsed = VendorGetResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("get_vendor", run)

    @mcp.tool(
        description=(
            "List vendors (paged). Use this to discover vendor IDs before create_unapproved_invoices. "
            "Response includes items plus pageSize/currentPage and alternateAddresses for each vendor."
        )
    )
    async def list_vendors(
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
        ),
        filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
            default=None,
            description=(
                "Optional filters: [{field, operator, values[]}]. "
                "Common vendor filters include name and vendorCode. See vista://guides/filters."
            ),
        ),
        order_by: str | None = Field(default=None, description="Optional orderBy query value."),
        order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
        limit: int | None = Field(
            default=None,
            description="Optional page size. Response includes pageSize/currentPage.",
        ),
        page: int | None = Field(default=None, description="Optional page index. Use with limit for pagination."),
        includes: str | None = Field(default=None, description="Optional includes query value."),
        correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
    ) -> str:
        async def run() -> str:
            query = build_query(filters)
            payload = await api.list_vendors(
                resolve_enterprise_id(enterprise_id),
                query.model_dump(by_alias=True, exclude_none=True),
                order_by=order_by,
                order_by_asc=order_by_asc,
                limit=limit,
                page=page,
                includes=includes,
                correlation_id=correlation_id,
            )
            parsed = VendorListResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("list_vendors", run)

    @mcp.tool(
        description=(
            "Check /health/ready endpoint (SQL + Blob readiness). No enterprise id required. "
            "Response includes Status, Description, and Exception; interpret Status for healthy/unhealthy."
        )
    )
    async def health_ready() -> str:
        async def run() -> str:
            payload = await api.health_ready()
            parsed = HealthResponse.model_validate(payload)
            return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

        return await with_tool_error_logging("health_ready", run)

    if settings.include_health_alive_tool:

        @mcp.tool(
            description=(
                "Check /health/alive endpoint (Kafka consumer liveness). No enterprise id required. "
                "Response includes Status, Description, and Exception; interpret Status for healthy/unhealthy."
            )
        )
        async def health_alive() -> str:
            async def run() -> str:
                payload = await api.health_alive()
                parsed = HealthResponse.model_validate(payload)
                return _to_json(parsed.model_dump(by_alias=True, exclude_none=True))

            return await with_tool_error_logging("health_alive", run)

    register_prompts(mcp)
    register_resources(mcp)
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
        server.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            streamable_http_path=settings.mcp_streamable_http_path,
            json_response=settings.mcp_json_response,
            stateless_http=settings.mcp_stateless_http,
        )
        return

    server.run(transport="stdio")


if __name__ == "__main__":
    main()

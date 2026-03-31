"""HTTP API client for Vista endpoints used by MCP tools."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import random
from typing import Any

import httpx

from .config import VistaSettings
from .endpoint_registry import EndpointSpec
from .token_exchange import TokenExchangeProvider
from .token_manager import TidTokenManager

logger = logging.getLogger(__name__)
_API_METRICS: dict[str, float | int] = {
    "requestsTotal": 0,
    "requestsSucceeded": 0,
    "requestsFailed": 0,
    "networkErrors": 0,
    "transientRetries": 0,
    "retryableStatusResponses": 0,
    "partialCollections": 0,
}


def get_api_metrics_snapshot() -> dict[str, float | int]:
    """Expose aggregate API transport metrics for observability resources."""

    return dict(_API_METRICS)


class VistaApiClient:
    """Thin async client wrapper for Vista REST API calls."""

    def __init__(
        self,
        settings: VistaSettings,
        token_manager: TidTokenManager | None = None,
        token_exchange_provider: TokenExchangeProvider | None = None,
    ):
        self._settings = settings
        self._token_manager = token_manager
        self._token_exchange_provider = token_exchange_provider
        self._api_base_url = self._normalize_api_base_url(str(settings.api_base_url))
        health_base = settings.health_base_url or settings.api_base_url
        self._health_base_url = self._normalize_api_base_url(str(health_base))
        self._timeout = self._build_timeout()
        self._limits = httpx.Limits(
            max_connections=max(1, settings.request_max_connections),
            max_keepalive_connections=max(1, settings.request_max_keepalive_connections),
        )
        self._request_semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_requests))
        self._retry_status_codes = settings.retry_status_codes()
        self._client = httpx.AsyncClient(base_url=self._api_base_url, timeout=self._timeout, limits=self._limits)
        self._health_client = httpx.AsyncClient(base_url=self._health_base_url, timeout=self._timeout, limits=self._limits)
        self._request_bearer_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "vista_request_bearer_token", default=None
        )

    @staticmethod
    def _normalize_api_base_url(raw_url: str) -> str:
        """Normalize base URL so endpoint paths don't duplicate /api/v1."""

        normalized = raw_url.rstrip("/")
        if normalized.lower().endswith("/api/v1"):
            return normalized[:-7]
        return normalized

    def _build_timeout(self) -> httpx.Timeout:
        fallback = max(0.1, float(self._settings.request_timeout_seconds))
        connect = self._settings.request_connect_timeout_seconds
        read = self._settings.request_read_timeout_seconds
        write = self._settings.request_write_timeout_seconds
        pool = self._settings.request_pool_timeout_seconds
        return httpx.Timeout(
            timeout=fallback,
            connect=connect if connect is not None else fallback,
            read=read if read is not None else fallback,
            write=write if write is not None else fallback,
            pool=pool if pool is not None else fallback,
        )

    async def close(self) -> None:
        """Close underlying HTTP client resources."""

        await self._client.aclose()
        await self._health_client.aclose()
        if self._token_exchange_provider is not None:
            await self._token_exchange_provider.close()

    def _ensure_clients_open(self) -> None:
        if self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self._api_base_url, timeout=self._timeout, limits=self._limits)
        if self._health_client.is_closed:
            self._health_client = httpx.AsyncClient(
                base_url=self._health_base_url,
                timeout=self._timeout,
                limits=self._limits,
            )

    async def _build_headers(
        self,
        correlation_id: str | None = None,
        *,
        require_auth: bool = True,
    ) -> tuple[dict[str, str], str | None]:
        headers: dict[str, str] = {"Accept": "application/json"}
        request_bearer = self._request_bearer_token.get()
        auth_source: str | None = None

        if require_auth:
            if self._settings.auth_mode == "delegated" and not request_bearer:
                raise RuntimeError(
                    "Delegated actor token missing for this request. "
                    "Re-authenticate in Agent Studio and retry."
                )
            if request_bearer:
                if self._settings.auth_strategy == "token_exchange":
                    if self._token_exchange_provider is None:
                        raise RuntimeError(
                            "Token exchange strategy is configured but no exchange provider is available."
                        )
                    exchanged_token = await self._token_exchange_provider.exchange(request_bearer)
                    headers["Authorization"] = f"Bearer {exchanged_token}"
                    auth_source = "request-token-exchange"
                else:
                    headers["Authorization"] = f"Bearer {request_bearer}"
                    auth_source = "request-bearer"
            elif self._token_manager:
                token = await self._token_manager.get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                auth_source = "server-managed"
            elif self._settings.bearer_token:
                headers["Authorization"] = f"Bearer {self._settings.bearer_token}"
                auth_source = "static-bearer"
            elif self._settings.api_key:
                headers[self._settings.api_key_header] = self._settings.api_key
                auth_source = "api-key"
            else:
                raise ValueError(
                    "No authentication configured. Set VISTA_BEARER_TOKEN or VISTA_API_KEY in your environment."
                )

        effective_correlation = correlation_id or self._settings.correlation_id
        if effective_correlation:
            headers["x-correlation-id"] = effective_correlation

        return headers, auth_source

    def set_request_bearer_token(self, token: str | None) -> contextvars.Token[str | None]:
        """Set request-scoped bearer token for delegated auth calls."""

        return self._request_bearer_token.set(token)

    def reset_request_bearer_token(self, token: contextvars.Token[str | None]) -> None:
        """Reset request-scoped bearer token."""

        self._request_bearer_token.reset(token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        require_auth: bool = True,
        use_health_client: bool = False,
        allow_transient_retry: bool = False,
    ) -> dict[str, Any]:
        _API_METRICS["requestsTotal"] = int(_API_METRICS["requestsTotal"]) + 1
        headers, auth_source = await self._build_headers(
            correlation_id=correlation_id,
            require_auth=require_auth,
        )
        response: httpx.Response | None = None
        attempt = 0
        max_attempts = max(0, self._settings.transient_retry_attempts)
        base_delay = max(0.0, self._settings.transient_retry_base_seconds)
        max_delay = max(0.0, self._settings.transient_retry_max_seconds)
        retry_jitter = max(0.0, self._settings.transient_retry_jitter_seconds)

        while True:
            self._ensure_clients_open()
            active_client = self._health_client if use_health_client else self._client
            try:
                async with self._request_semaphore:
                    response = await active_client.request(method, path, headers=headers, params=params, json=body)
            except RuntimeError as exc:
                if "client has been closed" not in str(exc).lower():
                    _API_METRICS["requestsFailed"] = int(_API_METRICS["requestsFailed"]) + 1
                    raise
                if attempt >= max_attempts:
                    _API_METRICS["requestsFailed"] = int(_API_METRICS["requestsFailed"]) + 1
                    raise RuntimeError(f"{method} {path} failed because HTTP client was unexpectedly closed.") from exc
                _API_METRICS["transientRetries"] = int(_API_METRICS["transientRetries"]) + 1
                await asyncio.sleep(self._compute_retry_delay(attempt, base_delay, max_delay, retry_jitter))
                attempt += 1
                continue
            except httpx.RequestError as exc:
                _API_METRICS["networkErrors"] = int(_API_METRICS["networkErrors"]) + 1
                if not allow_transient_retry or attempt >= max_attempts:
                    _API_METRICS["requestsFailed"] = int(_API_METRICS["requestsFailed"]) + 1
                    raise RuntimeError(
                        f"{method} {path} failed due to network error after {attempt + 1} attempt(s)."
                    ) from exc
                _API_METRICS["transientRetries"] = int(_API_METRICS["transientRetries"]) + 1
                delay = self._compute_retry_delay(attempt, base_delay, max_delay, retry_jitter)
                await asyncio.sleep(delay)
                attempt += 1
                continue

            if allow_transient_retry and response.status_code in self._retry_status_codes and attempt < max_attempts:
                _API_METRICS["retryableStatusResponses"] = int(_API_METRICS["retryableStatusResponses"]) + 1
                retry_after = response.headers.get("Retry-After")
                delay = self._compute_retry_delay(attempt, base_delay, max_delay, retry_jitter, retry_after=retry_after)
                _API_METRICS["transientRetries"] = int(_API_METRICS["transientRetries"]) + 1
                await asyncio.sleep(delay)
                attempt += 1
                continue
            break

        if (
            response.status_code == 401
            and require_auth
            and self._token_manager is not None
            and auth_source == "server-managed"
        ):
            await self._token_manager.get_access_token(force_refresh=True)
            retry_headers, _ = await self._build_headers(correlation_id=correlation_id, require_auth=require_auth)
            self._ensure_clients_open()
            active_client = self._health_client if use_health_client else self._client
            response = await active_client.request(
                method,
                path,
                headers=retry_headers,
                params=params,
                json=body,
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _API_METRICS["requestsFailed"] = int(_API_METRICS["requestsFailed"]) + 1
            status_code = response.status_code
            if status_code == 401:
                message = (
                    f"{method} {path} authentication failed (401). "
                    f"auth_source={auth_source or 'none'}"
                )
            elif status_code == 403:
                if path in {"/api/v1/enterprise", "/api/v1/test/enterprise"}:
                    message = (
                        f"{method} {path} authorization failed (403). "
                        f"auth_source={auth_source or 'none'}. "
                        "This endpoint often requires elevated admin permissions. "
                        "If enterprise context is already known, prefer get_enterprise."
                    )
                else:
                    message = (
                        f"{method} {path} authorization failed (403). "
                        f"auth_source={auth_source or 'none'}. "
                        "Token likely lacks required permission or scope for this endpoint."
                    )
            elif status_code >= 500:
                message = f"{method} {path} failed due to upstream server error ({status_code})."
            else:
                message = f"{method} {path} failed with status {status_code}."
            logger.warning("vista_request_failed path=%s status=%s auth_source=%s", path, status_code, auth_source)
            raise RuntimeError(message) from exc
        payload = response.json()
        if not isinstance(payload, dict):
            _API_METRICS["requestsFailed"] = int(_API_METRICS["requestsFailed"]) + 1
            raise RuntimeError(f"{method} {path} returned non-object JSON payload")
        _API_METRICS["requestsSucceeded"] = int(_API_METRICS["requestsSucceeded"]) + 1
        return payload

    @staticmethod
    def _compute_retry_delay(
        attempt: int,
        base_delay: float,
        max_delay: float,
        jitter_window: float,
        *,
        retry_after: str | None = None,
    ) -> float:
        if retry_after:
            try:
                parsed = float(retry_after)
                if parsed >= 0:
                    return min(max_delay, parsed)
            except ValueError:
                pass
        base = min(max_delay, base_delay * (2**attempt))
        jitter = random.uniform(0.0, jitter_window) if jitter_window > 0 else 0.0
        return min(max_delay, base + jitter)

    @staticmethod
    def _build_paged_query_params(
        *,
        order_by: str | None = None,
        order_by_asc: bool | None = None,
        limit: int | None = None,
        page: int | None = None,
        includes: str | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {}
        if order_by is not None:
            params["orderBy"] = order_by
        if order_by_asc is not None:
            params["orderByAsc"] = order_by_asc
        if limit is not None:
            params["limit"] = limit
        if page is not None:
            params["page"] = page
        if includes is not None:
            params["includes"] = includes
        return params or None

    @staticmethod
    def _is_400_runtime_error(exc: RuntimeError) -> bool:
        return "failed with status 400" in str(exc).lower()

    @staticmethod
    def _shrink_limit(limit: int | None) -> int | None:
        """Cap oversized page size when Vista rejects large limits."""
        if limit is None:
            return None
        if limit <= 100:
            return None
        return 100

    async def call_endpoint(
        self,
        endpoint: EndpointSpec,
        *,
        path_params: dict[str, Any] | None = None,
        query_body: dict[str, Any] | None = None,
        bulk_items: list[dict[str, Any]] | None = None,
        includes: str | None = None,
        order_by: str | None = None,
        order_by_asc: bool | None = None,
        limit: int | None = None,
        page: int | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute one registered endpoint with normalized params/body behavior."""

        path = endpoint.path.format(**(path_params or {}))
        params: dict[str, Any] | None = None
        body: dict[str, Any] | None = None

        if endpoint.operation_kind == "get":
            params = {"includes": includes} if includes else None
        elif endpoint.operation_kind == "list":
            params = self._build_paged_query_params(
                order_by=order_by,
                order_by_asc=order_by_asc,
                limit=limit,
                page=page,
                includes=includes,
            )
            body = query_body or {"filters": []}
        elif endpoint.operation_kind == "bulk":
            body = {"items": bulk_items or []}
        elif endpoint.operation_kind == "health":
            return await self._request(
                endpoint.method,
                path,
                require_auth=False,
                use_health_client=True,
                correlation_id=correlation_id,
                allow_transient_retry=True,
            )

        try:
            return await self._request(
                endpoint.method,
                path,
                params=params,
                body=body,
                correlation_id=correlation_id,
                allow_transient_retry=endpoint.operation_kind in {"get", "list"},
            )
        except RuntimeError as exc:
            # Vista occasionally rejects optional query params (includes) or large limits with 400.
            # Retry once with safer params for read-style operations to reduce tool flakiness.
            if not self._is_400_runtime_error(exc) or endpoint.operation_kind not in {"get", "list"}:
                raise

            if endpoint.operation_kind == "get" and includes:
                logger.warning(
                    "vista_400_fallback tool=%s path=%s action=drop_includes includes=%s",
                    endpoint.tool_name,
                    path,
                    includes,
                )
                return await self._request(
                    endpoint.method,
                    path,
                    params=None,
                    body=body,
                    correlation_id=correlation_id,
                    allow_transient_retry=True,
                )

            if endpoint.operation_kind == "list":
                fallback_params = dict(params or {})
                changed = False
                if "includes" in fallback_params:
                    fallback_params.pop("includes", None)
                    changed = True
                capped_limit = self._shrink_limit(limit)
                if capped_limit is not None:
                    fallback_params["limit"] = capped_limit
                    changed = True
                if changed:
                    logger.warning(
                        "vista_400_fallback tool=%s path=%s action=list_param_downgrade original_params=%s fallback_params=%s",
                        endpoint.tool_name,
                        path,
                        params,
                        fallback_params,
                    )
                    return await self._request(
                        endpoint.method,
                        path,
                        params=fallback_params or None,
                        body=body,
                        correlation_id=correlation_id,
                        allow_transient_retry=True,
                    )
            raise

    async def collect_list_pages(
        self,
        endpoint: EndpointSpec,
        *,
        path_params: dict[str, Any] | None = None,
        query_body: dict[str, Any] | None = None,
        includes: str | None = None,
        order_by: str | None = None,
        order_by_asc: bool | None = None,
        page_size: int = 100,
        max_pages: int = 20,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Collect paged list results with partial-result safety."""
        if endpoint.operation_kind != "list":
            raise ValueError("collect_list_pages requires a list endpoint.")

        effective_page_size = max(1, min(page_size, 100))
        effective_max_pages = max(1, max_pages)
        items: list[dict[str, Any]] = []
        pages_fetched = 0
        partial = False
        errors: list[dict[str, Any]] = []

        for page in range(1, effective_max_pages + 1):
            try:
                payload = await self.call_endpoint(
                    endpoint,
                    path_params=path_params,
                    query_body=query_body,
                    includes=includes,
                    order_by=order_by,
                    order_by_asc=order_by_asc,
                    limit=effective_page_size,
                    page=page,
                    correlation_id=correlation_id,
                )
            except RuntimeError as exc:
                partial = True
                _API_METRICS["partialCollections"] = int(_API_METRICS["partialCollections"]) + 1
                errors.append({"page": page, "message": str(exc)})
                break

            page_items = payload.get("items")
            if not isinstance(page_items, list):
                partial = True
                _API_METRICS["partialCollections"] = int(_API_METRICS["partialCollections"]) + 1
                errors.append(
                    {
                        "page": page,
                        "message": "List payload did not contain an items array.",
                    }
                )
                break

            dict_items = [item for item in page_items if isinstance(item, dict)]
            items.extend(dict_items)
            pages_fetched += 1

            if len(page_items) < effective_page_size:
                break

        return {
            "items": items,
            "pagesFetched": pages_fetched,
            "partial": partial,
            "errors": errors,
            "pageSize": effective_page_size,
            "maxPages": effective_max_pages,
        }

    async def get_enterprise(
        self,
        enterprise_id: int,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="get_enterprise",
            method="GET",
            path="/api/v1/{enterpriseId}",
            summary="Get enterprise by id",
            tag="Enterprise Endpoints",
            operation_kind="get",
            response_schema_ref="#/components/schemas/EnterpriseRecordGetItemResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id},
            includes=includes,
            correlation_id=correlation_id,
        )

    async def list_enterprises(
        self,
        query: dict[str, Any],
        *,
        order_by: str | None,
        order_by_asc: bool | None,
        limit: int | None,
        page: int | None,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="list_enterprises",
            method="POST",
            path="/api/v1/enterprise",
            summary="List enterprises",
            tag="Enterprise Endpoints",
            operation_kind="list",
            response_schema_ref="#/components/schemas/EnterpriseRecordListPagedResponse",
        )
        return await self.call_endpoint(
            endpoint,
            query_body=query,
            order_by=order_by,
            order_by_asc=order_by_asc,
            limit=limit,
            page=page,
            includes=includes,
            correlation_id=correlation_id,
        )

    async def test_list_enterprises(
        self,
        query: dict[str, Any],
        *,
        order_by: str | None,
        order_by_asc: bool | None,
        limit: int | None,
        page: int | None,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="test_list_enterprises",
            method="POST",
            path="/api/v1/test/enterprise",
            summary="Test list enterprises",
            tag="Enterprise Endpoints",
            operation_kind="list",
            response_schema_ref="#/components/schemas/EnterpriseRecordListPagedResponse",
        )
        return await self.call_endpoint(
            endpoint,
            query_body=query,
            order_by=order_by,
            order_by_asc=order_by_asc,
            limit=limit,
            page=page,
            includes=includes,
            correlation_id=correlation_id,
        )

    async def create_unapproved_invoices(
        self,
        enterprise_id: int,
        body: dict[str, Any],
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="create_unapproved_invoices",
            method="POST",
            path="/api/v1/{enterpriseId}/ap/unapprovedinvoice",
            summary="Create unapproved invoices",
            tag="Unapproved Invoice Endpoints",
            operation_kind="bulk",
            response_schema_ref="#/components/schemas/UnapprovedInvoiceActionRecordBulkApiActionResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id},
            bulk_items=body.get("items", []),
            correlation_id=correlation_id,
        )

    async def get_unapproved_invoice(
        self,
        enterprise_id: int,
        invoice_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="get_unapproved_invoice",
            method="GET",
            path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/{id}",
            summary="Get unapproved invoice",
            tag="Unapproved Invoice Endpoints",
            operation_kind="get",
            response_schema_ref="#/components/schemas/UnapprovedInvoiceRecordGetItemResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id, "id": invoice_id},
            includes=includes,
            correlation_id=correlation_id,
        )

    async def get_unapproved_invoice_action(
        self,
        enterprise_id: int,
        invoice_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="get_unapproved_invoice_action",
            method="GET",
            path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/action/{id}",
            summary="Get unapproved invoice action",
            tag="Unapproved Invoice Endpoints",
            operation_kind="get",
            response_schema_ref="#/components/schemas/UnapprovedInvoiceActionRecordGetItemResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id, "id": invoice_id},
            includes=includes,
            correlation_id=correlation_id,
        )

    async def query_unapproved_invoices(
        self,
        enterprise_id: int,
        query: dict[str, Any],
        *,
        order_by: str | None,
        order_by_asc: bool | None,
        limit: int | None,
        page: int | None,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="query_unapproved_invoices",
            method="POST",
            path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/query",
            summary="Query unapproved invoices",
            tag="Unapproved Invoice Endpoints",
            operation_kind="list",
            response_schema_ref="#/components/schemas/UnapprovedInvoiceRecordListPagedResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id},
            query_body=query,
            order_by=order_by,
            order_by_asc=order_by_asc,
            limit=limit,
            page=page,
            includes=includes,
            correlation_id=correlation_id,
        )

    async def get_project(
        self,
        enterprise_id: int,
        project_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="get_project",
            method="GET",
            path="/api/v1/{enterpriseId}/project/{id}",
            summary="Get project",
            tag="Project Endpoints",
            operation_kind="get",
            response_schema_ref="#/components/schemas/ProjectRecordGetItemResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id, "id": project_id},
            includes=includes,
            correlation_id=correlation_id,
        )

    async def list_projects(
        self,
        enterprise_id: int,
        query: dict[str, Any],
        *,
        order_by: str | None,
        order_by_asc: bool | None,
        limit: int | None,
        page: int | None,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="list_projects",
            method="POST",
            path="/api/v1/{enterpriseId}/project",
            summary="List projects",
            tag="Project Endpoints",
            operation_kind="list",
            response_schema_ref="#/components/schemas/ProjectRecordListPagedResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id},
            query_body=query,
            order_by=order_by,
            order_by_asc=order_by_asc,
            limit=limit,
            page=page,
            includes=includes,
            correlation_id=correlation_id,
        )

    async def get_vendor(
        self,
        enterprise_id: int,
        vendor_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="get_vendor",
            method="GET",
            path="/api/v1/{enterpriseId}/vendor/{id}",
            summary="Get vendor",
            tag="Vendor Endpoints",
            operation_kind="get",
            response_schema_ref="#/components/schemas/VendorRecordGetItemResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id, "id": vendor_id},
            includes=includes,
            correlation_id=correlation_id,
        )

    async def list_vendors(
        self,
        enterprise_id: int,
        query: dict[str, Any],
        *,
        order_by: str | None,
        order_by_asc: bool | None,
        limit: int | None,
        page: int | None,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        endpoint = EndpointSpec(
            tool_name="list_vendors",
            method="POST",
            path="/api/v1/{enterpriseId}/vendor",
            summary="List vendors",
            tag="Vendor Endpoints",
            operation_kind="list",
            response_schema_ref="#/components/schemas/VendorRecordListPagedResponse",
            requires_enterprise_id=True,
        )
        return await self.call_endpoint(
            endpoint,
            path_params={"enterpriseId": enterprise_id},
            query_body=query,
            order_by=order_by,
            order_by_asc=order_by_asc,
            limit=limit,
            page=page,
            includes=includes,
            correlation_id=correlation_id,
        )

    async def health_ready(self) -> dict[str, Any]:
        return await self._request("GET", "/health/ready", require_auth=False, use_health_client=True)

    async def health_alive(self) -> dict[str, Any]:
        return await self._request("GET", "/health/alive", require_auth=False, use_health_client=True)

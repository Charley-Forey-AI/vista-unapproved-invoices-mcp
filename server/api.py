"""HTTP API client for Vista endpoints used by MCP tools."""

from __future__ import annotations

import contextvars
from typing import Any

import httpx

from .config import VistaSettings
from .token_manager import TidTokenManager


class VistaApiClient:
    """Thin async client wrapper for Vista REST API calls."""

    def __init__(self, settings: VistaSettings, token_manager: TidTokenManager | None = None):
        self._settings = settings
        self._token_manager = token_manager
        self._api_base_url = str(settings.api_base_url).rstrip("/")
        health_base = settings.health_base_url or settings.api_base_url
        self._health_base_url = str(health_base).rstrip("/")
        self._timeout = settings.request_timeout_seconds
        self._client = httpx.AsyncClient(base_url=self._api_base_url, timeout=self._timeout)
        self._health_client = httpx.AsyncClient(base_url=self._health_base_url, timeout=self._timeout)
        self._request_bearer_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "vista_request_bearer_token", default=None
        )

    async def close(self) -> None:
        """Close underlying HTTP client resources."""

        await self._client.aclose()
        await self._health_client.aclose()

    def _ensure_clients_open(self) -> None:
        if self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self._api_base_url, timeout=self._timeout)
        if self._health_client.is_closed:
            self._health_client = httpx.AsyncClient(base_url=self._health_base_url, timeout=self._timeout)

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
            if request_bearer:
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
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        self._ensure_clients_open()
        headers, auth_source = await self._build_headers(
            correlation_id=correlation_id,
            require_auth=require_auth,
        )
        active_client = client or self._client
        response = await active_client.request(method, path, headers=headers, params=params, json=body)

        if (
            response.status_code == 401
            and require_auth
            and self._token_manager is not None
            and auth_source == "server-managed"
        ):
            await self._token_manager.get_access_token(force_refresh=True)
            retry_headers, _ = await self._build_headers(correlation_id=correlation_id, require_auth=require_auth)
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
            status_code = response.status_code
            if status_code == 401:
                message = f"{method} {path} authentication failed (401)."
            elif status_code == 403:
                message = f"{method} {path} authorization failed (403)."
            elif status_code >= 500:
                message = f"{method} {path} failed due to upstream server error ({status_code})."
            else:
                message = f"{method} {path} failed with status {status_code}."
            raise RuntimeError(message) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{method} {path} failed due to network error.") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{method} {path} returned non-object JSON payload")
        return payload

    async def get_enterprise(
        self,
        enterprise_id: int,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/{enterprise_id}",
            params={"includes": includes} if includes else None,
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

        return await self._request(
            "POST",
            "/api/v1/enterprise",
            params=params or None,
            body=query,
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

        return await self._request(
            "POST",
            "/api/v1/test/enterprise",
            params=params or None,
            body=query,
            correlation_id=correlation_id,
        )

    async def create_unapproved_invoices(
        self,
        enterprise_id: int,
        body: dict[str, Any],
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/v1/{enterprise_id}/ap/unapprovedinvoice",
            body=body,
            correlation_id=correlation_id,
        )

    async def get_unapproved_invoice(
        self,
        enterprise_id: int,
        invoice_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/{enterprise_id}/ap/unapprovedinvoice/{invoice_id}",
            params={"includes": includes} if includes else None,
            correlation_id=correlation_id,
        )

    async def get_unapproved_invoice_action(
        self,
        enterprise_id: int,
        invoice_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/{enterprise_id}/ap/unapprovedinvoice/action/{invoice_id}",
            params={"includes": includes} if includes else None,
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

        return await self._request(
            "POST",
            f"/api/v1/{enterprise_id}/ap/unapprovedinvoice/query",
            params=params or None,
            body=query,
            correlation_id=correlation_id,
        )

    async def get_project(
        self,
        enterprise_id: int,
        project_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/{enterprise_id}/project/{project_id}",
            params={"includes": includes} if includes else None,
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

        return await self._request(
            "POST",
            f"/api/v1/{enterprise_id}/project",
            params=params or None,
            body=query,
            correlation_id=correlation_id,
        )

    async def get_vendor(
        self,
        enterprise_id: int,
        vendor_id: str,
        includes: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/{enterprise_id}/vendor/{vendor_id}",
            params={"includes": includes} if includes else None,
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

        return await self._request(
            "POST",
            f"/api/v1/{enterprise_id}/vendor",
            params=params or None,
            body=query,
            correlation_id=correlation_id,
        )

    async def health_ready(self) -> dict[str, Any]:
        return await self._request("GET", "/health/ready", require_auth=False, client=self._health_client)

    async def health_alive(self) -> dict[str, Any]:
        return await self._request("GET", "/health/alive", require_auth=False, client=self._health_client)

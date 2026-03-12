"""HTTP API client for Vista endpoints used by MCP tools."""

from __future__ import annotations

from typing import Any

import httpx

from .config import VistaSettings


class VistaApiClient:
    """Thin async client wrapper for Vista REST API calls."""

    def __init__(self, settings: VistaSettings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.api_base_url).rstrip("/"),
            timeout=settings.request_timeout_seconds,
        )
        health_base = settings.health_base_url or settings.api_base_url
        self._health_client = httpx.AsyncClient(
            base_url=str(health_base).rstrip("/"),
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        """Close underlying HTTP client resources."""

        await self._client.aclose()
        await self._health_client.aclose()

    def _build_headers(
        self,
        correlation_id: str | None = None,
        *,
        require_auth: bool = True,
    ) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}

        if self._settings.bearer_token:
            headers["Authorization"] = f"Bearer {self._settings.bearer_token}"
        elif self._settings.api_key:
            headers[self._settings.api_key_header] = self._settings.api_key
        elif require_auth:
            raise ValueError(
                "No authentication configured. Set VISTA_BEARER_TOKEN or VISTA_API_KEY in your environment."
            )

        effective_correlation = correlation_id or self._settings.correlation_id
        if effective_correlation:
            headers["x-correlation-id"] = effective_correlation

        return headers

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
        headers = self._build_headers(correlation_id=correlation_id, require_auth=require_auth)
        active_client = client or self._client
        response = await active_client.request(method, path, headers=headers, params=params, json=body)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:1200]
            raise RuntimeError(f"{method} {path} failed with status {response.status_code}: {detail}") from exc

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

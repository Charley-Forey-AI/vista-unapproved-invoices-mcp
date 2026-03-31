"""Factory for registering Vista endpoint tools from registry metadata."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import UUID

from pydantic import Field, ValidationError

from .api import VistaApiClient
from .endpoint_registry import ANALYSIS_BY_TOOL, ENDPOINTS_BY_TOOL, EndpointSpec, iter_enabled_endpoints
from .generated_models import model_for_response_schema, request_model_for_schema
from .models import QueryFilter, QueryRequest
from .normalization import normalize_payload
from .openapi_intelligence import required_fields_for_request_schema
from .services.analysis_runs import AnalysisRunStore, decode_offset_cursor, encode_offset_cursor
from .services.analysis_cache import AnalysisCache
from .services.invoice_analysis import AnalysisConfig, analyze_invoices

logger = logging.getLogger(__name__)
_TOOL_METRICS: dict[str, dict[str, float | int]] = {}
_ANALYSIS_METRICS: dict[str, float | int] = {
    "runsCreated": 0,
    "cacheHits": 0,
    "cacheMisses": 0,
    "incrementalRuns": 0,
    "partialResponses": 0,
    "partialFailures": 0,
    "strictPartialFailures": 0,
    "degradedResponses": 0,
}
_RUN_STORE = AnalysisRunStore(ttl_seconds=7200)
_ANALYSIS_CACHE_BACKEND: AnalysisCache | None = None
_ANALYSIS_CACHE_BACKEND_KEY: str | None = None
_ANALYSIS_RUN_SEMAPHORE: asyncio.Semaphore | None = None
_ANALYSIS_RUN_SEMAPHORE_LIMIT: int | None = None
_ANALYSIS_ENTERPRISE_BULKHEADS: dict[int, asyncio.Semaphore] = {}
_ANALYSIS_ENTERPRISE_BULKHEADS_LOCK = asyncio.Lock()


def _to_json(data: object) -> str:
    return json.dumps(data, indent=2, default=str)


def _compact_analysis_payload(
    analysis: dict[str, Any],
    *,
    max_items_per_bucket: int,
    max_vendor_groups: int,
) -> dict[str, Any]:
    approve_candidates = analysis.get("approveCandidates", [])
    needs_correction = analysis.get("needsCorrection", [])
    needs_investigation = analysis.get("needsInvestigation", [])
    vendor_groups = analysis.get("vendorGroups", [])

    if not isinstance(approve_candidates, list):
        approve_candidates = []
    if not isinstance(needs_correction, list):
        needs_correction = []
    if not isinstance(needs_investigation, list):
        needs_investigation = []
    if not isinstance(vendor_groups, list):
        vendor_groups = []

    safe_bucket_limit = max(1, max_items_per_bucket)
    safe_vendor_limit = max(1, max_vendor_groups)

    return {
        "run": analysis.get("run", {}),
        "window": analysis.get("window", {}),
        "runHints": analysis.get("runHints", {}),
        "riskModel": analysis.get("riskModel", {}),
        "totals": analysis.get("totals", {}),
        "collection": analysis.get("collection", {}),
        "topRisks": analysis.get("topRisks", []),
        "vendorGroups": vendor_groups[:safe_vendor_limit],
        "vendorGroupsMeta": {
            "total": len(vendor_groups),
            "returned": min(len(vendor_groups), safe_vendor_limit),
            "truncated": len(vendor_groups) > safe_vendor_limit,
        },
        "reviewQueues": {
            "approveCandidates": {
                "total": len(approve_candidates),
                "sample": approve_candidates[:safe_bucket_limit],
                "sampleTruncated": len(approve_candidates) > safe_bucket_limit,
            },
            "needsCorrection": {
                "total": len(needs_correction),
                "sample": needs_correction[:safe_bucket_limit],
                "sampleTruncated": len(needs_correction) > safe_bucket_limit,
            },
            "needsInvestigation": {
                "total": len(needs_investigation),
                "sample": needs_investigation[:safe_bucket_limit],
                "sampleTruncated": len(needs_investigation) > safe_bucket_limit,
            },
        },
        "notes": [
            "Use detail_level=full to return every invoice in each review queue.",
            "Default compact output prevents oversized responses for large backlogs.",
        ],
    }


def _build_queue_views(analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    queues = {
        "approve_candidates": analysis.get("approveCandidates", []),
        "needs_correction": analysis.get("needsCorrection", []),
        "needs_investigation": analysis.get("needsInvestigation", []),
    }
    normalized: dict[str, list[dict[str, Any]]] = {}
    for queue_name, items in queues.items():
        if not isinstance(items, list):
            normalized[queue_name] = []
            continue
        sorted_items = [item for item in items if isinstance(item, dict)]
        sorted_items.sort(
            key=lambda item: (
                int(item.get("riskScore") or 0),
                float(item.get("invoiceAmount") or 0.0),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        normalized[queue_name] = sorted_items
    return normalized


def _find_invoice(analysis: dict[str, Any], invoice_id: str) -> dict[str, Any] | None:
    for queue_items in _build_queue_views(analysis).values():
        for item in queue_items:
            if str(item.get("id") or "") == invoice_id:
                return item
    return None


def _cache_key(*, enterprise_id: int, window_days: int, page_size: int, max_pages: int, policy_profile: str) -> str:
    return "|".join(
        [
            str(enterprise_id),
            str(window_days),
            str(page_size),
            str(max_pages),
            policy_profile.strip().lower(),
        ]
    )


def _cache_backend_for_settings(settings: Any) -> AnalysisCache:
    global _ANALYSIS_CACHE_BACKEND
    global _ANALYSIS_CACHE_BACKEND_KEY

    backend_key = "|".join(
        [
            str(settings.analysis_cache_backend),
            str(settings.redis_url or ""),
            str(settings.analysis_cache_prefix),
            str(settings.analysis_cache_ttl_seconds),
        ]
    )
    if _ANALYSIS_CACHE_BACKEND is None or _ANALYSIS_CACHE_BACKEND_KEY != backend_key:
        _ANALYSIS_CACHE_BACKEND = AnalysisCache(
            backend=settings.analysis_cache_backend,
            ttl_seconds=settings.analysis_cache_ttl_seconds,
            redis_url=settings.redis_url,
            key_prefix=settings.analysis_cache_prefix,
        )
        _ANALYSIS_CACHE_BACKEND_KEY = backend_key
    return _ANALYSIS_CACHE_BACKEND


def _analysis_run_bulkhead(settings: Any) -> asyncio.Semaphore:
    global _ANALYSIS_RUN_SEMAPHORE
    global _ANALYSIS_RUN_SEMAPHORE_LIMIT
    desired = max(1, int(settings.max_concurrent_analysis_runs))
    if _ANALYSIS_RUN_SEMAPHORE is None or _ANALYSIS_RUN_SEMAPHORE_LIMIT != desired:
        _ANALYSIS_RUN_SEMAPHORE = asyncio.Semaphore(desired)
        _ANALYSIS_RUN_SEMAPHORE_LIMIT = desired
    return _ANALYSIS_RUN_SEMAPHORE


async def _enterprise_bulkhead(enterprise_id: int, settings: Any) -> asyncio.Semaphore:
    limit = max(1, int(settings.max_concurrent_analysis_runs))
    async with _ANALYSIS_ENTERPRISE_BULKHEADS_LOCK:
        existing = _ANALYSIS_ENTERPRISE_BULKHEADS.get(enterprise_id)
        if existing is not None:
            return existing
        created = asyncio.Semaphore(limit)
        _ANALYSIS_ENTERPRISE_BULKHEADS[enterprise_id] = created
        return created


def _parse_analysis_as_of(as_of_date: str | None) -> datetime | None:
    if isinstance(as_of_date, str) and as_of_date.strip():
        parsed = datetime.fromisoformat(as_of_date)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _queue_page(
    *,
    queue_items: list[dict[str, Any]],
    cursor: str | None,
    page_size: int,
) -> dict[str, Any]:
    effective_page_size = max(1, min(page_size, 100))
    start = decode_offset_cursor(cursor if isinstance(cursor, str) else None)
    end = start + effective_page_size
    page_items = queue_items[start:end]
    has_more = end < len(queue_items)
    return {
        "items": page_items,
        "nextCursor": encode_offset_cursor(end) if has_more else None,
        "hasMore": has_more,
        "pageSize": effective_page_size,
        "offset": start,
        "returned": len(page_items),
    }


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


def normalize_bulk_items(
    items: list[dict[str, Any]] | dict[str, Any],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    if isinstance(items, list):
        normalized = [dict(item) for item in items]
    else:
        normalized = [dict(items)]
    if not normalized:
        raise ValueError("At least one item is required.")
    if len(normalized) > max_items:
        raise ValueError(f"Bulk request exceeds max_items={max_items}. Split into smaller batches.")
    return normalized


def _description_for_endpoint(spec: EndpointSpec) -> str:
    required_fields = required_fields_for_request_schema(spec.request_schema_ref)
    required_inputs = list(spec.required_inputs) or required_fields
    lines = [spec.summary]
    lines.append(f"Operation: {spec.method} {spec.path}")
    if spec.requires_enterprise_id:
        lines.append("Requires: enterprise_id (argument or VISTA_ENTERPRISE_ID)")
    if required_inputs:
        lines.append("Required inputs: " + ", ".join(required_inputs))
    if spec.produced_fields:
        lines.append("Produces: " + ", ".join(spec.produced_fields))
    if spec.recommended_prerequisites:
        lines.append("Recommended prerequisites: " + " -> ".join(spec.recommended_prerequisites))
    if spec.operation_kind == "bulk":
        lines.append("Supports dry_run for validation-only preflight.")
    return " ".join(lines)


def register_endpoint_tools(
    mcp: Any,
    settings: Any,
    api: VistaApiClient,
    delegated_mode: bool,
    require_request_token: bool,
    get_request_token: Callable[[], str | None],
    resolve_enterprise_id: Callable[[int | None], int],
) -> None:
    """Register endpoint tools using shared signatures by operation kind."""

    def _record_metric(tool_name: str, *, success: bool, elapsed_ms: float) -> None:
        metrics = _TOOL_METRICS.setdefault(
            tool_name,
            {"calls": 0, "successes": 0, "failures": 0, "total_latency_ms": 0.0},
        )
        metrics["calls"] = int(metrics["calls"]) + 1
        metrics["total_latency_ms"] = float(metrics["total_latency_ms"]) + elapsed_ms
        if success:
            metrics["successes"] = int(metrics["successes"]) + 1
        else:
            metrics["failures"] = int(metrics["failures"]) + 1

    async def with_tool_error_logging(
        tool_name: str,
        operation: Callable[[], Awaitable[str]],
        *,
        endpoint: EndpointSpec | None = None,
        enterprise_id: int | None = None,
        correlation_id: str | None = None,
    ) -> str:
        started = time.perf_counter()
        request_token = get_request_token() if delegated_mode else None
        if require_request_token and not request_token:
            raise RuntimeError(
                "Delegated actor token was not found in the MCP request context. "
                "Ensure Agent Studio sends an On behalf of actor token."
            )
        reset_token = api.set_request_bearer_token(request_token)
        try:
            result = await operation()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _record_metric(tool_name, success=True, elapsed_ms=elapsed_ms)
            logger.info(
                "tool_call",
                extra={
                    "tool_name": tool_name,
                    "status": "success",
                    "latency_ms": round(elapsed_ms, 2),
                    "endpoint_path": endpoint.path if endpoint else None,
                    "enterprise_id": enterprise_id,
                    "correlation_id": correlation_id,
                },
            )
            return result
        except RuntimeError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _record_metric(tool_name, success=False, elapsed_ms=elapsed_ms)
            message = str(exc)
            if "authorization failed (403)" in message or "authentication failed (401)" in message:
                logger.warning("Tool failed: %s | %s", tool_name, message)
            else:
                logger.exception("Tool failed: %s", tool_name)
            raise
        except (ValueError, ValidationError):
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _record_metric(tool_name, success=False, elapsed_ms=elapsed_ms)
            logger.exception("Tool failed: %s", tool_name)
            raise
        finally:
            api.reset_request_bearer_token(reset_token)

    def _validate_response(spec: EndpointSpec, payload: dict[str, Any]) -> dict[str, Any]:
        model = model_for_response_schema(spec.response_schema_ref)
        parsed = model.model_validate(payload)
        return parsed.model_dump(by_alias=True, exclude_none=True)

    def _check_bulk_policy(spec: EndpointSpec) -> list[str]:
        issues: list[str] = []
        if settings.read_only_mode:
            issues.append("Write tools are disabled by read_only_mode (VISTA_READ_ONLY_MODE).")
        allowed_domains = settings.normalized_write_domains()
        if allowed_domains and (spec.write_domain or "") not in allowed_domains:
            issues.append(f"Write domain '{spec.write_domain}' is not enabled. Allowed: {sorted(allowed_domains)}")
        return issues

    def _serialize_output(spec: EndpointSpec, raw_payload: dict[str, Any], output_mode: str) -> str:
        if output_mode == "raw":
            return _to_json(raw_payload)
        normalized = normalize_payload(raw_payload, tool_name=spec.tool_name, schema_ref=spec.response_schema_ref)
        if output_mode == "normalized":
            return _to_json(normalized)
        if output_mode == "both":
            return _to_json({"raw": raw_payload, "normalized": normalized})
        raise ValueError("output must be one of: raw, normalized, both.")

    def _serialize_custom_output(
        *,
        tool_name: str,
        raw_payload: dict[str, Any],
        output_mode: str,
    ) -> str:
        if output_mode == "raw":
            return _to_json(raw_payload)
        normalized = normalize_payload(raw_payload, tool_name=tool_name, schema_ref=None)
        if output_mode == "normalized":
            return _to_json(normalized)
        if output_mode == "both":
            return _to_json({"raw": raw_payload, "normalized": normalized})
        raise ValueError("output must be one of: raw, normalized, both.")

    def _register_get_tool(spec: EndpointSpec) -> None:
        description = _description_for_endpoint(spec)
        if spec.path == "/api/v1/{enterpriseId}":
            async def tool(
                enterprise_id: int | None = Field(
                    default=None,
                    description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
                ),
                includes: str | None = Field(default=None, description="Optional includes query value."),
                correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
                output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
            ) -> str:
                async def run() -> str:
                    resolved_enterprise = resolve_enterprise_id(enterprise_id)
                    payload = await api.call_endpoint(
                        spec,
                        path_params={"enterpriseId": resolved_enterprise},
                        includes=includes,
                        correlation_id=correlation_id,
                    )
                    return _serialize_output(spec, _validate_response(spec, payload), output)

                return await with_tool_error_logging(
                    spec.tool_name,
                    run,
                    endpoint=spec,
                    enterprise_id=enterprise_id,
                    correlation_id=correlation_id,
                )
        else:
            async def tool(
                id: UUID | str | int = Field(description="Record id for this endpoint."),
                enterprise_id: int | None = Field(
                    default=None,
                    description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
                ),
                includes: str | None = Field(default=None, description="Optional includes query value."),
                correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
                output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
            ) -> str:
                async def run() -> str:
                    path_params: dict[str, Any] = {"id": str(id)}
                    if spec.requires_enterprise_id:
                        path_params["enterpriseId"] = resolve_enterprise_id(enterprise_id)
                    payload = await api.call_endpoint(
                        spec,
                        path_params=path_params,
                        includes=includes,
                        correlation_id=correlation_id,
                    )
                    return _serialize_output(spec, _validate_response(spec, payload), output)

                return await with_tool_error_logging(
                    spec.tool_name,
                    run,
                    endpoint=spec,
                    enterprise_id=enterprise_id,
                    correlation_id=correlation_id,
                )

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=description)(tool)

    def _register_list_tool(spec: EndpointSpec) -> None:
        description = _description_for_endpoint(spec)
        async def tool(
            enterprise_id: int | None = Field(
                default=None,
                description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
            ),
            filters: list[QueryFilter | dict[str, Any]] | dict[str, Any] | None = Field(
                default=None,
                description="Optional filters: [{field, operator, values[]}].",
            ),
            order_by: str | None = Field(default=None, description="Optional orderBy query value."),
            order_by_asc: bool | None = Field(default=None, description="Optional orderByAsc query value."),
            limit: int | None = Field(default=None, description="Optional page size."),
            page: int | None = Field(default=None, description="Optional page index."),
            includes: str | None = Field(default=None, description="Optional includes query value."),
            correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                query = build_query(filters)
                request_model = request_model_for_schema(spec.request_schema_ref)
                body = query.model_dump(by_alias=True, exclude_none=True)
                if request_model is not None:
                    body = request_model.model_validate(body).model_dump(by_alias=True, exclude_none=True)
                path_params: dict[str, Any] = {}
                if spec.requires_enterprise_id:
                    path_params["enterpriseId"] = resolve_enterprise_id(enterprise_id)
                try:
                    payload = await api.call_endpoint(
                        spec,
                        path_params=path_params or None,
                        query_body=body,
                        order_by=order_by,
                        order_by_asc=order_by_asc,
                        limit=limit,
                        page=page,
                        includes=includes,
                        correlation_id=correlation_id,
                    )
                except RuntimeError as exc:
                    message = str(exc)
                    if (
                        spec.tool_name in {"list_enterprises", "test_list_enterprises"}
                        and "authorization failed (403)" in message
                        and settings.enterprise_id is not None
                    ):
                        # Fallback for non-admin actors: return the configured enterprise as one-item list.
                        enterprise_spec = ENDPOINTS_BY_TOOL["get_enterprise"]
                        fallback_payload = await api.call_endpoint(
                            enterprise_spec,
                            path_params={"enterpriseId": settings.enterprise_id},
                            includes=includes,
                            correlation_id=correlation_id,
                        )
                        fallback_item = fallback_payload.get("item")
                        payload = {
                            "items": [fallback_item] if fallback_item else [],
                            "pageSize": 1 if fallback_item else 0,
                            "currentPage": 1,
                            "fallback": {
                                "reason": "list_enterprises_forbidden",
                                "usedEnterpriseId": settings.enterprise_id,
                            },
                        }
                    else:
                        raise
                return _serialize_output(spec, _validate_response(spec, payload), output)

            return await with_tool_error_logging(
                spec.tool_name,
                run,
                endpoint=spec,
                enterprise_id=enterprise_id,
                correlation_id=correlation_id,
            )

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=description)(tool)

    def _register_bulk_tool(spec: EndpointSpec) -> None:
        description = _description_for_endpoint(spec)
        async def tool(
            items: list[dict[str, Any]] | dict[str, Any] = Field(
                description="Bulk request items for this endpoint."
            ),
            enterprise_id: int | None = Field(
                default=None,
                description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
            ),
            correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
            dry_run: bool = Field(
                default=False,
                description="Validate and preview payload only without writing to Vista.",
            ),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                policy_issues = _check_bulk_policy(spec)
                if policy_issues:
                    raise ValueError("; ".join(policy_issues))
                normalized_items = normalize_bulk_items(items, max_items=settings.effective_max_batch_size())
                request_model = request_model_for_schema(spec.request_schema_ref)
                body = {"items": normalized_items}
                if request_model is not None:
                    body = request_model.model_validate(body).model_dump(by_alias=True, exclude_none=True)
                if dry_run:
                    preview = {
                        "dryRun": True,
                        "tool": spec.tool_name,
                        "validatedItemCount": len(body.get("items", [])),
                        "requiredInputs": list(spec.required_inputs),
                        "writeDomain": spec.write_domain,
                    }
                    return _serialize_output(spec, preview, output)
                path_params: dict[str, Any] = {}
                if spec.requires_enterprise_id:
                    path_params["enterpriseId"] = resolve_enterprise_id(enterprise_id)
                payload = await api.call_endpoint(
                    spec,
                    path_params=path_params or None,
                    bulk_items=body.get("items", []),
                    correlation_id=correlation_id,
                )
                return _serialize_output(spec, _validate_response(spec, payload), output)

            return await with_tool_error_logging(
                spec.tool_name,
                run,
                endpoint=spec,
                enterprise_id=enterprise_id,
                correlation_id=correlation_id,
            )

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=description)(tool)

    def _register_bulk_preflight_tool(spec: EndpointSpec) -> None:
        preflight_name = f"validate_{spec.tool_name}_request"
        required_fields = required_fields_for_request_schema(spec.request_schema_ref)
        description = (
            f"Preflight validator for {spec.tool_name}. "
            "Validates payload shape, required fields, write policy, and enterprise context without calling Vista."
        )

        async def tool(
            items: list[dict[str, Any]] | dict[str, Any] = Field(
                description="Bulk request items to validate."
            ),
            enterprise_id: int | None = Field(
                default=None,
                description="Enterprise id for scoped write tools.",
            ),
        ) -> str:
            async def run() -> str:
                issues: list[dict[str, Any]] = []
                policy_issues = _check_bulk_policy(spec)
                for message in policy_issues:
                    issues.append({"type": "policy", "message": message})

                resolved_enterprise_id: int | None = None
                if spec.requires_enterprise_id:
                    try:
                        resolved_enterprise_id = resolve_enterprise_id(enterprise_id)
                    except ValueError as exc:
                        issues.append({"type": "dependency", "message": str(exc)})

                try:
                    normalized_items = normalize_bulk_items(items, max_items=settings.effective_max_batch_size())
                except ValueError as exc:
                    issues.append({"type": "shape", "message": str(exc)})
                    normalized_items = []

                request_model = request_model_for_schema(spec.request_schema_ref)
                if request_model is not None and normalized_items:
                    try:
                        request_model.model_validate({"items": normalized_items})
                    except ValidationError as exc:
                        for error in exc.errors():
                            issues.append({"type": "validation", "message": error.get("msg"), "loc": error.get("loc")})

                for index, item in enumerate(normalized_items):
                    for field in required_fields:
                        if not field.startswith("items[]."):
                            continue
                        key = field.replace("items[].", "", 1)
                        if item.get(key) is None:
                            issues.append(
                                {
                                    "type": "missing_required_input",
                                    "message": f"Missing {field}",
                                    "item_index": index,
                                }
                            )

                return _to_json(
                    {
                        "tool": spec.tool_name,
                        "preflightTool": preflight_name,
                        "valid": len(issues) == 0,
                        "issueCount": len(issues),
                        "issues": issues,
                        "requiredInputs": list(spec.required_inputs) or required_fields,
                        "validatedItemCount": len(normalized_items),
                        "resolvedEnterpriseId": resolved_enterprise_id,
                        "canExecute": len(issues) == 0,
                    }
                )

            return await with_tool_error_logging(preflight_name, run, endpoint=spec, enterprise_id=enterprise_id)

        tool.__name__ = preflight_name
        tool.__doc__ = description
        mcp.tool(description=description)(tool)

    def _register_health_tool(spec: EndpointSpec) -> None:
        description = _description_for_endpoint(spec)
        async def tool(
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                payload = await api.call_endpoint(spec)
                return _serialize_output(spec, _validate_response(spec, payload), output)

            return await with_tool_error_logging(spec.tool_name, run, endpoint=spec)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=description)(tool)

    async def _build_analysis_report(
        *,
        enterprise_id: int,
        window_days: int | None,
        top_n: int | None,
        page_size: int | None,
        max_pages: int | None,
        as_of_date: str | None,
        policy_profile: str | None,
        correlation_id: str | None,
        incremental_since: str | None,
        use_cache: bool,
        require_complete: bool,
    ) -> dict[str, Any]:
        list_spec = ENDPOINTS_BY_TOOL["query_unapproved_invoices"]
        resolved_page_size = page_size if isinstance(page_size, int) else settings.analysis_page_size
        resolved_max_pages = max_pages if isinstance(max_pages, int) else settings.analysis_max_pages
        configured_window = window_days if isinstance(window_days, int) else settings.analysis_default_window_days
        configured_top_n = top_n if isinstance(top_n, int) else settings.analysis_default_top_n
        profile_name = (
            policy_profile.strip().lower()
            if isinstance(policy_profile, str) and policy_profile.strip()
            else settings.analysis_policy_profile
        )

        cache_key = _cache_key(
            enterprise_id=enterprise_id,
            window_days=max(1, configured_window),
            page_size=max(1, resolved_page_size),
            max_pages=max(1, resolved_max_pages),
            policy_profile=profile_name,
        )
        cache_backend = _cache_backend_for_settings(settings)
        if use_cache:
            cached = await cache_backend.get(cache_key)
            if cached is not None:
                _ANALYSIS_METRICS["cacheHits"] = int(_ANALYSIS_METRICS["cacheHits"]) + 1
                return dict(cached)
            _ANALYSIS_METRICS["cacheMisses"] = int(_ANALYSIS_METRICS["cacheMisses"]) + 1

        async def compute_analysis() -> dict[str, Any]:
            body = {"filters": []}
            run_bulkhead = _analysis_run_bulkhead(settings)
            enterprise_bulkhead = await _enterprise_bulkhead(enterprise_id, settings)
            async with run_bulkhead:
                async with enterprise_bulkhead:
                    collection = await api.collect_list_pages(
                        list_spec,
                        path_params={"enterpriseId": enterprise_id},
                        query_body=body,
                        # Force recent-first paging so window filtering sees relevant invoices early.
                        order_by="lastUpdateDateUtc",
                        order_by_asc=False,
                        page_size=max(1, resolved_page_size),
                        max_pages=max(1, resolved_max_pages),
                        correlation_id=correlation_id,
                    )
            if collection["partial"]:
                _ANALYSIS_METRICS["partialResponses"] = int(_ANALYSIS_METRICS["partialResponses"]) + 1
                if require_complete:
                    _ANALYSIS_METRICS["partialFailures"] = int(_ANALYSIS_METRICS["partialFailures"]) + 1
                    _ANALYSIS_METRICS["strictPartialFailures"] = int(_ANALYSIS_METRICS["strictPartialFailures"]) + 1
                    raise RuntimeError(
                        "Analysis collection returned partial results. "
                        "Retry later or set require_complete=false to allow degraded responses."
                    )

            items = collection["items"]
            if isinstance(incremental_since, str) and incremental_since.strip():
                cutoff = _parse_analysis_as_of(incremental_since)
                if cutoff is not None:
                    _ANALYSIS_METRICS["incrementalRuns"] = int(_ANALYSIS_METRICS["incrementalRuns"]) + 1
                    filtered_items: list[dict[str, Any]] = []
                    for item in items:
                        value = item.get("lastUpdateDateUtc") or item.get("createdDateTime") or item.get("invoiceDate")
                        updated_at = _parse_analysis_as_of(str(value)) if value is not None else None
                        if updated_at is not None and updated_at >= cutoff:
                            filtered_items.append(item)
                    items = filtered_items

            analysis = analyze_invoices(
                items,
                config=AnalysisConfig(
                    window_days=max(1, configured_window),
                    stale_days=max(1, settings.analysis_stale_days),
                    top_n=max(1, configured_top_n),
                    high_amount_threshold=max(0.0, settings.analysis_high_amount_threshold),
                    duplicate_amount_delta=max(0.0, settings.analysis_duplicate_amount_delta),
                    policy_profile=profile_name,
                ),
                as_of=_parse_analysis_as_of(as_of_date),
            )
            degraded = bool(collection["partial"])
            if degraded:
                _ANALYSIS_METRICS["degradedResponses"] = int(_ANALYSIS_METRICS["degradedResponses"]) + 1
            analysis["collection"] = {
                "pageSize": collection["pageSize"],
                "maxPages": collection["maxPages"],
                "pagesFetched": collection["pagesFetched"],
                "orderBy": "lastUpdateDateUtc",
                "orderByAsc": False,
                "partial": collection["partial"],
                "errors": collection["errors"],
                "incrementalSince": incremental_since,
            }
            analysis["degraded"] = {
                "isDegraded": degraded,
                "reason": "partial_collection" if degraded else None,
                "strictMode": require_complete,
            }
            analysis["reliability"] = {
                "cacheBackend": settings.analysis_cache_backend,
                "maxConcurrentAnalysisRuns": settings.max_concurrent_analysis_runs,
                "maxConcurrentRequests": settings.max_concurrent_requests,
                "retryStatusCodes": sorted(settings.retry_status_codes()),
                "canary": {
                    "enabled": bool(settings.reliability_canary_enabled),
                    "sampleRate": float(settings.reliability_canary_sample_rate),
                    "sampled": bool(settings.reliability_canary_enabled)
                    and random.random() < max(0.0, min(1.0, settings.reliability_canary_sample_rate)),
                },
            }
            return analysis

        if use_cache:
            computed, _cache_hit = await cache_backend.get_or_compute(
                key=cache_key,
                compute=compute_analysis,
                ttl_seconds=max(30, settings.analysis_cache_ttl_seconds),
            )
            return computed

        return await compute_analysis()

    def _register_unapproved_invoice_analysis_tool() -> None:
        spec = ANALYSIS_BY_TOOL["analyze_unapproved_invoices"]
        description = (
            f"{spec.summary} "
            "Use this for reviewer-ready recommendations without performing write actions."
        )

        async def tool(
            enterprise_id: int | None = Field(
                default=None,
                description="Enterprise id. Optional when VISTA_ENTERPRISE_ID is configured.",
            ),
            window_days: int | None = Field(
                default=None,
                description="Lookback window in days. Defaults to VISTA_ANALYSIS_DEFAULT_WINDOW_DAYS.",
            ),
            top_n: int | None = Field(
                default=None,
                description="Number of highest-dollar attention invoices to highlight.",
            ),
            page_size: int | None = Field(
                default=None,
                description="Page size for invoice collection. Defaults to VISTA_ANALYSIS_PAGE_SIZE.",
            ),
            max_pages: int | None = Field(
                default=None,
                description="Maximum pages to collect. Defaults to VISTA_ANALYSIS_MAX_PAGES.",
            ),
            as_of_date: str | None = Field(
                default=None,
                description="Optional YYYY-MM-DD date override for deterministic analysis windows.",
            ),
            policy_profile: str | None = Field(
                default=None,
                description="Policy profile override: standard, strict, or lenient.",
            ),
            detail_level: str = Field(
                default="compact",
                description="Response detail level: compact (default) or full.",
            ),
            max_items_per_bucket: int | None = Field(
                default=None,
                description="Compact mode: max sample items returned for each review queue.",
            ),
            max_vendor_groups: int | None = Field(
                default=None,
                description="Compact mode: max vendor groups returned.",
            ),
            incremental_since: str | None = Field(
                default=None,
                description="Optional ISO timestamp watermark for incremental analysis mode.",
            ),
            use_cache: bool = Field(
                default=True,
                description="Whether to reuse cached analysis snapshot for identical inputs.",
            ),
            require_complete: bool | None = Field(
                default=None,
                description=(
                    "When true, fail if analysis paging is partial. "
                    "Defaults to VISTA_ANALYSIS_FAIL_ON_PARTIAL."
                ),
            ),
            correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                normalized_detail_level = detail_level.strip().lower() if isinstance(detail_level, str) else "compact"
                if normalized_detail_level not in {"compact", "full"}:
                    raise ValueError("detail_level must be one of: compact, full.")

                resolved_enterprise = resolve_enterprise_id(enterprise_id)
                analysis = await _build_analysis_report(
                    enterprise_id=resolved_enterprise,
                    window_days=window_days,
                    top_n=top_n,
                    page_size=page_size,
                    max_pages=max_pages,
                    as_of_date=as_of_date,
                    policy_profile=policy_profile,
                    correlation_id=correlation_id,
                    incremental_since=incremental_since,
                    use_cache=bool(use_cache),
                    require_complete=(
                        require_complete
                        if isinstance(require_complete, bool)
                        else bool(settings.analysis_fail_on_partial)
                    ),
                )
                run = _RUN_STORE.create_run(
                    analysis=analysis,
                    metadata={
                        "enterpriseId": resolved_enterprise,
                        "windowDays": window_days if isinstance(window_days, int) else settings.analysis_default_window_days,
                        "policyProfile": policy_profile or settings.analysis_policy_profile,
                        "detailLevel": normalized_detail_level,
                    },
                )
                analysis["run"] = run
                _ANALYSIS_METRICS["runsCreated"] = int(_ANALYSIS_METRICS["runsCreated"]) + 1
                if normalized_detail_level == "compact":
                    analysis = _compact_analysis_payload(
                        analysis,
                        max_items_per_bucket=max_items_per_bucket
                        if isinstance(max_items_per_bucket, int)
                        else 25,
                        max_vendor_groups=max_vendor_groups if isinstance(max_vendor_groups, int) else 25,
                    )
                return _serialize_custom_output(
                    tool_name=spec.tool_name,
                    raw_payload=analysis,
                    output_mode=output,
                )

            return await with_tool_error_logging(
                spec.tool_name,
                run,
                enterprise_id=enterprise_id,
                correlation_id=correlation_id,
            )

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=description)(tool)

    def _register_list_invoice_review_queues_tool() -> None:
        spec = ANALYSIS_BY_TOOL["list_invoice_review_queues"]
        async def tool(
            enterprise_id: int | None = Field(default=None, description="Enterprise id."),
            window_days: int | None = Field(default=None, description="Lookback window in days."),
            page_size: int | None = Field(default=None, description="Collection page size."),
            max_pages: int | None = Field(default=None, description="Collection max pages."),
            policy_profile: str | None = Field(default=None, description="Policy profile override."),
            require_complete: bool | None = Field(
                default=None,
                description=(
                    "When true, fail if analysis paging is partial. "
                    "Defaults to VISTA_ANALYSIS_FAIL_ON_PARTIAL."
                ),
            ),
            correlation_id: str | None = Field(default=None, description="Optional x-correlation-id header."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                resolved_enterprise = resolve_enterprise_id(enterprise_id)
                analysis = await _build_analysis_report(
                    enterprise_id=resolved_enterprise,
                    window_days=window_days,
                    top_n=None,
                    page_size=page_size,
                    max_pages=max_pages,
                    as_of_date=None,
                    policy_profile=policy_profile,
                    correlation_id=correlation_id,
                    incremental_since=None,
                    use_cache=True,
                    require_complete=(
                        require_complete
                        if isinstance(require_complete, bool)
                        else bool(settings.analysis_fail_on_partial)
                    ),
                )
                created_run = _RUN_STORE.create_run(
                    analysis=analysis,
                    metadata={
                        "enterpriseId": resolved_enterprise,
                        "windowDays": window_days if isinstance(window_days, int) else settings.analysis_default_window_days,
                        "policyProfile": policy_profile or settings.analysis_policy_profile,
                        "sourceTool": spec.tool_name,
                    },
                )
                queues = _build_queue_views(analysis)
                payload = {
                    "run": created_run,
                    "window": analysis.get("window", {}),
                    "totals": analysis.get("totals", {}),
                    "collection": analysis.get("collection", {}),
                    "topRisks": analysis.get("topRisks", []),
                    "vendorGroups": analysis.get("vendorGroups", [])[:25],
                    "reviewQueues": {
                        queue: {"count": len(items), "startCursor": encode_offset_cursor(0)}
                        for queue, items in queues.items()
                    },
                }
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run, enterprise_id=enterprise_id, correlation_id=correlation_id)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    def _register_get_invoice_queue_page_tool() -> None:
        spec = ANALYSIS_BY_TOOL["get_invoice_queue_page"]
        async def tool(
            run_id: str = Field(description="Analysis run id."),
            queue: str = Field(description="Queue name: approve_candidates, needs_correction, or needs_investigation."),
            cursor: str | None = Field(default=None, description="Opaque page cursor returned by previous call."),
            page_size: int = Field(default=25, description="Max items per queue page (max 100)."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                run_state = _RUN_STORE.get_run(run_id)
                if run_state is None:
                    raise ValueError("run_id not found or expired.")
                normalized_queue = queue.strip().lower()
                queues = _build_queue_views(run_state.get("analysis", {}))
                if normalized_queue not in queues:
                    raise ValueError("queue must be one of: approve_candidates, needs_correction, needs_investigation.")
                page_payload = _queue_page(queue_items=queues[normalized_queue], cursor=cursor, page_size=page_size)
                payload = {
                    "runId": run_id,
                    "queue": normalized_queue,
                    **page_payload,
                    "total": len(queues[normalized_queue]),
                }
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    def _register_get_invoice_review_packet_tool() -> None:
        spec = ANALYSIS_BY_TOOL["get_invoice_review_packet"]
        async def tool(
            run_id: str = Field(description="Analysis run id."),
            invoice_id: str = Field(description="Invoice id from an analysis queue."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                run_state = _RUN_STORE.get_run(run_id)
                if run_state is None:
                    raise ValueError("run_id not found or expired.")
                invoice = _find_invoice(run_state.get("analysis", {}), invoice_id)
                if invoice is None:
                    raise ValueError("invoice_id not found in run queues.")
                payload = {
                    "runId": run_id,
                    "invoice": invoice,
                    "findings": invoice.get("findings", []),
                    "recommendedAction": invoice.get("recommendedAction"),
                    "requiredHumanCheck": bool(invoice.get("requiredHumanCheck")),
                }
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    def _register_capture_invoice_review_decision_tool() -> None:
        spec = ANALYSIS_BY_TOOL["capture_invoice_review_decision"]
        async def tool(
            run_id: str = Field(description="Analysis run id."),
            invoice_id: str = Field(description="Invoice id from an analysis queue."),
            decision: str = Field(description="Decision: approve, correct, investigate."),
            rationale: str | None = Field(default=None, description="Optional reviewer rationale."),
            actor: str | None = Field(default=None, description="Optional actor/reviewer identifier."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                normalized_decision = decision.strip().lower()
                if normalized_decision not in {"approve", "correct", "investigate"}:
                    raise ValueError("decision must be one of: approve, correct, investigate.")
                run_state = _RUN_STORE.get_run(run_id)
                if run_state is None:
                    raise ValueError("run_id not found or expired.")
                if _find_invoice(run_state.get("analysis", {}), invoice_id) is None:
                    raise ValueError("invoice_id not found in run queues.")
                saved = _RUN_STORE.save_decision(
                    run_id=run_id,
                    invoice_id=invoice_id,
                    decision=normalized_decision,
                    rationale=rationale,
                    actor=actor,
                )
                if saved is None:
                    raise ValueError("run_id not found or expired.")
                payload = {"runId": run_id, **saved}
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    def _register_preflight_invoice_approval_tool() -> None:
        spec = ANALYSIS_BY_TOOL["preflight_invoice_approval"]
        async def tool(
            run_id: str = Field(description="Analysis run id."),
            invoice_id: str = Field(description="Invoice id from an analysis queue."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                run_state = _RUN_STORE.get_run(run_id)
                if run_state is None:
                    raise ValueError("run_id not found or expired.")
                invoice = _find_invoice(run_state.get("analysis", {}), invoice_id)
                if invoice is None:
                    raise ValueError("invoice_id not found in run queues.")

                findings = invoice.get("findings", [])
                blocking = []
                warnings = []
                for finding in findings if isinstance(findings, list) else []:
                    severity = str(finding.get("severity") or "").lower()
                    if severity == "high":
                        blocking.append(finding.get("code"))
                    elif severity in {"medium", "low"}:
                        warnings.append(finding.get("code"))
                if not invoice.get("id") or not invoice.get("vendorId") or not invoice.get("invoiceNumber"):
                    blocking.append("missing_required_identity_fields")
                if invoice.get("invoiceAmount") is None or float(invoice.get("invoiceAmount") or 0.0) <= 0:
                    blocking.append("invalid_invoice_amount")

                payload = {
                    "runId": run_id,
                    "invoiceId": invoice_id,
                    "canApprove": len(blocking) == 0,
                    "blockingIssues": blocking,
                    "warnings": warnings,
                    "recommendedAction": invoice.get("recommendedAction"),
                }
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    def _register_export_invoice_audit_tool() -> None:
        spec = ANALYSIS_BY_TOOL["export_invoice_audit"]
        async def tool(
            run_id: str = Field(description="Analysis run id."),
            output: str = Field(default="raw", description="Output mode: raw, normalized, or both."),
        ) -> str:
            async def run() -> str:
                run_state = _RUN_STORE.get_run(run_id)
                if run_state is None:
                    raise ValueError("run_id not found or expired.")
                analysis = run_state.get("analysis", {})
                payload = {
                    "run": {
                        "runId": run_state.get("runId"),
                        "createdAt": run_state.get("createdAt"),
                        "metadata": run_state.get("metadata", {}),
                    },
                    "window": analysis.get("window", {}),
                    "totals": analysis.get("totals", {}),
                    "collection": analysis.get("collection", {}),
                    "decisions": run_state.get("decisions", []),
                    "decisionCount": len(run_state.get("decisions", [])),
                }
                return _serialize_custom_output(tool_name=spec.tool_name, raw_payload=payload, output_mode=output)

            return await with_tool_error_logging(spec.tool_name, run)

        tool.__name__ = spec.tool_name
        tool.__doc__ = spec.summary
        mcp.tool(description=spec.summary)(tool)

    for endpoint in iter_enabled_endpoints(settings):
        if endpoint.operation_kind == "get":
            _register_get_tool(endpoint)
        elif endpoint.operation_kind == "list":
            _register_list_tool(endpoint)
        elif endpoint.operation_kind == "bulk":
            _register_bulk_tool(endpoint)
            _register_bulk_preflight_tool(endpoint)
        else:
            _register_health_tool(endpoint)

    _register_unapproved_invoice_analysis_tool()
    _register_list_invoice_review_queues_tool()
    _register_get_invoice_queue_page_tool()
    _register_get_invoice_review_packet_tool()
    _register_capture_invoice_review_decision_tool()
    _register_preflight_invoice_approval_tool()
    _register_export_invoice_audit_tool()


def get_tool_metrics_snapshot() -> dict[str, dict[str, float | int]]:
    """Expose in-memory tool metrics for debugging/monitoring resources."""

    return {tool: dict(values) for tool, values in _TOOL_METRICS.items()}


def get_analysis_metrics_snapshot() -> dict[str, float | int]:
    """Expose in-memory analysis orchestration metrics."""
    snapshot: dict[str, float | int] = dict(_ANALYSIS_METRICS)
    if _ANALYSIS_CACHE_BACKEND is not None:
        for key, value in _ANALYSIS_CACHE_BACKEND.metrics_snapshot().items():
            snapshot[f"cache_{key}"] = value
    return snapshot


async def close_tool_factory_resources() -> None:
    """Close long-lived tool-factory resources such as Redis cache clients."""

    global _ANALYSIS_CACHE_BACKEND
    if _ANALYSIS_CACHE_BACKEND is not None:
        await _ANALYSIS_CACHE_BACKEND.close()
        _ANALYSIS_CACHE_BACKEND = None


"""OpenAPI-driven helper utilities for tool descriptions and validation hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_SCHEMA_CACHE: dict[str, Any] | None = None


def _openapi_path() -> Path:
    return Path(__file__).resolve().parent.parent / "viewpoint_common_api.json"


def _load_schemas() -> dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        payload = json.loads(_openapi_path().read_text(encoding="utf-8"))
        _SCHEMA_CACHE = payload.get("components", {}).get("schemas", {})
    return _SCHEMA_CACHE


def _schema_name(schema_ref: str | None) -> str | None:
    if not schema_ref:
        return None
    return schema_ref.rsplit("/", 1)[-1]


def _schema_by_ref(schema_ref: str | None) -> dict[str, Any] | None:
    name = _schema_name(schema_ref)
    if not name:
        return None
    return _load_schemas().get(name)


def required_fields_for_request_schema(schema_ref: str | None) -> list[str]:
    """Return request-required fields from an OpenAPI schema ref."""

    schema = _schema_by_ref(schema_ref)
    if not schema:
        return []

    if schema.get("type") == "object":
        top_required = schema.get("required", [])
    else:
        top_required = []

    name = _schema_name(schema_ref) or ""
    if name.endswith("BulkActionBody"):
        item_schema = schema.get("properties", {}).get("items", {}).get("items", {})
        item_ref = item_schema.get("$ref")
        if not item_ref:
            return [f"items[].{field}" for field in top_required]
        item = _schema_by_ref(item_ref)
        if not item:
            return [f"items[].{field}" for field in top_required]
        item_required = item.get("required", [])
        return [f"items[].{field}" for field in item_required]

    return list(top_required)


# Short OpenAPI-aligned examples appended to MCP tool descriptions (reduce bad calls).
_TOOL_DESCRIPTION_EXAMPLES: dict[str, str] = {
    "query_unapproved_invoices": (
        'Example filters JSON: [{"field":"invoiceNumber","operator":"contains","values":["INV-2026"]}, '
        '{"field":"vendorId","operator":"eq","values":["00000000-0000-0000-0000-000000000001"]}]. '
        "Use limit/page for pagination."
    ),
    "list_vendors": (
        'Example filters: [{"field":"vendorCode","operator":"eq","values":["V-1001"]}] or '
        '[{"field":"name","operator":"contains","values":["Acme"]}].'
    ),
    "list_projects": (
        'Example filters: [{"field":"job","operator":"eq","values":["J-2205"]}, '
        '{"field":"companyCode","operator":"eq","values":["01"]}].'
    ),
    "create_unapproved_invoices": (
        "Example items[] keys: companyId, vendorId, invoiceNumber, invoiceAmount (UUIDs as strings). "
        "Use validate_create_unapproved_invoices_request before submit in production."
    ),
    "create_daily_production": (
        "Example items[] keys: companyId, phaseId, projectId, quantityCompleted (per OpenAPI DailyProduction action item)."
    ),
    "get_unapproved_invoice": (
        "Pass id as the unapproved invoice UUID from query_unapproved_invoices items[].id."
    ),
    "get_purchase_order": (
        "Pass id as posted PO UUID from invoice purchaseOrderId or list_purchase_orders items[].id."
    ),
    "get_subcontract": (
        "Pass id as subcontract UUID from invoice subcontractId or list_subcontracts items[].id."
    ),
    "compare_invoice_to_commitments": (
        "Pass enterprise_id and invoice_id; optional run_id to reuse invoice snapshot from a reviewer run. "
        "Fetches PO/sub from Vista when IDs are present."
    ),
    "collect_unapproved_invoices_pages": (
        "Walks query_unapproved_invoices pages until max_pages or short page; set page_size<=100. "
        "Returns partial=true if a page errored mid-collection."
    ),
}


def enrich_tool_description(tool_name: str, base: str) -> str:
    """Append a compact example line when we have curated guidance for this tool."""

    extra = _TOOL_DESCRIPTION_EXAMPLES.get(tool_name)
    if not extra:
        return base
    return f"{base} {extra}"


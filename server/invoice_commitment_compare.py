"""Normalize invoice vs PO/subcontract payloads for structured review comparison."""

from __future__ import annotations

from typing import Any


def _to_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _sum_po_line_extended(items: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in items:
        if not isinstance(row, dict):
            continue
        q = _to_float(row.get("quantity")) or 0.0
        p = _to_float(row.get("itemPrice")) or 0.0
        total += q * p
    return total


def _po_commitment_summary(po_payload: dict[str, Any]) -> dict[str, Any]:
    item = po_payload.get("item")
    if not isinstance(item, dict):
        item = {}
    raw_items = item.get("items")
    lines: list[dict[str, Any]] = [row for row in raw_items if isinstance(row, dict)] if isinstance(raw_items, list) else []
    line_sum = _sum_po_line_extended(lines)
    return {
        "commitmentType": "purchase_order",
        "id": item.get("id"),
        "purchaseOrderNumber": item.get("purchaseOrderNumber"),
        "vendorId": item.get("vendorId"),
        "projectId": item.get("projectId"),
        "lineCount": len(lines),
        "sumLineExtended": round(line_sum, 2),
        "notes": (
            "PO comparison total is sum(quantity * itemPrice) per line from PurchaseOrderRecord.items; "
            "tax and freight may not be included."
        ),
    }


def _sub_commitment_summary(sub_payload: dict[str, Any]) -> dict[str, Any]:
    item = sub_payload.get("item")
    if not isinstance(item, dict):
        item = {}
    raw_items = item.get("items")
    lines = [row for row in raw_items if isinstance(row, dict)] if isinstance(raw_items, list) else []
    return {
        "commitmentType": "subcontract",
        "id": item.get("id"),
        "subcontractNumber": item.get("subcontractNumber"),
        "vendorId": item.get("vendorId"),
        "projectId": item.get("projectId"),
        "lineCount": len(lines),
        "notes": (
            "Subcontract OpenAPI line items do not expose per-line amounts; compare vendor, project, and line counts. "
            "Use ERP UI or extended includes for dollar tie-out when available."
        ),
    }


def compare_invoice_to_commitments(
    invoice: dict[str, Any],
    *,
    po_payload: dict[str, Any] | None,
    sub_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a normalized comparison between an invoice dict and optional PO/sub GET payloads."""

    inv_amt = _to_float(invoice.get("invoiceAmount"))
    vid = invoice.get("vendorId")
    po_id = invoice.get("purchaseOrderId")
    sub_id = invoice.get("subcontractId")

    result: dict[str, Any] = {
        "invoiceId": invoice.get("id"),
        "invoiceNumber": invoice.get("invoiceNumber"),
        "invoiceAmount": inv_amt,
        "vendorId": vid,
        "purchaseOrderId": po_id,
        "subcontractId": sub_id,
        "commitments": [],
        "flags": [],
        "deltas": {},
    }

    if po_id:
        if po_payload is not None:
            pc = _po_commitment_summary(po_payload)
            result["commitments"].append(pc)
            pv = pc.get("vendorId")
            if pv is not None and vid is not None and str(pv) != str(vid):
                result["flags"].append("vendor_mismatch_po")
            if inv_amt is not None and pc.get("sumLineExtended") is not None:
                result["deltas"]["invoiceMinusPoLineSum"] = round(inv_amt - float(pc["sumLineExtended"]), 2)
        else:
            result["flags"].append("purchase_order_not_loaded")

    if sub_id:
        if sub_payload is not None:
            sc = _sub_commitment_summary(sub_payload)
            result["commitments"].append(sc)
            sv = sc.get("vendorId")
            if sv is not None and vid is not None and str(sv) != str(vid):
                result["flags"].append("vendor_mismatch_subcontract")
        else:
            result["flags"].append("subcontract_not_loaded")

    return result

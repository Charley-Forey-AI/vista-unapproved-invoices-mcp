from __future__ import annotations

from server.invoice_commitment_compare import compare_invoice_to_commitments


def test_compare_matches_vendor_and_po_line_sum() -> None:
    invoice = {
        "id": "inv-1",
        "invoiceNumber": "A1",
        "invoiceAmount": 100.0,
        "vendorId": "00000000-0000-0000-0000-000000000001",
        "purchaseOrderId": "11111111-1111-1111-1111-111111111111",
    }
    po_payload = {
        "item": {
            "id": "11111111-1111-1111-1111-111111111111",
            "vendorId": "00000000-0000-0000-0000-000000000001",
            "purchaseOrderNumber": "PO-1",
            "items": [{"quantity": 2.0, "itemPrice": 50.0}],
        }
    }
    result = compare_invoice_to_commitments(invoice, po_payload=po_payload, sub_payload=None)
    assert result["deltas"]["invoiceMinusPoLineSum"] == 0.0
    assert "vendor_mismatch_po" not in result["flags"]


def test_compare_flags_vendor_mismatch_on_po() -> None:
    invoice = {
        "id": "inv-1",
        "invoiceAmount": 10.0,
        "vendorId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "purchaseOrderId": "11111111-1111-1111-1111-111111111111",
    }
    po_payload = {
        "item": {
            "id": "11111111-1111-1111-1111-111111111111",
            "vendorId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "items": [],
        }
    }
    result = compare_invoice_to_commitments(invoice, po_payload=po_payload, sub_payload=None)
    assert "vendor_mismatch_po" in result["flags"]

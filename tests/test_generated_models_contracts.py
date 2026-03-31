from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.generated_models import request_model_for_schema


def test_bulk_request_model_enforces_required_fields_for_unapproved_invoice() -> None:
    model = request_model_for_schema("#/components/schemas/UnapprovedInvoiceActionRequestBulkActionBody")
    assert model is not None

    with pytest.raises(ValidationError):
        model.model_validate({"items": [{"invoiceNumber": "INV-1"}]})

    validated = model.model_validate(
        {
            "items": [
                {
                    "companyId": "00000000-0000-0000-0000-000000000001",
                    "vendorId": "00000000-0000-0000-0000-000000000002",
                    "invoiceNumber": "INV-1",
                    "invoiceAmount": 123.45,
                }
            ]
        }
    )
    assert validated.items[0].invoiceNumber == "INV-1"


def test_bulk_request_model_enforces_purchase_order_required_fields() -> None:
    model = request_model_for_schema("#/components/schemas/PurchaseOrderActionRequestBulkActionBody")
    assert model is not None
    with pytest.raises(ValidationError):
        model.model_validate({"items": [{"vendorId": "00000000-0000-0000-0000-000000000002"}]})


from __future__ import annotations

from server.normalization import normalize_payload


def test_normalize_payload_converts_nested_keys_to_snake_case() -> None:
    raw = {
        "item": {
            "id": "abc",
            "vendorCode": "V100",
            "alternateAddresses": [{"postalCode": "12345"}],
        },
        "pageSize": 25,
    }
    normalized = normalize_payload(raw, tool_name="get_vendor", schema_ref="#/components/schemas/VendorRecordGetItemResponse")
    assert normalized["tool_name"] == "get_vendor"
    assert normalized["data"]["item"]["vendor_code"] == "V100"
    assert normalized["data"]["item"]["alternate_addresses"][0]["postal_code"] == "12345"
    assert normalized["data"]["page_size"] == 25


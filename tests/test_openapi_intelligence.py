from __future__ import annotations

from server.openapi_intelligence import enrich_tool_description


def test_enrich_tool_description_appends_example_for_query_invoices() -> None:
    base = "List invoices."
    out = enrich_tool_description("query_unapproved_invoices", base)
    assert out.startswith(base)
    assert "Example filters JSON" in out

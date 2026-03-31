from __future__ import annotations

import json

import pytest

from server.config import VistaSettings
from server.tool_factory import register_endpoint_tools


class _FakeMcp:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.descriptions: dict[str, str] = {}

    def tool(self, description: str):  # type: ignore[no-untyped-def]
        def decorator(func):  # type: ignore[no-untyped-def]
            self.tools[func.__name__] = func
            self.descriptions[func.__name__] = description
            return func

        return decorator


class _FakeApi:
    def __init__(self, *, partial_analysis: bool = False) -> None:
        self.called = False
        self.partial_analysis = partial_analysis

    def set_request_bearer_token(self, token):  # type: ignore[no-untyped-def]
        return object()

    def reset_request_bearer_token(self, token):  # type: ignore[no-untyped-def]
        return None

    async def call_endpoint(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.called = True
        spec = args[0]
        if spec.tool_name == "get_enterprise":
            return {"item": {"id": 3231, "name": "Fallback Enterprise"}}
        if spec.tool_name in {"list_enterprises", "test_list_enterprises"}:
            raise RuntimeError("POST /api/v1/enterprise authorization failed (403).")
        return {"items": []}

    async def collect_list_pages(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.called = True
        return {
            "items": [
                {
                    "id": "inv-deleted",
                    "vendorId": "vendor-1",
                    "invoiceNumber": "INV-DEL",
                    "invoiceAmount": 50.0,
                    "invoiceDate": "2026-01-01T00:00:00Z",
                    "deleted": True,
                },
                {
                    "id": "inv-1",
                    "vendorId": "vendor-1",
                    "invoiceNumber": "INV-1",
                    "invoiceAmount": 123.45,
                    "invoiceDate": "2026-01-01T00:00:00Z",
                }
            ],
            "pagesFetched": 1,
            "partial": self.partial_analysis,
            "errors": [{"page": 1, "message": "simulated partial"}] if self.partial_analysis else [],
            "pageSize": kwargs.get("page_size", 100),
            "maxPages": kwargs.get("max_pages", 20),
        }


@pytest.mark.anyio
async def test_bulk_tool_dry_run_does_not_call_api() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 1,
    )

    create_po = mcp.tools["create_purchase_orders"]
    result = await create_po(  # type: ignore[misc]
        items={
            "companyId": "00000000-0000-0000-0000-000000000001",
            "purchaseOrderNumber": "PO-10",
            "vendorId": "00000000-0000-0000-0000-000000000002",
        },
        enterprise_id=1,
        dry_run=True,
        output="raw",
    )
    assert '"dryRun": true' in result
    assert api.called is False


@pytest.mark.anyio
async def test_bulk_tool_rejects_writes_when_read_only() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        read_only_mode=True,
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 1,
    )

    create_invoice = mcp.tools["create_unapproved_invoices"]
    with pytest.raises(ValueError, match="read_only_mode"):
        await create_invoice(  # type: ignore[misc]
            items={
                "companyId": "00000000-0000-0000-0000-000000000001",
                "vendorId": "00000000-0000-0000-0000-000000000002",
                "invoiceNumber": "INV-2",
                "invoiceAmount": 55.0,
            },
            enterprise_id=1,
        )


@pytest.mark.anyio
async def test_preflight_tool_reports_missing_required_fields() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 1,
    )

    preflight = mcp.tools["validate_create_unapproved_invoices_request"]
    result = await preflight(  # type: ignore[misc]
        items={
            "companyId": "00000000-0000-0000-0000-000000000001",
            "invoiceAmount": 55.0,
        },
        enterprise_id=1,
    )

    assert '"valid": false' in result
    assert '"missing_required_input"' in result


def test_tool_description_is_enriched_with_required_inputs() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 1,
    )
    description = mcp.descriptions["create_purchase_orders"]
    assert "Required inputs:" in description
    assert "items[].purchaseOrderNumber" in description


@pytest.mark.anyio
async def test_list_enterprises_falls_back_to_get_enterprise_on_403() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        enterprise_id=3231,
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    list_enterprises = mcp.tools["list_enterprises"]
    result = await list_enterprises(filters=None, limit=50, output="raw")  # type: ignore[misc]
    assert '"id": 3231' in result
    assert '"pageSize": 1' in result


@pytest.mark.anyio
async def test_delegated_mode_requires_request_token() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        auth_mode="delegated",
        mcp_transport="streamable-http",
        auth_issuer="https://stage.id.trimblecloud.com",
        auth_jwks_url="https://stage.id.trimblecloud.com/.well-known/jwks.json",
        auth_resource_server_url="https://mcp.example.com/mcp",
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=True,
        require_request_token=True,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    list_enterprises = mcp.tools["list_enterprises"]
    with pytest.raises(RuntimeError, match="On behalf of actor token"):
        await list_enterprises(filters=None, limit=10, output="raw")  # type: ignore[misc]


@pytest.mark.anyio
async def test_analysis_tool_registered_and_returns_summary() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        enterprise_id=3231,
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    analyze = mcp.tools["analyze_unapproved_invoices"]
    result = await analyze(output="raw")  # type: ignore[misc]
    payload = json.loads(result)
    assert "totals" in payload
    assert payload["totals"]["excludedDeletedCount"] == 1
    assert "topRisks" in payload
    assert "vendorGroups" in payload
    assert "reviewQueues" in payload
    assert "approveCandidates" not in payload


@pytest.mark.anyio
async def test_analysis_tool_full_detail_mode_returns_all_buckets() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        enterprise_id=3231,
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    analyze = mcp.tools["analyze_unapproved_invoices"]
    result = await analyze(output="raw", detail_level="full")  # type: ignore[misc]
    payload = json.loads(result)
    assert "approveCandidates" in payload
    assert "needsCorrection" in payload
    assert "needsInvestigation" in payload


@pytest.mark.anyio
async def test_analysis_tool_strict_mode_fails_on_partial_collection() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        enterprise_id=3231,
    )
    mcp = _FakeMcp()
    api = _FakeApi(partial_analysis=True)
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    analyze = mcp.tools["analyze_unapproved_invoices"]
    with pytest.raises(RuntimeError, match="partial results"):
        await analyze(output="raw", require_complete=True, use_cache=False)  # type: ignore[misc]


@pytest.mark.anyio
async def test_queue_workflow_tools_support_paging_packet_and_decision() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        enterprise_id=3231,
    )
    mcp = _FakeMcp()
    api = _FakeApi()
    register_endpoint_tools(
        mcp=mcp,
        settings=settings,
        api=api,  # type: ignore[arg-type]
        delegated_mode=False,
        require_request_token=False,
        get_request_token=lambda: None,
        resolve_enterprise_id=lambda value: value if value is not None else 3231,
    )

    list_queues = mcp.tools["list_invoice_review_queues"]
    queue_payload = json.loads(await list_queues(output="raw"))  # type: ignore[misc]
    run_id = queue_payload["run"]["runId"]

    get_page = mcp.tools["get_invoice_queue_page"]
    page_payload = json.loads(
        await get_page(run_id=run_id, queue="approve_candidates", page_size=10, output="raw")  # type: ignore[misc]
    )
    assert page_payload["runId"] == run_id
    assert "items" in page_payload

    item_id = page_payload["items"][0]["id"]
    packet_tool = mcp.tools["get_invoice_review_packet"]
    packet_payload = json.loads(
        await packet_tool(run_id=run_id, invoice_id=item_id, output="raw")  # type: ignore[misc]
    )
    assert packet_payload["invoice"]["id"] == item_id

    decision_tool = mcp.tools["capture_invoice_review_decision"]
    decision_payload = json.loads(
        await decision_tool(
            run_id=run_id,
            invoice_id=item_id,
            decision="approve",
            rationale="validated",
            output="raw",
        )  # type: ignore[misc]
    )
    assert decision_payload["decision"] == "approve"

    preflight_tool = mcp.tools["preflight_invoice_approval"]
    preflight_payload = json.loads(
        await preflight_tool(run_id=run_id, invoice_id=item_id, output="raw")  # type: ignore[misc]
    )
    assert "canApprove" in preflight_payload

    export_tool = mcp.tools["export_invoice_audit"]
    export_payload = json.loads(await export_tool(run_id=run_id, output="raw"))  # type: ignore[misc]
    assert export_payload["decisionCount"] >= 1


"""Registry of Vista operations exposed as MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import VistaSettings

OperationKind = Literal["get", "list", "bulk", "health"]


@dataclass(frozen=True)
class EndpointSpec:
    """Declarative metadata used to register tools and call Vista endpoints."""

    tool_name: str
    method: Literal["GET", "POST"]
    path: str
    summary: str
    tag: str
    operation_kind: OperationKind
    response_schema_ref: str | None
    request_schema_ref: str | None = None
    requires_enterprise_id: bool = False
    optional_setting_flag: str | None = None
    required_inputs: tuple[str, ...] = ()
    produced_fields: tuple[str, ...] = ()
    recommended_prerequisites: tuple[str, ...] = ()
    write_domain: str | None = None
    safe_to_retry: bool | None = None


@dataclass(frozen=True)
class AnalysisToolSpec:
    """Declarative metadata for non-endpoint analysis tools."""

    tool_name: str
    summary: str
    required_inputs: tuple[str, ...] = ()
    produced_fields: tuple[str, ...] = ()


SCOPED_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        tool_name="get_enterprise",
        method="GET",
        path="/api/v1/{enterpriseId}",
        summary="Get an Enterprise by Id.",
        tag="Enterprise Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/EnterpriseRecordGetItemResponse",
        requires_enterprise_id=True,
        produced_fields=("item.id", "item.name"),
    ),
    EndpointSpec(
        tool_name="list_enterprises",
        method="POST",
        path="/api/v1/enterprise",
        summary="List Enterprises (paged).",
        tag="Enterprise Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/EnterpriseRecordFilterBody",
        response_schema_ref="#/components/schemas/EnterpriseRecordListPagedResponse",
        produced_fields=("items[].id", "items[].name"),
    ),
    EndpointSpec(
        tool_name="test_list_enterprises",
        method="POST",
        path="/api/v1/test/enterprise",
        summary="Test List Enterprises (paged).",
        tag="Enterprise Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/EnterpriseRecordFilterBody",
        response_schema_ref="#/components/schemas/EnterpriseRecordListPagedResponse",
        optional_setting_flag="include_test_enterprise_tool",
    ),
    EndpointSpec(
        tool_name="get_company",
        method="GET",
        path="/api/v1/{enterpriseId}/company/{id}",
        summary="Get a Company Item by Id.",
        tag="Company Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/CompanyRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_companies",
        method="POST",
        path="/api/v1/{enterpriseId}/company",
        summary="List Company Records (paged).",
        tag="Company Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/CompanyRecordFilterBody",
        response_schema_ref="#/components/schemas/CompanyRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_contract",
        method="GET",
        path="/api/v1/{enterpriseId}/contract/{id}",
        summary="Get a Contract by Id.",
        tag="Contract Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/ContractRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_contracts",
        method="POST",
        path="/api/v1/{enterpriseId}/contract",
        summary="List Contracts (paged).",
        tag="Contract Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/ContractRecordFilterBody",
        response_schema_ref="#/components/schemas/ContractRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_customer",
        method="GET",
        path="/api/v1/{enterpriseId}/customer/{id}",
        summary="Get a Customer by Id.",
        tag="Customer Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/CustomerRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_customers",
        method="POST",
        path="/api/v1/{enterpriseId}/customer",
        summary="List Customers (paged).",
        tag="Customer Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/CustomerRecordFilterBody",
        response_schema_ref="#/components/schemas/CustomerRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="create_daily_production",
        method="POST",
        path="/api/v1/{enterpriseId}/jc/dailyproduction",
        summary="Create Daily Production records in bulk.",
        tag="Project Cost Entry Endpoints",
        operation_kind="bulk",
        request_schema_ref="#/components/schemas/DailyProductionActionRequestBulkActionBody",
        response_schema_ref="#/components/schemas/DailyProductionActionRecordBulkApiActionResponse",
        requires_enterprise_id=True,
        required_inputs=("items[].companyId", "items[].phaseId", "items[].projectId", "items[].quantityCompleted"),
        produced_fields=("items[].item.id", "items[].statusCode", "items[].message"),
        recommended_prerequisites=("get_project", "get_project_phase"),
        write_domain="jc",
    ),
    EndpointSpec(
        tool_name="get_daily_production_action",
        method="GET",
        path="/api/v1/{enterpriseId}/jc/dailyproduction/action/{id}",
        summary="Get a Daily Production Action by Id.",
        tag="Project Cost Entry Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/DailyProductionActionRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_unposted_daily_production",
        method="GET",
        path="/api/v1/{enterpriseId}/jc/unposteddailyproduction/{id}",
        summary="Get an Unposted Daily Production by Id.",
        tag="Project Cost Entry Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/UnpostedDailyProductionRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_unposted_daily_production",
        method="POST",
        path="/api/v1/{enterpriseId}/jc/unposteddailyproduction/query",
        summary="List Unposted Daily Production records (paged).",
        tag="Project Cost Entry Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/UnpostedDailyProductionRecordFilterBody",
        response_schema_ref="#/components/schemas/UnpostedDailyProductionRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_project_cost_history",
        method="GET",
        path="/api/v1/{enterpriseId}/projectcosthistory/{id}",
        summary="Get a Project Cost History Item by Id.",
        tag="Project Cost History Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/ProjectCostHistoryRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_project_cost_history",
        method="POST",
        path="/api/v1/{enterpriseId}/projectcosthistory",
        summary="List Project Cost History (paged).",
        tag="Project Cost History Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/ProjectCostHistoryRecordFilterBody",
        response_schema_ref="#/components/schemas/ProjectCostHistoryRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_project",
        method="GET",
        path="/api/v1/{enterpriseId}/project/{id}",
        summary="Get a Project by Id.",
        tag="Project Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/ProjectRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_projects",
        method="POST",
        path="/api/v1/{enterpriseId}/project",
        summary="List Projects (paged).",
        tag="Project Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/ProjectRecordFilterBody",
        response_schema_ref="#/components/schemas/ProjectRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_project_phase",
        method="GET",
        path="/api/v1/{enterpriseId}/projectphase/{id}",
        summary="Get a Project Phase by Id.",
        tag="Project Phase Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/ProjectPhaseRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_project_phases",
        method="POST",
        path="/api/v1/{enterpriseId}/projectphase",
        summary="List Project Phases (paged).",
        tag="Project Phase Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/ProjectPhaseRecordFilterBody",
        response_schema_ref="#/components/schemas/ProjectPhaseRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_equipment_action",
        method="GET",
        path="/api/v1/{enterpriseId}/eq/equipment/action/{id}",
        summary="Get an Equipment Action by Id.",
        tag="Equipment Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/EquipmentActionRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_equipment",
        method="GET",
        path="/api/v1/{enterpriseId}/eq/equipment/{id}",
        summary="Get an Equipment by Id.",
        tag="Equipment Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/EquipmentRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_equipment",
        method="POST",
        path="/api/v1/{enterpriseId}/eq/equipment/query",
        summary="List Equipment Records (paged).",
        tag="Equipment Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/EquipmentRecordFilterBody",
        response_schema_ref="#/components/schemas/EquipmentRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_purchase_order_action",
        method="GET",
        path="/api/v1/{enterpriseId}/po/purchaseorder/action/{id}",
        summary="Get a Purchase Order Action by Id.",
        tag="Purchase Order Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/PurchaseOrderActionRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_purchase_order",
        method="GET",
        path="/api/v1/{enterpriseId}/po/purchaseorder/{id}",
        summary="Get a posted Purchase Order by Id.",
        tag="Purchase Order Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/PurchaseOrderRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_unposted_purchase_order",
        method="GET",
        path="/api/v1/{enterpriseId}/po/unpostedpurchaseorder/{id}",
        summary="Get an Unposted Purchase Order by Id.",
        tag="Purchase Order Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/UnpostedPurchaseOrderRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_purchase_orders",
        method="POST",
        path="/api/v1/{enterpriseId}/po/purchaseorder/query",
        summary="List posted Purchase Orders (paged).",
        tag="Purchase Order Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/PurchaseOrderRecordFilterBody",
        response_schema_ref="#/components/schemas/PurchaseOrderRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_unposted_purchase_orders",
        method="POST",
        path="/api/v1/{enterpriseId}/po/unpostedpurchaseorder/query",
        summary="List Unposted Purchase Orders (paged).",
        tag="Purchase Order Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/UnpostedPurchaseOrderRecordFilterBody",
        response_schema_ref="#/components/schemas/UnpostedPurchaseOrderRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_sales_tax",
        method="GET",
        path="/api/v1/{enterpriseId}/salestax/{id}",
        summary="Get a Sales Tax record by Id.",
        tag="Sales Tax Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/SalesTaxRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_sales_tax",
        method="POST",
        path="/api/v1/{enterpriseId}/salestax",
        summary="List Sales Tax records (paged).",
        tag="Sales Tax Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/SalesTaxRecordFilterBody",
        response_schema_ref="#/components/schemas/SalesTaxRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_schedule_of_values",
        method="GET",
        path="/api/v1/{enterpriseId}/scheduleofvalues/{id}",
        summary="Get a Schedule of Values item by Id.",
        tag="Schedule Of Values Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/ScheduleOfValuesRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_schedule_of_values",
        method="POST",
        path="/api/v1/{enterpriseId}/scheduleofvalues",
        summary="List Schedule of Values (paged).",
        tag="Schedule Of Values Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/ScheduleOfValuesRecordFilterBody",
        response_schema_ref="#/components/schemas/ScheduleOfValuesRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_standard_cost_type",
        method="GET",
        path="/api/v1/{enterpriseId}/standardcosttype/{id}",
        summary="Get a Standard Cost Type by Id.",
        tag="Standard Cost Type Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/StandardCostTypeRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_standard_cost_types",
        method="POST",
        path="/api/v1/{enterpriseId}/standardcosttype",
        summary="List Standard Cost Types (paged).",
        tag="Standard Cost Type Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/StandardCostTypeRecordFilterBody",
        response_schema_ref="#/components/schemas/StandardCostTypeRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_standard_phase",
        method="GET",
        path="/api/v1/{enterpriseId}/standardphase/{id}",
        summary="Get a Standard Phase by Id.",
        tag="Standard Phase Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/StandardPhaseRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_standard_phases",
        method="POST",
        path="/api/v1/{enterpriseId}/standardphase",
        summary="List Standard Phases (paged).",
        tag="Standard Phase Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/StandardPhaseRecordFilterBody",
        response_schema_ref="#/components/schemas/StandardPhaseRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_subcontract",
        method="GET",
        path="/api/v1/{enterpriseId}/sub/subcontract/{id}",
        summary="Get a Subcontract by Id.",
        tag="Subcontract Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/SubcontractRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_subcontracts",
        method="POST",
        path="/api/v1/{enterpriseId}/sub/subcontract/query",
        summary="List Subcontract Records (paged).",
        tag="Subcontract Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/SubcontractRecordFilterBody",
        response_schema_ref="#/components/schemas/SubcontractRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="create_unapproved_invoices",
        method="POST",
        path="/api/v1/{enterpriseId}/ap/unapprovedinvoice",
        summary="Create Unapproved Invoices in bulk.",
        tag="Unapproved Invoice Endpoints",
        operation_kind="bulk",
        request_schema_ref="#/components/schemas/UnapprovedInvoiceActionRequestBulkActionBody",
        response_schema_ref="#/components/schemas/UnapprovedInvoiceActionRecordBulkApiActionResponse",
        requires_enterprise_id=True,
        required_inputs=("items[].companyId", "items[].vendorId", "items[].invoiceNumber", "items[].invoiceAmount"),
        produced_fields=("items[].item.id", "items[].statusCode", "items[].message"),
        recommended_prerequisites=("get_enterprise", "get_vendor"),
        write_domain="ap",
    ),
    EndpointSpec(
        tool_name="get_unapproved_invoice_action",
        method="GET",
        path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/action/{id}",
        summary="Get an Unapproved Invoice Action by Id.",
        tag="Unapproved Invoice Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/UnapprovedInvoiceActionRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_unapproved_invoice",
        method="GET",
        path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/{id}",
        summary="Get an Unapproved Invoice by Id.",
        tag="Unapproved Invoice Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/UnapprovedInvoiceRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="query_unapproved_invoices",
        method="POST",
        path="/api/v1/{enterpriseId}/ap/unapprovedinvoice/query",
        summary="List Unapproved Invoice records (paged).",
        tag="Unapproved Invoice Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/UnapprovedInvoiceRecordFilterBody",
        response_schema_ref="#/components/schemas/UnapprovedInvoiceRecordListPagedResponse",
        requires_enterprise_id=True,
        produced_fields=("items[].id", "items[].vendorId", "items[].purchaseOrderId", "items[].subcontractId"),
    ),
    EndpointSpec(
        tool_name="get_vendor_alternate_address",
        method="GET",
        path="/api/v1/{enterpriseId}/vendoralternateaddress/{id}",
        summary="Get a Vendor Alternate Address by Id.",
        tag="Vendor Alternate Address Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/VendorAlternateAddressRecordGetItemResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="list_vendor_alternate_addresses",
        method="POST",
        path="/api/v1/{enterpriseId}/vendoralternateaddress",
        summary="List Vendor Alternate Addresses (paged).",
        tag="Vendor Alternate Address Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/VendorAlternateAddressRecordFilterBody",
        response_schema_ref="#/components/schemas/VendorAlternateAddressRecordListPagedResponse",
        requires_enterprise_id=True,
    ),
    EndpointSpec(
        tool_name="get_vendor",
        method="GET",
        path="/api/v1/{enterpriseId}/vendor/{id}",
        summary="Get a Vendor by Id.",
        tag="Vendor Endpoints",
        operation_kind="get",
        response_schema_ref="#/components/schemas/VendorRecordGetItemResponse",
        requires_enterprise_id=True,
        produced_fields=("item.id", "item.alternateAddresses[].id", "item.vendorCode"),
        recommended_prerequisites=("list_vendors",),
    ),
    EndpointSpec(
        tool_name="list_vendors",
        method="POST",
        path="/api/v1/{enterpriseId}/vendor",
        summary="List Vendors (paged).",
        tag="Vendor Endpoints",
        operation_kind="list",
        request_schema_ref="#/components/schemas/VendorRecordFilterBody",
        response_schema_ref="#/components/schemas/VendorRecordListPagedResponse",
        requires_enterprise_id=True,
        produced_fields=("items[].id", "items[].alternateAddresses[].id", "items[].vendorCode"),
    ),
    EndpointSpec(
        tool_name="health_ready",
        method="GET",
        path="/health/ready",
        summary="Verify SQL and Blob Storage connections are ready.",
        tag="Health Check Endpoints",
        operation_kind="health",
        response_schema_ref=None,
    ),
    EndpointSpec(
        tool_name="health_alive",
        method="GET",
        path="/health/alive",
        summary="Verify Kafka client is alive.",
        tag="Health Check Endpoints",
        operation_kind="health",
        response_schema_ref=None,
        optional_setting_flag="include_health_alive_tool",
    ),
)

ENDPOINTS_BY_TOOL: dict[str, EndpointSpec] = {endpoint.tool_name: endpoint for endpoint in SCOPED_ENDPOINTS}
ANALYSIS_TOOLS: tuple[AnalysisToolSpec, ...] = (
    AnalysisToolSpec(
        tool_name="list_invoice_review_queues",
        summary=(
            "Create a reviewer run and return queue counts, vendor rollups, and top risks "
            "without returning full queue payloads."
        ),
        required_inputs=("enterprise_id",),
        produced_fields=("runId", "totals", "reviewQueues", "vendorGroups", "topRisks"),
    ),
    AnalysisToolSpec(
        tool_name="get_invoice_queue_page",
        summary="Get a deterministic page from a stored invoice review queue using cursor pagination.",
        required_inputs=("run_id", "queue"),
        produced_fields=("items", "nextCursor", "hasMore"),
    ),
    AnalysisToolSpec(
        tool_name="get_invoice_review_packet",
        summary="Fetch reviewer-ready packet for one invoice from a stored run.",
        required_inputs=("run_id", "invoice_id"),
        produced_fields=("invoice", "findings", "recommendedAction", "riskScore"),
    ),
    AnalysisToolSpec(
        tool_name="capture_invoice_review_decision",
        summary="Record reviewer decision rationale for an analyzed invoice.",
        required_inputs=("run_id", "invoice_id", "decision"),
        produced_fields=("decision", "recordedAt"),
    ),
    AnalysisToolSpec(
        tool_name="preflight_invoice_approval",
        summary="Validate invoice readiness against policy before approval action.",
        required_inputs=("run_id", "invoice_id"),
        produced_fields=("canApprove", "blockingIssues", "warnings"),
    ),
    AnalysisToolSpec(
        tool_name="export_invoice_audit",
        summary="Export run metadata, queue totals, and reviewer decisions for audit traceability.",
        required_inputs=("run_id",),
        produced_fields=("run", "totals", "decisions"),
    ),
    AnalysisToolSpec(
        tool_name="analyze_unapproved_invoices",
        summary=(
            "Analyze unapproved invoices with schema and AP policy checks. "
            "Returns compact reviewer queues by default (with full-detail mode available), "
            "vendor rollups, and top risks."
        ),
        required_inputs=("enterprise_id", "window_days"),
        produced_fields=(
            "totals.excludedDeletedCount",
            "totals.approveCandidateCount",
            "totals.needsCorrectionCount",
            "totals.needsInvestigationCount",
            "reviewQueues",
            "vendorGroups[]",
            "topRisks[]",
        ),
    ),
    AnalysisToolSpec(
        tool_name="compare_invoice_to_commitments",
        summary=(
            "Structured comparison of an unapproved invoice to posted purchase order and/or subcontract "
            "(amounts, vendor match, line counts). Uses Vista GET payloads when PO/sub IDs are present."
        ),
        required_inputs=("enterprise_id", "invoice_id"),
        produced_fields=(
            "invoiceAmount",
            "commitments",
            "flags",
            "deltas",
        ),
    ),
    AnalysisToolSpec(
        tool_name="collect_unapproved_invoices_pages",
        summary=(
            "Collect all pages from query_unapproved_invoices up to max_pages with partial-result safety. "
            "Prefer this over manual paging when you need the full open backlog."
        ),
        required_inputs=("enterprise_id",),
        produced_fields=("items", "pagesFetched", "partial", "errors", "pageSize", "maxPages"),
    ),
)
ANALYSIS_BY_TOOL: dict[str, AnalysisToolSpec] = {tool.tool_name: tool for tool in ANALYSIS_TOOLS}

ID_SOURCE_MAP: dict[str, tuple[str, ...]] = {
    "enterprise_id": ("list_enterprises", "get_enterprise"),
    "companyId": ("get_company", "list_companies", "get_enterprise"),
    "contractId": ("get_contract", "list_contracts"),
    "customerId": ("get_customer", "list_customers"),
    "vendorId": ("get_vendor", "list_vendors"),
    "vendorAlternateAddressId": ("get_vendor", "list_vendors", "get_vendor_alternate_address"),
    "projectId": ("get_project", "list_projects"),
    "phaseId": ("get_project_phase", "list_project_phases"),
    "purchaseOrderId": ("get_purchase_order", "list_purchase_orders"),
    "subcontractId": ("get_subcontract", "list_subcontracts"),
    "equipmentId": ("get_equipment", "list_equipment"),
}

# IDs used only by analysis tools (merged into planner id_sources with Vista map).
ANALYSIS_ID_SOURCE_MAP: dict[str, tuple[str, ...]] = {
    "run_id": ("list_invoice_review_queues", "analyze_unapproved_invoices"),
    "invoice_id": (
        "query_unapproved_invoices",
        "get_unapproved_invoice",
        "get_invoice_review_packet",
        "get_invoice_queue_page",
    ),
}


def iter_enabled_endpoints(settings: VistaSettings) -> list[EndpointSpec]:
    """Return endpoint specs enabled by runtime flags."""

    enabled: list[EndpointSpec] = []
    for endpoint in SCOPED_ENDPOINTS:
        if endpoint.optional_setting_flag:
            if not bool(getattr(settings, endpoint.optional_setting_flag, False)):
                continue
        enabled.append(endpoint)
    return enabled


def endpoint_dependency_graph(settings: VistaSettings) -> dict[str, object]:
    """Build machine-readable dependency metadata for all enabled tools."""

    nodes: list[dict[str, object]] = []
    combined_id_sources: dict[str, tuple[str, ...]] = {**ID_SOURCE_MAP, **ANALYSIS_ID_SOURCE_MAP}

    def _infer_id_sources(required_fields: list[str]) -> dict[str, list[str]]:
        sources: dict[str, list[str]] = {}
        for field in required_fields:
            normalized = field.replace("items[].", "")
            for key, providers in combined_id_sources.items():
                if normalized == key:
                    sources[normalized] = list(providers)
        return sources

    def _safe_to_retry(endpoint: EndpointSpec) -> bool:
        if endpoint.safe_to_retry is not None:
            return endpoint.safe_to_retry
        return endpoint.operation_kind in {"get", "list", "health"}

    for endpoint in iter_enabled_endpoints(settings):
        required_inputs = list(endpoint.required_inputs)
        if endpoint.requires_enterprise_id and "enterprise_id" not in required_inputs:
            required_inputs.insert(0, "enterprise_id")

        produced_fields = list(endpoint.produced_fields)
        if endpoint.operation_kind in {"get", "list"} and "item.id" not in produced_fields:
            produced_fields.append("item.id")
        if endpoint.operation_kind == "list":
            if "items[].id" not in produced_fields:
                produced_fields.append("items[].id")
            if "pagination.pageSize" not in produced_fields:
                produced_fields.append("pagination.pageSize")
            if "pagination.currentPage" not in produced_fields:
                produced_fields.append("pagination.currentPage")

        nodes.append(
            {
                "tool": endpoint.tool_name,
                "tag": endpoint.tag,
                "kind": endpoint.operation_kind,
                "method": endpoint.method,
                "path": endpoint.path,
                "required_inputs": required_inputs,
                "produced_fields": produced_fields,
                "requires": required_inputs,
                "produces": produced_fields,
                "prerequisites": list(endpoint.recommended_prerequisites),
                "id_sources": _infer_id_sources(required_inputs),
                "safe_to_retry": _safe_to_retry(endpoint),
                "response_schema_ref": endpoint.response_schema_ref,
                "request_schema_ref": endpoint.request_schema_ref,
                "write_domain": endpoint.write_domain,
            }
        )

    for analysis in ANALYSIS_TOOLS:
        required_inputs = list(analysis.required_inputs)
        produced_fields = list(analysis.produced_fields)
        nodes.append(
            {
                "tool": analysis.tool_name,
                "tag": "Analysis Tools",
                "kind": "analysis",
                "method": None,
                "path": None,
                "required_inputs": required_inputs,
                "produced_fields": produced_fields,
                "requires": required_inputs,
                "produces": produced_fields,
                "prerequisites": [],
                "id_sources": _infer_id_sources(required_inputs),
                "safe_to_retry": False,
                "response_schema_ref": None,
                "request_schema_ref": None,
                "write_domain": None,
            }
        )

    workflows: list[dict[str, object]] = [
        {
            "intent": "create_unapproved_invoice",
            "tool_order": [
                "list_enterprises",
                "list_vendors",
                "get_vendor",
                "get_enterprise",
                "create_unapproved_invoices",
            ],
            "decision_rules": [
                "If enterprise_id is already known, skip list_enterprises.",
                "If vendorId is already known, skip list_vendors/get_vendor.",
                "If bulk item count exceeds max_batch_size, split into chunks.",
            ],
        },
        {
            "intent": "investigate_invoice",
            "tool_order": [
                "get_unapproved_invoice",
                "get_vendor",
                "get_project",
            ],
            "decision_rules": [
                "Use query_unapproved_invoices first when invoice id is unknown.",
                "Call get_project only when project context is needed.",
            ],
        },
        {
            "intent": "triage_backlog",
            "tool_order": [
                "analyze_unapproved_invoices",
                "list_invoice_review_queues",
                "get_invoice_queue_page",
                "get_invoice_review_packet",
                "preflight_invoice_approval",
            ],
            "decision_rules": [
                "Use list_invoice_review_queues for a stored reviewer run and queue counts without full re-analysis.",
                "Use analyze_unapproved_invoices for a fresh analysis over window_days when no run exists or source data changed.",
                "After queues exist, page with get_invoice_queue_page then open get_invoice_review_packet per invoice.",
                "Call preflight_invoice_approval when an explicit policy gate is needed before human approval.",
                "Rely on analysis schema and policy checks before Vista enrichment unless investigating a specific field.",
            ],
        },
        {
            "intent": "deep_verify_vendor_and_amount",
            "tool_order": [
                "get_unapproved_invoice",
                "get_invoice_review_packet",
                "get_vendor",
                "get_purchase_order",
                "get_subcontract",
                "compare_invoice_to_commitments",
            ],
            "decision_rules": [
                "Use get_invoice_review_packet when run_id is available; otherwise get_unapproved_invoice.",
                "Call get_vendor for master data validation.",
                "If purchaseOrderId is present, call get_purchase_order; if subcontractId is present, call get_subcontract.",
                "Call compare_invoice_to_commitments for structured vendor/amount/line deltas (PO line sum uses quantity*itemPrice).",
            ],
        },
        {
            "intent": "resolve_duplicate_or_suspect_invoice_number",
            "tool_order": [
                "query_unapproved_invoices",
                "get_vendor",
                "get_unapproved_invoice",
            ],
            "decision_rules": [
                "Build filters on invoiceNumber, vendorId, and date or amount fields as needed.",
                "Call get_vendor to confirm vendor identity across candidate rows.",
                "Open each suspect row with get_unapproved_invoice for full detail.",
            ],
        },
        {
            "intent": "project_cost_context",
            "tool_order": [
                "get_project",
                "list_project_phases",
                "get_project_cost_history",
                "list_project_cost_history",
            ],
            "decision_rules": [
                "Resolve projectId from the invoice or review packet first.",
                "Use list_project_phases when phase-level coding matters.",
                "Use get_project_cost_history for one record by id; list_project_cost_history for paged queries.",
            ],
        },
        {
            "intent": "pre_approval_gate",
            "tool_order": [
                "get_invoice_review_packet",
                "preflight_invoice_approval",
                "capture_invoice_review_decision",
            ],
            "decision_rules": [
                "Load get_invoice_review_packet before preflight_invoice_approval.",
                "If preflight canApprove is true, record capture_invoice_review_decision; otherwise capture blockers from preflight output.",
            ],
        },
        {
            "intent": "audit_closeout",
            "tool_order": [
                "export_invoice_audit",
                "list_invoice_review_queues",
            ],
            "decision_rules": [
                "Call export_invoice_audit with run_id after reviewer decisions are recorded.",
                "Use list_invoice_review_queues only when rediscovering run_id or queue metadata.",
            ],
        },
        {
            "intent": "vendor_master_spot_check",
            "tool_order": [
                "get_vendor",
                "list_vendor_alternate_addresses",
                "get_vendor_alternate_address",
                "list_vendors",
            ],
            "decision_rules": [
                "Prefer get_vendor when vendorId is known from the invoice or vendorGroups.",
                "Use list_vendor_alternate_addresses or get_vendor_alternate_address for remit-to or address mismatches.",
                "Use list_vendors with filters when resolving vendor by code or name.",
            ],
        },
    ]

    return {"version": 4, "tools": nodes, "workflows": workflows}


"""MCP resources with dependency and workflow guidance."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import VistaSettings
from .api import get_api_metrics_snapshot
from .endpoint_registry import endpoint_dependency_graph
from .tool_factory import get_analysis_metrics_snapshot, get_tool_metrics_snapshot


def register_resources(mcp: FastMCP, settings: VistaSettings) -> None:
    """Register static resources describing ID dependencies and workflow order."""

    @mcp.resource(
        "vista://guides/dependencies",
        name="vista-dependency-guide",
        title="Vista Tool Dependency Guide",
        description="Maps required IDs to the tools that provide them.",
        mime_type="text/markdown",
    )
    def dependency_guide() -> str:
        return """# Vista Tool Dependency Guide

## Enterprise Context
- Scoped tools use `enterprise_id`.
- Resolution order: tool argument `enterprise_id` -> `VISTA_ENTERPRISE_ID`.
- If neither is available, set `VISTA_ENTERPRISE_ID` or pass `enterprise_id`.

## Vendor Dependencies
- `create_unapproved_invoices` needs `vendorId` and may use `vendorAlternateAddressId`.
- Get these from `get_vendor` or `list_vendors`.

## Company / Project Dependencies
- `create_unapproved_invoices` needs `companyId`.
- Use `get_enterprise` and optionally `get_project` / `list_projects` for project context.

## Typical ID Lookup Order
1. `list_vendors` (filter by vendor name/code)
2. `get_vendor` (confirm exact vendor and alternate address)
3. `get_enterprise` (confirm enterprise/company context)
4. `list_projects` or `get_project` (optional project/contract context)
5. `create_unapproved_invoices`

See also: `vista://guides/workflows`, `vista://guides/response-interpretation`, `vista://guides/filters`, `vista://guides/errors-and-edge-cases`, `vista://guides/bulk-retry`, `vista://guides/pagination-collections`, `vista://guides/scenarios`
"""

    @mcp.resource(
        "vista://schema/tool-graph",
        name="vista-tool-graph",
        title="Vista Tool Dependency Graph",
        description="Machine-readable tool dependency/IO graph for agent planning.",
        mime_type="application/json",
    )
    def tool_graph() -> str:
        graph = endpoint_dependency_graph(settings)
        return json.dumps(graph, indent=2)

    @mcp.resource(
        "vista://schema/planner",
        name="vista-tool-planner",
        title="Vista Tool Planner",
        description="Intent-based sequencing hints and decision rules for tool orchestration.",
        mime_type="application/json",
    )
    def tool_planner() -> str:
        graph = endpoint_dependency_graph(settings)
        planner = {
            "version": graph.get("version"),
            "workflows": graph.get("workflows", []),
            "notes": [
                "Prefer list tools to discover IDs before get/create calls.",
                "Use id_sources for resolving missing required inputs.",
                "Honor safe_to_retry when implementing retry loops in clients.",
            ],
        }
        return json.dumps(planner, indent=2)

    @mcp.resource(
        "vista://metrics/tool-usage",
        name="vista-tool-usage-metrics",
        title="Vista Tool Usage Metrics",
        description="In-memory counters and latency totals by tool.",
        mime_type="application/json",
    )
    def tool_usage_metrics() -> str:
        return json.dumps(get_tool_metrics_snapshot(), indent=2)

    @mcp.resource(
        "vista://metrics/analysis-ops",
        name="vista-analysis-ops-metrics",
        title="Vista Analysis Ops Metrics",
        description="In-memory counters for analysis runs, cache usage, and incremental runs.",
        mime_type="application/json",
    )
    def analysis_ops_metrics() -> str:
        return json.dumps(get_analysis_metrics_snapshot(), indent=2)

    @mcp.resource(
        "vista://metrics/api-transport",
        name="vista-api-transport-metrics",
        title="Vista API Transport Metrics",
        description="In-memory transport-level reliability counters (retries, network errors, partial collections).",
        mime_type="application/json",
    )
    def api_transport_metrics() -> str:
        return json.dumps(get_api_metrics_snapshot(), indent=2)

    @mcp.resource(
        "vista://ops/reliability-policy",
        name="vista-reliability-policy",
        title="Vista Reliability Policy",
        description="Active retry and canary rollback thresholds used for production hardening.",
        mime_type="application/json",
    )
    def reliability_policy() -> str:
        payload = {
            "retries": {
                "attempts": settings.transient_retry_attempts,
                "baseSeconds": settings.transient_retry_base_seconds,
                "maxSeconds": settings.transient_retry_max_seconds,
                "jitterSeconds": settings.transient_retry_jitter_seconds,
                "statusCodes": sorted(settings.retry_status_codes()),
            },
            "analysis": {
                "cacheBackend": settings.analysis_cache_backend,
                "cacheTtlSeconds": settings.analysis_cache_ttl_seconds,
                "failOnPartial": settings.analysis_fail_on_partial,
                "maxConcurrentRuns": settings.max_concurrent_analysis_runs,
                "maxConcurrentRequests": settings.max_concurrent_requests,
            },
            "canary": {
                "enabled": settings.reliability_canary_enabled,
                "sampleRate": settings.reliability_canary_sample_rate,
                "rollbackErrorRateThreshold": settings.reliability_rollback_error_rate_threshold,
                "rollbackP95MsThreshold": settings.reliability_rollback_p95_ms_threshold,
            },
        }
        return json.dumps(payload, indent=2)

    @mcp.resource(
        "vista://guides/workflows",
        name="vista-workflow-guide",
        title="Vista Workflow Guide",
        description="Recommended end-to-end workflows for common AP tasks.",
        mime_type="text/markdown",
    )
    def workflow_guide() -> str:
        return """# Vista Workflow Guide

## Create Unapproved Invoice (Recommended)
1. Resolve `enterprise_id`.
2. Resolve vendor (`list_vendors` -> `get_vendor`) to obtain `vendorId`.
3. Resolve project/company context (`get_enterprise`, optionally `get_project`).
4. Build `items` payload for `create_unapproved_invoices`.
5. Verify with `query_unapproved_invoices` or `get_unapproved_invoice`.

## Investigate Existing Invoice
1. `get_unapproved_invoice` or `query_unapproved_invoices`.
2. Use returned `vendorId` for `get_vendor`.
3. If needed, use returned project identifiers with `get_project`.

See also: `vista://guides/dependencies`, `vista://guides/response-interpretation`, `vista://guides/filters`, `vista://guides/errors-and-edge-cases`, `vista://guides/scenarios`
"""

    @mcp.resource(
        "vista://guides/response-interpretation",
        name="vista-response-interpretation-guide",
        title="Vista Response Interpretation Guide",
        description="Explains response shapes and how to reuse returned values in follow-up calls.",
        mime_type="text/markdown",
    )
    def response_interpretation_guide() -> str:
        return """# Vista Response Interpretation Guide

## List and Query Tools
- `list_enterprises`, `list_vendors`, `list_projects`, `query_unapproved_invoices` return:
  - `items` (array)
  - `pageSize`
  - `currentPage`
- Use `limit` and `page` to continue pagination.

### Useful Values To Extract
- Enterprises: `items[].id` for `enterprise_id`.
- Vendors: `items[].id`, `items[].alternateAddresses[].id` for `vendorAlternateAddressId`.
- Projects: `items[].id`, `items[].contracts[]` for contract context.
- Invoices: `items[].id`, `items[].vendorId`, `items[].purchaseOrderId`, `items[].subcontractId`, `items[].invoiceNumber`.

## Get-By-ID Tools
- `get_enterprise`, `get_vendor`, `get_project`, `get_unapproved_invoice` return one `item`.
- Reuse `item.id` and related identifiers for downstream tools.

## Create Invoices
- `create_unapproved_invoices` returns `items[]` per input row.
- Each row may include:
  - `statusCode`
  - `action`
  - `message`
  - `item` (created invoice payload on success)
- Partial success is possible. Inspect each row independently.

## Health
- `health_ready` and `health_alive` return `Status`, `Description`, and `Exception`.
- Treat `Status` as the primary healthy/unhealthy indicator and use `Exception` for diagnostics.
"""

    @mcp.resource(
        "vista://guides/filters",
        name="vista-filters-guide",
        title="Vista Filter And Query Guide",
        description="Documents filter structure, common operators, and example query patterns.",
        mime_type="text/markdown",
    )
    def filter_guide() -> str:
        return """# Vista Filter And Query Guide

## Filter Shape
Use a list of filter objects:
- `field`: string
- `operator`: string
- `values`: array of strings

Applies to: `list_enterprises`, `list_vendors`, `list_projects`, `query_unapproved_invoices`.

## Common Operators
Typical operators include `eq`, `contains`, and `in`.
Operator support depends on API behavior and entity field compatibility.

## Example Filters

### Vendors
```json
[
  {"field": "name", "operator": "contains", "values": ["Acme"]},
  {"field": "vendorCode", "operator": "eq", "values": ["V-1001"]}
]
```

### Projects
```json
[
  {"field": "job", "operator": "eq", "values": ["J-2205"]},
  {"field": "companyCode", "operator": "eq", "values": ["01"]}
]
```

### Unapproved Invoices
```json
[
  {"field": "invoiceNumber", "operator": "contains", "values": ["INV-2026"]},
  {"field": "vendorId", "operator": "eq", "values": ["00000000-0000-0000-0000-000000000000"]}
]
```

## Pagination
- Use `limit` and `page` in list/query tools.
- Read `currentPage` and `pageSize` in responses to drive iteration.
"""

    @mcp.resource(
        "vista://guides/errors-and-edge-cases",
        name="vista-errors-and-edge-cases-guide",
        title="Vista Errors And Edge Cases Guide",
        description="How to interpret tool failures, API errors, and partial-success outcomes.",
        mime_type="text/markdown",
    )
    def errors_and_edge_cases_guide() -> str:
        return """# Vista Errors And Edge Cases Guide

## Missing Enterprise Context
- If `enterprise_id` is missing and `VISTA_ENTERPRISE_ID` is not set, scoped tools fail.
- Fix by setting `VISTA_ENTERPRISE_ID` or passing `enterprise_id` per call.

## API Errors (4xx / 5xx)
- Tool failures can include HTTP status and response details.
- Typical checks:
  - `401`/`403`: auth config (`VISTA_BEARER_TOKEN` or `VISTA_API_KEY`)
  - `404`: wrong ID or enterprise scope mismatch
  - `4xx`: request validation or unsupported filter/operator
  - `5xx`: upstream service issue

## Create Partial Success
- `create_unapproved_invoices` is row-based. Some rows can succeed while others fail.
- Inspect every `items[]` entry:
  - success row: useful `item.id`
  - failure row: `statusCode`/`message` describe correction needed
- Retry only failed rows after fixing input.

## Validation Errors
- Invalid UUID/date formats or missing required fields raise validation errors.
- Correct payload shape and retry.

## Empty List Results
- `items: []` is valid for list/query tools.
- Adjust filters, page, limit, or enterprise scope.
"""

    @mcp.resource(
        "vista://guides/bulk-retry",
        name="vista-bulk-retry-guide",
        title="Bulk Write Retry And Idempotency",
        description="How to retry only failed bulk rows and use stable correlation keys.",
        mime_type="text/markdown",
    )
    def bulk_retry_guide() -> str:
        return """# Bulk Write Retry And Idempotency

## Row-Independent Outcomes
- Bulk tools (`create_unapproved_invoices`, `create_daily_production`, etc.) return one result object per input row.
- Successful rows include `item` with created ids; failed rows include `statusCode`, `message`, and may omit `item`.

## Retry Only Failed Rows
- Do not resubmit the full batch after a partial failure unless you intentionally want duplicate creates.
- Identify failed indices from the response, fix payload fields, and call the bulk tool again with **only** those items.

## Stable Client Keys For Agents
- When an agent retries, pass a deterministic `x-correlation-id` (or rely on `VISTA_CORRELATION_ID`) so support can trace a single logical operation in Vista logs.
- For human review, correlate retries using natural keys in your payload: `invoiceNumber` + `vendorId` + `companyId` should uniquely identify an intended invoice line before duplicate submission.

## Preflight Before Retry
- Call `validate_<tool_name>_request` for the same bulk tool to catch missing fields before the second POST.

See also: `vista://guides/errors-and-edge-cases`, bulk preflight tools in README.
"""

    @mcp.resource(
        "vista://guides/pagination-collections",
        name="vista-pagination-collections-guide",
        title="Full-List Pagination For Unapproved Invoices",
        description="Walking all pages safely vs manual paging.",
        mime_type="text/markdown",
    )
    def pagination_collections_guide() -> str:
        return """# Full-List Pagination (Unapproved Invoices)

## Preferred: collect_unapproved_invoices_pages
- MCP tool that wraps `query_unapproved_invoices` with `VistaApiClient.collect_list_pages`.
- Parameters: `page_size` (capped, max 100), `max_pages`, optional `filters`, `order_by`, `includes`.
- Response includes `items` (concatenated), `pagesFetched`, `partial` (true if a page failed mid-collection), and `errors` per failed page.
- Use when you need the **entire** open backlog matching filters, not a single page.

## Manual Pattern
- Call `query_unapproved_invoices` with `limit` and `page` starting at 1.
- Increment `page` until `items` length is less than `limit` or `currentPage` indicates the last page.

## Partial Results
- If `partial` is true on `collect_unapproved_invoices_pages`, treat the item list as incomplete; fix upstream errors or reduce concurrency and retry.

See also: `vista://guides/filters`.
"""

    @mcp.resource(
        "vista://guides/scenarios",
        name="vista-scenarios-guide",
        title="Vista Scenarios Quick Reference",
        description="Maps user intents to prompts, resources, and recommended tool order.",
        mime_type="text/markdown",
    )
    def scenarios_guide() -> str:
        return """# Vista Scenarios Quick Reference

## Create Invoice
- Prompt: `create_unapproved_invoice_workflow`
- Read first: `vista://guides/dependencies`
- Tool order: `list_vendors` -> `get_vendor` -> `get_enterprise` -> `create_unapproved_invoices`

## Discover Enterprise And Vendor Before Create
- Prompt: `discover_enterprise_and_vendor_before_create_workflow`
- Read first: `vista://guides/filters`
- Tool order: `list_enterprises` -> `list_vendors` -> `get_vendor` -> `get_enterprise` -> `create_unapproved_invoices`

## Investigate Existing Invoice
- Prompt: `investigate_invoice_workflow`
- Read first: `vista://guides/response-interpretation`
- Tool order: `get_unapproved_invoice` -> `get_vendor` -> `get_project` (if project IDs are present)

## Filter And Enrich Invoice List
- Prompt: `filter_and_enrich_invoices_workflow`
- Read first: `vista://guides/filters`
- Tool order: `query_unapproved_invoices` -> `get_vendor` -> `get_project` (optional)

## Handle Partial Create Failures
- Prompt: `handle_invoice_create_partial_failure_workflow`
- Read first: `vista://guides/errors-and-edge-cases`
- Tool order: `create_unapproved_invoices` -> inspect per-row result -> retry failed rows only

## Triage Backlog (analysis first)
- Prompt: `triage_backlog_workflow`
- Read first: `vista://schema/planner` (intent `triage_backlog`)
- Tool order: `analyze_unapproved_invoices` or `list_invoice_review_queues` -> `get_invoice_queue_page` -> `get_invoice_review_packet` -> optional `preflight_invoice_approval`

## Deep Verify Vendor And Amounts
- Prompt: `deep_verify_vendor_and_amount_workflow`
- Read first: `vista://guides/response-interpretation`
- Tool order: `get_unapproved_invoice` or `get_invoice_review_packet` -> `get_vendor` -> `get_purchase_order` / `get_subcontract` (if IDs present) -> `compare_invoice_to_commitments`

## Resolve Duplicate Or Suspect Invoice Number
- Prompt: `resolve_duplicate_or_suspect_invoice_number_workflow`
- Read first: `vista://guides/filters`
- Tool order: `query_unapproved_invoices` -> `get_vendor` -> `get_unapproved_invoice` (per candidate)

## Project Cost Context
- Prompt: `project_cost_context_workflow`
- Read first: `vista://guides/response-interpretation`
- Tool order: `get_project` -> optional `list_project_phases` -> `get_project_cost_history` / `list_project_cost_history`

## Pre-Approval Gate
- Prompt: `pre_approval_gate_workflow`
- Read first: `vista://schema/planner` (intent `pre_approval_gate`)
- Tool order: `get_invoice_review_packet` -> `preflight_invoice_approval` -> `capture_invoice_review_decision`

## Audit Closeout
- Prompt: `audit_closeout_workflow`
- Read first: `vista://guides/errors-and-edge-cases` (traceability)
- Tool order: `export_invoice_audit` (optional `list_invoice_review_queues` to discover `run_id`)

## Vendor Master Spot Check
- Prompt: `vendor_master_spot_check_workflow`
- Read first: `vista://guides/filters`
- Tool order: `get_vendor` or `list_vendors` -> `list_vendor_alternate_addresses` / `get_vendor_alternate_address`
"""


"""MCP resources with dependency and workflow guidance."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def register_resources(mcp: MCPServer) -> None:
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

See also: `vista://guides/workflows`, `vista://guides/response-interpretation`, `vista://guides/filters`, `vista://guides/errors-and-edge-cases`, `vista://guides/scenarios`
"""

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
"""


"""MCP prompts that describe common multi-tool workflows."""

from __future__ import annotations

from pydantic import Field

from mcp.server.mcpserver import MCPServer


def register_prompts(mcp: MCPServer) -> None:
    """Register prompts that help clients choose and sequence tools correctly."""

    @mcp.prompt(
        name="create_unapproved_invoice_workflow",
        title="Create Unapproved Invoice Workflow",
        description="Guides tool ordering and required IDs for invoice creation.",
    )
    def create_unapproved_invoice_workflow(
        vendor_name: str = Field(description="Vendor name or code to resolve first"),
        invoice_number: str = Field(description="Invoice number to create"),
        include_project_lookup: bool = Field(
            default=True,
            description="Whether to resolve project context before creation",
        ),
    ) -> str:
        steps = [
            "1) Resolve enterprise context: pass enterprise_id or rely on VISTA_ENTERPRISE_ID.",
            f"2) Resolve vendor '{vendor_name}': call list_vendors (filter by name/code), then get_vendor.",
            "3) Resolve company context: call get_enterprise.",
        ]
        if include_project_lookup:
            steps.append("4) Optional project context: call list_projects or get_project.")
            steps.append(
                "5) Call create_unapproved_invoices with items including companyId, vendorId, and invoice fields."
            )
        else:
            steps.append(
                "4) Call create_unapproved_invoices with items including companyId, vendorId, and invoice fields."
            )

        steps.append(f"Target invoice number: {invoice_number}.")
        steps.append("Verify result with query_unapproved_invoices or get_unapproved_invoice.")
        return "\n".join(steps)

    @mcp.prompt(
        name="investigate_invoice_workflow",
        title="Investigate Invoice With Related Entities",
        description="Looks up invoice first, then traverses vendor/project dependencies.",
    )
    def investigate_invoice_workflow(
        invoice_id: str = Field(description="Unapproved invoice UUID"),
    ) -> str:
        return (
            "1) Call get_unapproved_invoice with the provided invoice_id.\n"
            "2) From the response, extract vendorId and call get_vendor.\n"
            "3) If project identifiers are present, call get_project for context.\n"
            "4) If you need a wider list, call query_unapproved_invoices with filters."
            f"\nTarget invoice id: {invoice_id}"
        )

    @mcp.prompt(
        name="filter_and_enrich_invoices_workflow",
        title="Filter Invoices And Enrich With Vendor Project",
        description="Query invoices first, then enrich selected rows with vendor and project lookups.",
    )
    def filter_and_enrich_invoices_workflow(
        filter_hint: str = Field(
            default="invoiceNumber or vendorId",
            description="Natural-language hint for the filter criteria to apply.",
        ),
        include_project_enrichment: bool = Field(
            default=True,
            description="Whether to enrich selected invoices with project context in addition to vendor context.",
        ),
    ) -> str:
        steps = [
            "1) Resolve enterprise context: pass enterprise_id or rely on VISTA_ENTERPRISE_ID.",
            "2) Build query_unapproved_invoices filters using field/operator/values based on the filter hint.",
            "3) Call query_unapproved_invoices with optional limit/page for pagination.",
            "4) For selected results, call get_vendor using each item's vendorId.",
        ]
        if include_project_enrichment:
            steps.append(
                "5) If purchaseOrderId or subcontractId is present, call get_project to enrich project context."
            )
            steps.append("6) Summarize invoice, vendor, and project insights.")
        else:
            steps.append("5) Summarize invoice and vendor insights.")
        steps.append(f"Filter hint: {filter_hint}.")
        steps.append("See vista://guides/filters and vista://guides/response-interpretation for examples.")
        return "\n".join(steps)

    @mcp.prompt(
        name="handle_invoice_create_partial_failure_workflow",
        title="Handle Partial Failure On Invoice Creation",
        description="Explains how to inspect per-item create results and recover from failures.",
    )
    def handle_invoice_create_partial_failure_workflow() -> str:
        return (
            "1) Call create_unapproved_invoices with one or more items.\n"
            "2) Inspect each response entry in items[] (statusCode, action, message, item).\n"
            "3) Treat each row independently: some rows may succeed while others fail.\n"
            "4) For failed rows, report the row index or invoice number and the message.\n"
            "5) For successful rows, use item.id to confirm with get_unapproved_invoice if needed.\n"
            "6) Correct failed payload fields and retry only failed rows when appropriate.\n"
            "See vista://guides/errors-and-edge-cases and vista://guides/response-interpretation."
        )

    @mcp.prompt(
        name="discover_enterprise_and_vendor_before_create_workflow",
        title="Discover Enterprise And Vendor Before Invoice Create",
        description="Find enterprise and vendor IDs first, then compose create_unapproved_invoices payload.",
    )
    def discover_enterprise_and_vendor_before_create_workflow(
        vendor_name_or_code: str = Field(description="Vendor name or vendor code used for lookup."),
        enterprise_name_hint: str | None = Field(
            default=None,
            description="Optional enterprise name hint when enterprise_id is not already known.",
        ),
    ) -> str:
        enterprise_step = (
            "1) If enterprise_id is unknown, call list_enterprises"
            + (f" with a filter hint '{enterprise_name_hint}'." if enterprise_name_hint else ".")
            + " Select the correct items[].id."
        )
        return (
            f"{enterprise_step}\n"
            f"2) Call list_vendors with filters for '{vendor_name_or_code}', then call get_vendor for exact match.\n"
            "3) Extract vendorId and optional alternateAddresses[].id for vendorAlternateAddressId.\n"
            "4) Call get_enterprise to confirm company context and required IDs.\n"
            "5) Build create_unapproved_invoices items with companyId, vendorId, and invoice fields, then submit.\n"
            "See vista://guides/dependencies, vista://guides/filters, and vista://guides/response-interpretation."
        )


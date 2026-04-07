"""MCP prompts that describe common multi-tool workflows."""

from __future__ import annotations

from pydantic import Field

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
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

    @mcp.prompt(
        name="triage_backlog_workflow",
        title="Triage Unapproved Invoice Backlog",
        description=(
            "Policy and schema review via analysis, then queue paging and packets; optional preflight before Vista enrichment."
        ),
    )
    def triage_backlog_workflow(
        enterprise_id: int | None = Field(
            default=None,
            description="Enterprise id or rely on VISTA_ENTERPRISE_ID.",
        ),
        prefer_stored_run: bool = Field(
            default=False,
            description="If true, start with list_invoice_review_queues; otherwise prefer analyze_unapproved_invoices.",
        ),
        window_days: int = Field(
            default=30,
            description="When using analyze_unapproved_invoices, history window in days.",
        ),
    ) -> str:
        start = (
            "1) list_invoice_review_queues (enterprise_id) to create or reuse a run and get queue counts."
            if prefer_stored_run
            else (
                f"1) analyze_unapproved_invoices (enterprise_id, window_days={window_days}) for fresh analysis and queues."
            )
        )
        return "\n".join(
            [
                "Resolve enterprise: pass enterprise_id or VISTA_ENTERPRISE_ID.",
                start,
                "2) get_invoice_queue_page with run_id and queue name; repeat with nextCursor until done.",
                "3) For each item, get_invoice_review_packet (run_id, invoice_id) for findings and risk.",
                "4) Optionally preflight_invoice_approval before any approval narrative.",
                "5) Defer Vista get_* until you need to validate a specific field against ERP.",
                "See vista://schema/planner (intent triage_backlog), vista://guides/filters.",
                f"enterprise_id hint: {enterprise_id}",
            ]
        )

    @mcp.prompt(
        name="deep_verify_vendor_and_amount_workflow",
        title="Deep Verify Vendor And Commitment Amounts",
        description="Invoice or packet, vendor master data, then PO or subcontract; compare amounts in reasoning.",
    )
    def deep_verify_vendor_and_amount_workflow(
        invoice_id: str = Field(description="Unapproved invoice UUID."),
        run_id: str | None = Field(
            default=None,
            description="Optional reviewer run id; if set, use get_invoice_review_packet first.",
        ),
    ) -> str:
        packet_step = (
            f"1) get_invoice_review_packet (run_id={run_id}, invoice_id={invoice_id})."
            if run_id
            else f"1) get_unapproved_invoice (invoice_id={invoice_id})."
        )
        return "\n".join(
            [
                "Resolve enterprise context first.",
                packet_step,
                "2) get_vendor using vendorId from the invoice or packet.",
                "3) If purchaseOrderId is set, get_purchase_order; if subcontractId is set, get_subcontract.",
                "4) Compare invoice amount and lines to PO or subcontract totals in reasoning (no automated compare tool yet).",
                "See vista://schema/planner (intent deep_verify_vendor_and_amount).",
            ]
        )

    @mcp.prompt(
        name="resolve_duplicate_or_suspect_invoice_number_workflow",
        title="Resolve Duplicate Or Suspect Invoice Numbers",
        description="Query open backlog, confirm vendor, open each candidate invoice.",
    )
    def resolve_duplicate_or_suspect_invoice_number_workflow(
        invoice_number_hint: str = Field(description="Invoice number or fragment to search."),
        vendor_id: str | None = Field(
            default=None,
            description="Optional vendor UUID to narrow candidates.",
        ),
    ) -> str:
        vendor_line = (
            f"2) Add filter vendorId eq [{vendor_id}] if narrowing." if vendor_id else "2) Add vendor filters if known."
        )
        return "\n".join(
            [
                "1) query_unapproved_invoices with filters on invoiceNumber (contains or eq) and date or amount as needed.",
                vendor_line,
                "3) get_vendor for each distinct vendorId in results.",
                "4) get_unapproved_invoice for each candidate id to compare full payloads.",
                "See vista://guides/filters and vista://schema/planner (intent resolve_duplicate_or_suspect_invoice_number).",
                f"Search hint: {invoice_number_hint}",
            ]
        )

    @mcp.prompt(
        name="project_cost_context_workflow",
        title="Project And Cost History Context For An Invoice",
        description="Project detail, optional phases, then cost history list or get by id.",
    )
    def project_cost_context_workflow(
        project_id: str = Field(description="Project UUID from invoice or packet."),
        cost_history_id: str | None = Field(
            default=None,
            description="If you already have a project cost history id, call get_project_cost_history directly.",
        ),
    ) -> str:
        if cost_history_id:
            tail = (
                f"2) get_project_cost_history (id={cost_history_id}).\n"
                "3) Optionally list_project_cost_history with filters for broader history."
            )
        else:
            tail = (
                "2) list_project_phases if phase coding matters.\n"
                "3) list_project_cost_history with filters or get_project_cost_history when you have a specific id."
            )
        return "\n".join(
            [
                f"1) get_project (id={project_id}).",
                tail,
                "See vista://schema/planner (intent project_cost_context).",
            ]
        )

    @mcp.prompt(
        name="pre_approval_gate_workflow",
        title="Pre-Approval Policy Gate And Decision",
        description="Packet, preflight, then capture decision with explicit branch on canApprove.",
    )
    def pre_approval_gate_workflow(
        run_id: str = Field(description="Reviewer analysis run id."),
        invoice_id: str = Field(description="Invoice UUID within the run."),
    ) -> str:
        return "\n".join(
            [
                f"1) get_invoice_review_packet (run_id={run_id}, invoice_id={invoice_id}).",
                f"2) preflight_invoice_approval (run_id={run_id}, invoice_id={invoice_id}).",
                "3) If canApprove, call capture_invoice_review_decision with approve or equivalent.",
                "4) If not canApprove, record decision with rationale from blockingIssues or document fix steps; do not treat as approved.",
                "See vista://schema/planner (intent pre_approval_gate).",
            ]
        )

    @mcp.prompt(
        name="audit_closeout_workflow",
        title="Audit Export After Review",
        description="Export run metadata and decisions after review is complete.",
    )
    def audit_closeout_workflow(
        run_id: str = Field(description="Reviewer run id to export."),
    ) -> str:
        return "\n".join(
            [
                f"1) export_invoice_audit (run_id={run_id}) for run metadata, totals, and reviewer decisions.",
                "2) Use list_invoice_review_queues only if run_id was unknown and you need to discover runs.",
                "See vista://schema/planner (intent audit_closeout).",
            ]
        )

    @mcp.prompt(
        name="vendor_master_spot_check_workflow",
        title="Vendor Master Data Spot Check",
        description="Validate vendor record and alternate addresses for high-risk or mismatched remit context.",
    )
    def vendor_master_spot_check_workflow(
        vendor_id: str | None = Field(
            default=None,
            description="Vendor UUID when known.",
        ),
        vendor_code_hint: str | None = Field(
            default=None,
            description="When vendor_id unknown, filter list_vendors by vendorCode or name.",
        ),
    ) -> str:
        if vendor_id:
            steps = [
                f"1) get_vendor (id={vendor_id}).",
                "2) list_vendor_alternate_addresses or get_vendor_alternate_address if remit-to does not match invoice.",
            ]
        else:
            steps = [
                f"1) list_vendors with filters for code or name (hint: {vendor_code_hint}).",
                "2) get_vendor for the chosen id.",
                "3) list_vendor_alternate_addresses or get_vendor_alternate_address as needed.",
            ]
        steps.append("See vista://guides/filters and vista://schema/planner (intent vendor_master_spot_check).")
        return "\n".join(steps)

    @mcp.prompt(
        name="bulk_write_retry_workflow",
        title="Bulk Write Partial Failure And Retry",
        description="Retry only failed bulk rows with preflight and stable correlation.",
    )
    def bulk_write_retry_workflow(
        bulk_tool_name: str = Field(
            default="create_unapproved_invoices",
            description="Bulk Vista tool that returned partial success.",
        ),
    ) -> str:
        return "\n".join(
            [
                "1) Read each row in the bulk response items[].",
                "2) For rows without a successful item.id, capture statusCode and message.",
                "3) Call validate_<tool_name>_request (e.g. validate_create_unapproved_invoices_request) for corrected rows only.",
                f"4) Call {bulk_tool_name} again with only failed/corrected items (not the whole batch).",
                "5) Optional: set correlation_id or VISTA_CORRELATION_ID for traceability across retries.",
                "See vista://guides/bulk-retry and vista://guides/errors-and-edge-cases.",
            ]
        )


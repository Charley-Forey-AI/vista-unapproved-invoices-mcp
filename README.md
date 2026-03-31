# Vista MCP Server

MCP server exposing Vista Enterprise, Company, Contract, Customer, Project, PO, AP, Vendor, and Health endpoints.

## Endpoint Coverage

The server registers tools from a central endpoint registry (`server/endpoint_registry.py`) and validates response payloads with generated schema adapters (`server/generated_models.py`).

Covered endpoint families:

- Enterprise (`get_enterprise`, `list_enterprises`, optional `test_list_enterprises`)
- Company, Contract, Customer (`get_*`, `list_*`)
- Project (`get_project`, `list_projects`)
- Project Cost Entry (`create_daily_production`, `get_daily_production_action`, `get_unposted_daily_production`, `list_unposted_daily_production`)
- Project Cost History (`get_project_cost_history`, `list_project_cost_history`)
- Project Phase (`get_project_phase`, `list_project_phases`)
- Purchase Order (`create_purchase_orders`, `get_purchase_order`, `get_purchase_order_action`, `get_unposted_purchase_order`, `list_purchase_orders`, `list_unposted_purchase_orders`)
- Unapproved Invoice (`create_unapproved_invoices`, `get_unapproved_invoice`, `get_unapproved_invoice_action`, `query_unapproved_invoices`)
- Analysis (`analyze_unapproved_invoices`) for read-only portfolio triage and reviewer-ready risk buckets (deleted invoices are excluded; compact output is default for large backlogs)
- Review workflow tools (`list_invoice_review_queues`, `get_invoice_queue_page`, `get_invoice_review_packet`, `capture_invoice_review_decision`, `preflight_invoice_approval`, `export_invoice_audit`)
- Sales Tax, Schedule of Values, Standard Cost Type, Standard Phase (`get_*`, `list_*`)
- Subcontract (`get_subcontract`, `list_subcontracts`)
- Vendor + Vendor Alternate Address (`get_*`, `list_*`)
- Health (`health_ready`, optional `health_alive`)

## Organization And Conventions

- Registry-first design: endpoint metadata (method/path/schema refs/tool names) lives in `server/endpoint_registry.py`.
- Generic execution path: `VistaApiClient.call_endpoint()` handles path interpolation, `orderBy`/`orderByAsc`/`limit`/`page`/`includes`, bulk request bodies, and health auth bypass.
- Shared tool factory: `server/tool_factory.py` registers tools by endpoint kind (`get`, `list`, `bulk`, `health`) with consistent signatures.
- Validation:
  - list/query requests normalize to `{ filters: [] }` using `QueryFilter`.
  - bulk requests normalize to `{ items: [...] }` and use typed request models generated from OpenAPI schema refs.
  - responses are validated against generated schema-specific adapters from `server/generated_models.py`.
- Output modes:
  - each tool accepts `output=raw|normalized|both` (default `raw`)
  - `normalized` returns snake_case data with `tool_name`, `schema_ref`, and canonical metadata for agent chaining
- Preflight validation:
  - each bulk write tool has a paired preflight tool named `validate_<tool>_request`
  - preflight validates required fields, policy gates, enterprise context, and typed request contract without calling Vista
- Feature flags:
  - `VISTA_INCLUDE_TEST_ENTERPRISE_TOOL` controls `test_list_enterprises`
  - `VISTA_INCLUDE_HEALTH_ALIVE_TOOL` controls `health_alive`
- Machine-readable planning:
  - `vista://schema/tool-graph` exposes dependencies with `requires`, `produces`, `prerequisites`, `id_sources`, `safe_to_retry`.
  - `vista://schema/planner` provides intent-based tool order + decision rules.
- Observability:
  - `vista://metrics/tool-usage` exposes in-memory call, success/failure, and latency counters by tool.
- Permission-aware behavior:
  - `list_enterprises`/`test_list_enterprises` may require elevated permissions.
  - when those calls are forbidden (403) and `VISTA_ENTERPRISE_ID` is configured, the server falls back to `get_enterprise`.

## Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/)

## Install

From the repository root:

```bash
uv sync
```

## Configure environment

Copy `.env.example` to `.env` and populate values:

- Required: `VISTA_API_BASE_URL`
  - Use the API host root (for example `https://integrations-qa.centralus.cloudapp.azure.com`).
  - Do not include a trailing `/api/v1`; tool paths already append `/api/v1/...`.
- Required auth mode: set `VISTA_AUTH_MODE` to one of:
  - `static`: use `VISTA_BEARER_TOKEN` or `VISTA_API_KEY`
  - `delegated`: require per-request actor token validation (no static fallback)
  - `hybrid`: prefer per-request bearer token, fallback to static credentials
  - `server-managed`: use `VISTA_CLIENT_ID`/`VISTA_CLIENT_SECRET` + `VISTA_REFRESH_TOKEN` and refresh TID access tokens in memory
- Optional delegated strategy:
  - `VISTA_AUTH_STRATEGY=delegated_passthrough` (default): forward actor token directly to Vista
  - `VISTA_AUTH_STRATEGY=token_exchange`: exchange actor token for Vista token before Vista calls (with in-memory cache and expiry-aware reuse)
- Required for `static`: one of `VISTA_BEARER_TOKEN` or `VISTA_API_KEY`
- Required for `server-managed`:
  - `VISTA_CLIENT_ID`
  - `VISTA_CLIENT_SECRET`
  - `VISTA_REFRESH_TOKEN`
  - `VISTA_AUTH_ISSUER` (or explicit `VISTA_TOKEN_URL`)
- Optional for `server-managed`:
  - `VISTA_ACCESS_TOKEN` (seed token used until near expiry/401)
  - `VISTA_SCOPE` (space-delimited, example `openid vista_agent`)
- Required for `delegated`/`hybrid`:
  - `VISTA_AUTH_ISSUER`
  - `VISTA_AUTH_JWKS_URL`
  - `VISTA_AUTH_RESOURCE_SERVER_URL`
- Optional for delegated validation:
  - `VISTA_AUTH_AUDIENCE`
  - `VISTA_AUTH_REQUIRED_SCOPES` (space- or comma-delimited)
- Optional for `token_exchange` strategy:
  - `VISTA_TOKEN_EXCHANGE_TOKEN_URL` (otherwise uses `VISTA_TOKEN_URL` or `<VISTA_AUTH_ISSUER>/oauth/token`)
  - `VISTA_TOKEN_EXCHANGE_SCOPE`
  - `VISTA_TOKEN_EXCHANGE_AUDIENCE`
- Optional: `VISTA_ENTERPRISE_ID` to avoid passing `enterprise_id` on every scoped request
- Optional: `VISTA_MAX_BULK_ITEMS` to cap bulk create payload size (default `100`)
- Optional: `VISTA_MAX_BATCH_SIZE` override for bulk create cap (takes precedence)
- Optional: `VISTA_READ_ONLY_MODE=true` to disable all write/bulk tools
- Optional: `VISTA_WRITE_ENABLED_DOMAINS` allowlist for writes (example `ap,po,jc`)
- Optional transient retry controls:
  - `VISTA_TRANSIENT_RETRY_ATTEMPTS` (default `3`)
  - `VISTA_TRANSIENT_RETRY_BASE_SECONDS` (default `0.75`)
  - `VISTA_TRANSIENT_RETRY_MAX_SECONDS` (default `8.0`)
  - `VISTA_TRANSIENT_RETRY_JITTER_SECONDS` (default `0.25`)
  - `VISTA_TRANSIENT_RETRY_STATUS_CODES` (default `429,500,502,503,504`)
- Optional request timeout and connection controls:
  - `VISTA_REQUEST_TIMEOUT_SECONDS` (default `45`)
  - `VISTA_REQUEST_CONNECT_TIMEOUT_SECONDS` (default `10`)
  - `VISTA_REQUEST_READ_TIMEOUT_SECONDS` (default `45`)
  - `VISTA_REQUEST_WRITE_TIMEOUT_SECONDS` (default `30`)
  - `VISTA_REQUEST_POOL_TIMEOUT_SECONDS` (default `10`)
  - `VISTA_REQUEST_MAX_CONNECTIONS` (default `100`)
  - `VISTA_REQUEST_MAX_KEEPALIVE_CONNECTIONS` (default `40`)
  - `VISTA_MAX_CONCURRENT_REQUESTS` (default `32`)
  - `VISTA_MAX_CONCURRENT_ANALYSIS_RUNS` (default `4`)
- Optional unapproved invoice analysis controls:
  - `VISTA_ANALYSIS_DEFAULT_WINDOW_DAYS` (default `365`)
  - `VISTA_ANALYSIS_DEFAULT_TOP_N` (default `5`)
  - `VISTA_ANALYSIS_PAGE_SIZE` (default `100`)
  - `VISTA_ANALYSIS_MAX_PAGES` (default `10`)
  - `VISTA_ANALYSIS_STALE_DAYS` (default `30`)
  - `VISTA_ANALYSIS_HIGH_AMOUNT_THRESHOLD` (default `50000`)
  - `VISTA_ANALYSIS_DUPLICATE_AMOUNT_DELTA` (default `0.01`)
  - `VISTA_ANALYSIS_POLICY_PROFILE` (`standard|strict|lenient`, default `standard`)
  - `VISTA_ANALYSIS_CACHE_TTL_SECONDS` (default `180`)
  - `VISTA_ANALYSIS_CACHE_BACKEND` (`memory|redis`, default `memory`)
  - `VISTA_ANALYSIS_CACHE_PREFIX` (default `vista:analysis`)
  - `VISTA_ANALYSIS_FAIL_ON_PARTIAL` (default `false`)
  - `VISTA_REDIS_URL` (required when `VISTA_ANALYSIS_CACHE_BACKEND=redis`)
- Optional token and JWKS timeout controls:
  - `VISTA_TOKEN_HTTP_TIMEOUT_SECONDS` (default `20`)
  - `VISTA_AUTH_JWKS_TIMEOUT_SECONDS` (default `15`)
  - `VISTA_TOKEN_EXCHANGE_CACHE_TTL_SECONDS` (default `300`)
  - `VISTA_TOKEN_EXCHANGE_REFRESH_SKEW_SECONDS` (default `30`)
- Optional canary rollout guardrails:
  - `VISTA_RELIABILITY_CANARY_ENABLED` (default `false`)
  - `VISTA_RELIABILITY_CANARY_SAMPLE_RATE` (default `0.1`)
  - `VISTA_RELIABILITY_ROLLBACK_ERROR_RATE_THRESHOLD` (default `0.05`)
  - `VISTA_RELIABILITY_ROLLBACK_P95_MS_THRESHOLD` (default `4000`)
- `analyze_unapproved_invoices` response controls:
  - `detail_level=compact|full` (default `compact`)
  - `max_items_per_bucket` (compact mode queue sample cap, default `25`)
  - `max_vendor_groups` (compact mode vendor rollup cap, default `25`)
  - `incremental_since` (ISO timestamp watermark for incremental analysis mode)

## Queue-First Review Pattern

- Run `list_invoice_review_queues` to create a run and receive queue counts.
- Page a queue with `get_invoice_queue_page` using `nextCursor`.
- Pull single-invoice packet via `get_invoice_review_packet`.
- Record reviewer outcome with `capture_invoice_review_decision`.
- Gate action readiness using `preflight_invoice_approval`.
- Export traceability report using `export_invoice_audit`.
- Health tools do not require auth

## Reliability Runbook (Production)

- **Degraded analysis handling**: if `collection.partial=true`, treat response as degraded and retry before taking approval action.
- **Strict completeness mode**: set `VISTA_ANALYSIS_FAIL_ON_PARTIAL=true` or pass `require_complete=true` to fail fast instead of returning partial analysis.
- **Scale-safe cache mode**: for multi-instance deployments set `VISTA_ANALYSIS_CACHE_BACKEND=redis` and configure `VISTA_REDIS_URL`.
- **Rollback guardrails**: monitor `vista://metrics/api-transport`, `vista://metrics/analysis-ops`, and `vista://metrics/tool-usage`; revert canary when error rate or p95 exceeds `vista://ops/reliability-policy` thresholds.
- **Retry tuning path**: increase `VISTA_TRANSIENT_RETRY_ATTEMPTS` and timeout settings in small increments, then validate using canary metrics before global rollout.

## Run

From the repository root:

```bash
uv run vista-mcp-server
```

Or through the script entrypoint:

```bash
uv run vista-mcp-server
```

## Transport modes

### STDIO (default)

- Keep `VISTA_MCP_TRANSPORT=stdio` (or unset it)
- Best for local MCP clients that launch the server process directly

### Streamable HTTP

Set:

- `VISTA_MCP_TRANSPORT=streamable-http`
- `VISTA_MCP_HOST` (default `127.0.0.1`)
- `VISTA_MCP_PORT` (default `8000`)
- `VISTA_MCP_STREAMABLE_HTTP_PATH` (default `/mcp`)

Then run:

```bash
uv run vista-mcp-server
```

Set `VISTA_MCP_TRANSPORT=streamable-http` in `.env`, or set it in your shell before launching:

```powershell
$env:VISTA_MCP_TRANSPORT="streamable-http"
uv run vista-mcp-server
```

```bash
export VISTA_MCP_TRANSPORT=streamable-http
uv run vista-mcp-server
```

The MCP endpoint URL is typically:

`http://127.0.0.1:8000/mcp`

When exposing the server through ngrok, set `VISTA_MCP_HOST=0.0.0.0` so external Host headers are accepted.

For Agent Studio production usage, pair `streamable-http` with `VISTA_AUTH_MODE=delegated` or `hybrid`.
The server validates incoming bearer tokens against Trimble JWKS and forwards a validated delegated token to Vista API.
In `delegated` mode, requests without actor tokens fail immediately with a clear error.

## Scope formatting note

When requesting OAuth tokens with `application/x-www-form-urlencoded`, send scope as a space-delimited string:

- `scope=kb models kb-ingest agents`

Do not wrap the full scope string in quotes. In `.env`, use:

- `VISTA_SCOPE=openid vista_agent`

For delegated validation, set `VISTA_AUTH_REQUIRED_SCOPES` to scopes that are actually present in incoming access tokens.
If your delegated tokens contain only `vista_agent`, use:

- `VISTA_AUTH_REQUIRED_SCOPES=vista_agent`

Requiring scopes that are not present (for example adding `openid` when the token does not include it) causes authentication failures.

## Server-managed TID refresh behavior

- `server-managed` mode keeps access/refresh tokens in memory and refreshes before expiry (and once on Vista 401).
- Refreshed tokens are not written back to `.env`.
- Use streamable-http for this mode.

Quick check:

1. Set `VISTA_AUTH_MODE=server-managed` and `VISTA_MCP_TRANSPORT=streamable-http`.
2. Populate `VISTA_CLIENT_ID`, `VISTA_CLIENT_SECRET`, `VISTA_REFRESH_TOKEN`, and `VISTA_AUTH_ISSUER`.
3. Optionally set `VISTA_ACCESS_TOKEN` and `VISTA_SCOPE=openid vista_agent`.
4. Start server with `uv run vista-mcp-server` and call a Vista-backed tool.

## Agent Studio auth mode mapping

- If Agent Studio connection auth is `None`, run this server with `VISTA_AUTH_MODE=server-managed`.
- If Agent Studio connection auth is `On behalf of actor token` (or Agent token), run this server with `VISTA_AUTH_MODE=delegated` or `hybrid` and configure a real OAuth client in Agent Studio.
- Start with `VISTA_AUTH_MODE=delegated` + `VISTA_AUTH_STRATEGY=delegated_passthrough`.
- Only switch to `VISTA_AUTH_STRATEGY=token_exchange` when Vista rejects actor tokens due to audience/token-type requirements.
- A placeholder OAuth client in Agent Studio causes validation failures before MCP tool calls reach `/mcp`.

## Cursor MCP configuration

For stdio mode in Cursor MCP settings, use a command like:

- command: `uv`
- args: `--directory`, `C:\Users\cforey\Documents\vista-unapproved-invoice`, `run`, `server.main`

For streamable-http mode, configure Cursor to connect to the server URL (for example `http://127.0.0.1:8000/mcp`) instead of launching stdio.

Ensure env vars are defined in the environment/context Cursor uses to start or connect to the server.

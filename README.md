# Vista MCP Server

Production-focused MCP server for Vista APIs, with strong auth options, schema-backed validation, queue-first invoice review workflows, and built-in operational telemetry.

## What This Server Provides

- Unified MCP tools across Enterprise, Company, Contract, Customer, Project, JC, PO, AP, Vendor, and Health domains.
- Read-only invoice risk analysis and reviewer workflows with deterministic queue pagination.
- Multiple auth modes (`static`, `delegated`, `hybrid`, `server-managed`) for local and hosted MCP clients.
- Registry-first tool definitions, OpenAPI-backed request/response validation, and normalized output modes for agent chaining.
- Runtime safety controls for write access, bulk limits, retries, cache behavior, and canary guardrails.

## Quick Start (5 minutes)

### 1) Prerequisites

- Python `3.10+`
- [`uv`](https://docs.astral.sh/uv/)

### 2) Install dependencies

```bash
uv sync
```

For local development tooling (`pytest`, `ruff`):

```bash
uv sync --group dev
```

### 3) Configure environment

Copy `.env.example` to `.env` and set at minimum:

- `VISTA_API_BASE_URL` (host root only, no trailing `/api/v1`)
- `VISTA_AUTH_MODE`
- Auth-specific required variables (see the auth matrix below)

### 4) Start server

```bash
uv run vista-mcp-server
```

The console script entrypoint is defined in `pyproject.toml` as `server.main:main`.

## Auth Modes And Transport Matrix

`VISTA_AUTH_MODE` controls how outbound Vista credentials are resolved.

| Mode | Intended use | Required settings | Transport requirement |
| --- | --- | --- | --- |
| `static` | Simple local testing or service token usage | `VISTA_BEARER_TOKEN` or `VISTA_API_KEY` | `stdio` or `streamable-http` |
| `delegated` | Strict on-behalf-of actor token flow | `VISTA_AUTH_ISSUER`, `VISTA_AUTH_JWKS_URL`, `VISTA_AUTH_RESOURCE_SERVER_URL` | `streamable-http` required |
| `hybrid` | Delegated first, static fallback | Delegated settings + static credential (`VISTA_BEARER_TOKEN` or `VISTA_API_KEY`) | `streamable-http` required |
| `server-managed` | MCP server owns TID refresh lifecycle | `VISTA_CLIENT_ID`, `VISTA_CLIENT_SECRET`, `VISTA_REFRESH_TOKEN`, and `VISTA_AUTH_ISSUER` (or `VISTA_TOKEN_URL`) | `streamable-http` required |

### Delegated auth strategy

`VISTA_AUTH_STRATEGY` applies when request tokens are present:

- `delegated_passthrough` (default): forwards actor token directly to Vista.
- `token_exchange`: exchanges actor token at OAuth token endpoint before Vista calls.

Token exchange requires OAuth client credentials and token URL resolution (`VISTA_TOKEN_EXCHANGE_TOKEN_URL` or fallback to `VISTA_TOKEN_URL` / issuer token endpoint).

## Environment Configuration Reference

### Core

- `VISTA_API_BASE_URL` (**required**): API host root (example: `https://integrations-qa.centralus.cloudapp.azure.com`).
- `VISTA_ENTERPRISE_ID` (optional): default enterprise context when tool call omits `enterprise_id`.
- `VISTA_CORRELATION_ID` (optional): default `x-correlation-id` header.

### Static auth

- `VISTA_BEARER_TOKEN` (optional; required if no API key)
- `VISTA_API_KEY` (optional; required if no bearer token)
- `VISTA_API_KEY_HEADER` (default: `x-api-key`)

### Delegated / hybrid auth

- `VISTA_AUTH_ISSUER` (**required** for delegated/hybrid)
- `VISTA_AUTH_JWKS_URL` (**required** for delegated/hybrid)
- `VISTA_AUTH_RESOURCE_SERVER_URL` (**required** for delegated/hybrid)
- `VISTA_AUTH_AUDIENCE` (optional)
- `VISTA_AUTH_REQUIRED_SCOPES` (optional, space/comma delimited)
- `VISTA_AUTH_JWKS_CACHE_TTL_SECONDS` (default: `300`)
- `VISTA_AUTH_JWT_LEEWAY_SECONDS` (default: `60`)

### Token exchange (optional delegated strategy)

- `VISTA_TOKEN_EXCHANGE_TOKEN_URL`
- `VISTA_TOKEN_EXCHANGE_SCOPE`
- `VISTA_TOKEN_EXCHANGE_AUDIENCE`
- `VISTA_TOKEN_EXCHANGE_SUBJECT_TOKEN_TYPE` (default JWT token-type urn)
- `VISTA_TOKEN_EXCHANGE_REQUESTED_TOKEN_TYPE` (default access-token urn)
- `VISTA_TOKEN_EXCHANGE_CACHE_TTL_SECONDS` (default: `300`)
- `VISTA_TOKEN_EXCHANGE_REFRESH_SKEW_SECONDS` (default: `30`)

### Server-managed TID refresh

- `VISTA_CLIENT_ID` (**required**)
- `VISTA_CLIENT_SECRET` (**required**)
- `VISTA_REFRESH_TOKEN` (**required**)
- `VISTA_AUTH_ISSUER` or `VISTA_TOKEN_URL` (**required**)
- `VISTA_ACCESS_TOKEN` (optional seed token)
- `VISTA_SCOPE` (optional, space-delimited; example `openid vista_agent`)

### MCP transport

- `VISTA_MCP_TRANSPORT` = `stdio` (default) or `streamable-http`
- `VISTA_MCP_HOST` (default: `127.0.0.1`)
- `VISTA_MCP_PORT` (default: `8000`)
- `VISTA_MCP_STREAMABLE_HTTP_PATH` (default: `/mcp`)
- `VISTA_MCP_JSON_RESPONSE` (default: `false`)
- `VISTA_MCP_STATELESS_HTTP` (default: `false`)

### Request timeouts, pooling, and bulkheads

- `VISTA_REQUEST_TIMEOUT_SECONDS` (default: `45`)
- `VISTA_REQUEST_CONNECT_TIMEOUT_SECONDS` (default: `10`)
- `VISTA_REQUEST_READ_TIMEOUT_SECONDS` (default: `45`)
- `VISTA_REQUEST_WRITE_TIMEOUT_SECONDS` (default: `30`)
- `VISTA_REQUEST_POOL_TIMEOUT_SECONDS` (default: `10`)
- `VISTA_REQUEST_MAX_CONNECTIONS` (default: `100`)
- `VISTA_REQUEST_MAX_KEEPALIVE_CONNECTIONS` (default: `40`)
- `VISTA_MAX_CONCURRENT_REQUESTS` (default: `32`)
- `VISTA_MAX_CONCURRENT_ANALYSIS_RUNS` (default: `4`)

### Retry and reliability controls

- `VISTA_TRANSIENT_RETRY_ATTEMPTS` (default: `3`)
- `VISTA_TRANSIENT_RETRY_BASE_SECONDS` (default: `0.75`)
- `VISTA_TRANSIENT_RETRY_MAX_SECONDS` (default: `8.0`)
- `VISTA_TRANSIENT_RETRY_JITTER_SECONDS` (default: `0.25`)
- `VISTA_TRANSIENT_RETRY_STATUS_CODES` (default: `429,500,502,503,504`)

### Write-safety controls

- `VISTA_READ_ONLY_MODE` (default: `false`) disables write/bulk tools.
- `VISTA_WRITE_ENABLED_DOMAINS` (optional allowlist, example: `ap,po,jc`).
- `VISTA_MAX_BULK_ITEMS` (default: `100`)
- `VISTA_MAX_BATCH_SIZE` (optional override, takes precedence)

### Analysis controls

- `VISTA_ANALYSIS_DEFAULT_WINDOW_DAYS` (default: `365`)
- `VISTA_ANALYSIS_DEFAULT_TOP_N` (default: `5`)
- `VISTA_ANALYSIS_PAGE_SIZE` (default: `100`)
- `VISTA_ANALYSIS_MAX_PAGES` (default: `10`)
- `VISTA_ANALYSIS_STALE_DAYS` (default: `30`)
- `VISTA_ANALYSIS_HIGH_AMOUNT_THRESHOLD` (default: `50000`)
- `VISTA_ANALYSIS_DUPLICATE_AMOUNT_DELTA` (default: `0.01`)
- `VISTA_ANALYSIS_POLICY_PROFILE` (`standard|strict|lenient`, default `standard`)
- `VISTA_ANALYSIS_CACHE_BACKEND` (`memory|redis`, default `memory`)
- `VISTA_ANALYSIS_CACHE_TTL_SECONDS` (default: `180`)
- `VISTA_ANALYSIS_CACHE_PREFIX` (default: `vista:analysis`)
- `VISTA_ANALYSIS_FAIL_ON_PARTIAL` (default: `false`)
- `VISTA_REDIS_URL` (**required** when cache backend = `redis`)

### Optional feature flags

- `VISTA_INCLUDE_TEST_ENTERPRISE_TOOL` (default: `true`)
- `VISTA_INCLUDE_HEALTH_ALIVE_TOOL` (default: `true`)

### Canary guardrails

- `VISTA_RELIABILITY_CANARY_ENABLED` (default: `false`)
- `VISTA_RELIABILITY_CANARY_SAMPLE_RATE` (default: `0.1`)
- `VISTA_RELIABILITY_ROLLBACK_ERROR_RATE_THRESHOLD` (default: `0.05`)
- `VISTA_RELIABILITY_ROLLBACK_P95_MS_THRESHOLD` (default: `4000`)

## Running The Server

### STDIO mode (default)

Use for clients that spawn the process directly.

```bash
uv run vista-mcp-server
```

### Streamable HTTP mode

Set transport and run:

```bash
uv run vista-mcp-server
```

PowerShell example:

```powershell
$env:VISTA_MCP_TRANSPORT="streamable-http"
$env:VISTA_MCP_HOST="127.0.0.1"
$env:VISTA_MCP_PORT="8000"
$env:VISTA_MCP_STREAMABLE_HTTP_PATH="/mcp"
uv run vista-mcp-server
```

Typical endpoint URL:

- `http://127.0.0.1:8000/mcp`

When exposing through tunnel/proxy, set `VISTA_MCP_HOST=0.0.0.0`.

## Tool Inventory

Tools are declared centrally in `server/endpoint_registry.py` and registered by `server/tool_factory.py`.

### Endpoint families

- Enterprise: `get_enterprise`, `list_enterprises`, optional `test_list_enterprises`
- Company / Contract / Customer: `get_*`, `list_*`
- Project: `get_project`, `list_projects`
- Project Cost Entry: `create_daily_production`, `get_daily_production_action`, `get_unposted_daily_production`, `list_unposted_daily_production`
- Project Cost History: `get_project_cost_history`, `list_project_cost_history`
- Project Phase: `get_project_phase`, `list_project_phases`
- Purchase Order: `create_purchase_orders`, `get_purchase_order`, `get_purchase_order_action`, `get_unposted_purchase_order`, `list_purchase_orders`, `list_unposted_purchase_orders`
- Unapproved Invoice: `create_unapproved_invoices`, `get_unapproved_invoice`, `get_unapproved_invoice_action`, `query_unapproved_invoices`
- Sales Tax / Schedule Of Values / Standard Cost Type / Standard Phase: `get_*`, `list_*`
- Subcontract: `get_subcontract`, `list_subcontracts`
- Vendor + vendor alternate address: `get_*`, `list_*`
- Health: `health_ready`, optional `health_alive` (health tools bypass auth)

### Analysis and review tools

- `analyze_unapproved_invoices`
- `list_invoice_review_queues`
- `get_invoice_queue_page`
- `get_invoice_review_packet`
- `capture_invoice_review_decision`
- `preflight_invoice_approval`
- `export_invoice_audit`

### Bulk preflight tools

For each bulk write tool, a preflight validator is registered as:

- `validate_<tool_name>_request`

These validate request shape and policy constraints without calling Vista.

## Universal Tool Behaviors

### Output mode

Every tool accepts:

- `output=raw` (default): original payload
- `output=normalized`: snake_case `data` plus `tool_name` and `schema_ref`
- `output=both`: `{ raw, normalized }`

### Query normalization

List/query-style inputs normalize to:

```json
{"filters": []}
```

### Bulk normalization and safety

- Single item and list item forms normalize to `{ "items": [...] }`.
- Bulk requests are capped by `effective_max_batch_size` (`VISTA_MAX_BATCH_SIZE` or `VISTA_MAX_BULK_ITEMS`).
- `dry_run=true` validates payload contracts without API mutation.

### Enterprise scope resolution

For scoped endpoints:

1. explicit `enterprise_id` argument
2. fallback `VISTA_ENTERPRISE_ID`
3. otherwise fail with actionable error

### Permission-aware enterprise fallback

If enterprise list endpoints (`/api/v1/enterprise` or test variant) return `403` and `VISTA_ENTERPRISE_ID` is set, tool execution falls back to `get_enterprise`.

## Queue-First Invoice Review Workflow

Recommended review path:

1. `list_invoice_review_queues` to create a run and get queue counts/top risks.
2. `get_invoice_queue_page` with `queue` + `nextCursor` for deterministic pagination.
3. `get_invoice_review_packet` for single-invoice context and findings.
4. `capture_invoice_review_decision` to store reviewer rationale.
5. `preflight_invoice_approval` to evaluate readiness and blockers.
6. `export_invoice_audit` for run-level traceability payload.

Notes:

- Run state is ephemeral in-memory (`AnalysisRunStore`) with TTL-based pruning.
- Cursor values are offset-encoded tokens.
- `analyze_unapproved_invoices` defaults to compact queue samples to avoid oversized payloads.

## Built-In MCP Resources

Resources are registered in `server/resources.py`.

### Guides

- `vista://guides/dependencies`
- `vista://guides/workflows`
- `vista://guides/response-interpretation`
- `vista://guides/filters`
- `vista://guides/errors-and-edge-cases`
- `vista://guides/scenarios`

### Planning schema

- `vista://schema/tool-graph` (machine-readable dependency graph with `requires`, `produces`, `prerequisites`, `id_sources`, `safe_to_retry`)
- `vista://schema/planner` (intent-level sequencing hints)

### Metrics and policy

- `vista://metrics/tool-usage`
- `vista://metrics/analysis-ops`
- `vista://metrics/api-transport`
- `vista://ops/reliability-policy`

## Built-In MCP Prompts

Prompts are registered in `server/prompts.py`:

- `create_unapproved_invoice_workflow`
- `investigate_invoice_workflow`
- `filter_and_enrich_invoices_workflow`
- `handle_invoice_create_partial_failure_workflow`
- `discover_enterprise_and_vendor_before_create_workflow`

## Reliability And Production Runbook

- Treat `collection.partial=true` as degraded data; retry before approval actions.
- For strict completeness, set `VISTA_ANALYSIS_FAIL_ON_PARTIAL=true` or call analysis with `require_complete=true`.
- In multi-instance deployments, set `VISTA_ANALYSIS_CACHE_BACKEND=redis` + `VISTA_REDIS_URL`.
- Monitor rollback guardrails via `vista://metrics/*` and `vista://ops/reliability-policy`.
- Tune retries/timeouts incrementally, validate with canary metrics, then promote globally.

## Local Development

### Run tests

```bash
uv run pytest
```

### Lint

```bash
uv run ruff check .
```

### Package metadata

- Project metadata and runtime dependencies live in `pyproject.toml`.
- OpenAPI source contracts are `viewpoint_common_api.json` and `viewpoint_auth_api.json`.

## Architecture Overview

- `server/main.py`: startup, auth wiring, transport run mode, route compatibility metadata.
- `server/config.py`: settings model and startup validation rules.
- `server/api.py`: HTTP client, retries, auth header resolution, partial collection handling.
- `server/tool_factory.py`: tool registration, query/bulk normalization, output mode handling, analysis/review tools.
- `server/endpoint_registry.py`: declarative endpoint metadata and dependency graph synthesis.
- `server/generated_models.py`: OpenAPI schema-ref to runtime Pydantic adapter mapping.
- `server/services/invoice_analysis.py`: risk scoring and queue classification logic.
- `server/services/analysis_cache.py`: memory/Redis cache abstraction with singleflight.
- `server/services/analysis_runs.py`: in-memory run and decision store.
- `server/auth.py`: delegated JWT verification via JWKS.
- `server/token_manager.py`: server-managed refresh token lifecycle.
- `server/token_exchange.py`: OAuth token exchange with caching/retry behavior.

## Client Configuration Notes

### Cursor MCP

- STDIO: configure command execution (for example `uv ... run server.main` or `uv run vista-mcp-server`).
- Streamable HTTP: connect Cursor to your `/mcp` URL instead of launching a process.
- Ensure env vars are present in the same environment Cursor uses.

### Agent Studio

- Connection auth `None` -> use `VISTA_AUTH_MODE=server-managed`.
- Connection auth on-behalf-of actor token -> use `VISTA_AUTH_MODE=delegated` or `hybrid`.
- Start with `VISTA_AUTH_STRATEGY=delegated_passthrough`; switch to `token_exchange` only if Vista token audience/type requirements demand it.

## Troubleshooting

### Startup validation fails

- `VISTA_AUTH_MODE=static requires ...`: provide `VISTA_BEARER_TOKEN` or `VISTA_API_KEY`.
- Delegated/hybrid mode errors: ensure `streamable-http` transport and delegated settings are complete.
- `server-managed requires streamable-http`: set `VISTA_MCP_TRANSPORT=streamable-http`.
- Redis cache error: set `VISTA_REDIS_URL` when `VISTA_ANALYSIS_CACHE_BACKEND=redis`.

### Auth failures at runtime

- `401 authentication failed`: token missing/expired/invalid for chosen auth path.
- `403 authorization failed`: token lacks scope/permission; enterprise list endpoints may require elevated access.
- Delegated mode missing actor token: re-authenticate client and retry request.

### Scope formatting pitfalls

- OAuth scope values must be space-delimited strings (`VISTA_SCOPE=openid vista_agent`).
- If using `VISTA_AUTH_REQUIRED_SCOPES`, ensure each required scope exists in incoming delegated token scope claims.

### Oversized/partial data

- Use compact analysis output defaults for large backlogs.
- If partial list collection appears, retry with tuned page size/max pages/retry settings.
- Enable strict mode (`require_complete=true` or `VISTA_ANALYSIS_FAIL_ON_PARTIAL=true`) for approval-critical workflows.

## Security Notes

- Do not commit real tokens, secrets, or `.env` values.
- Prefer delegated or server-managed auth in hosted environments.
- Use `VISTA_READ_ONLY_MODE=true` and/or `VISTA_WRITE_ENABLED_DOMAINS` for least-privilege write posture.
- Use preflight tools and `dry_run=true` before bulk writes in production workflows.

# Vista MCP Server

MCP server exposing Vista Enterprise, Unapproved Invoice, Project, Vendor, and Health endpoints.

## Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/)
- `python-sdk-main` directory present at the repository root (used as the local `mcp` dependency source)

## Install

From the repository root:

```bash
uv sync
```

## Configure environment

Copy `.env.example` to `.env` and populate values:

- Required: `VISTA_API_BASE_URL`
- Required auth mode: set `VISTA_AUTH_MODE` to one of:
  - `static`: use `VISTA_BEARER_TOKEN` or `VISTA_API_KEY`
  - `delegated`: require per-request bearer token validation
  - `hybrid`: prefer per-request bearer token, fallback to static credentials
  - `server-managed`: use `VISTA_CLIENT_ID`/`VISTA_CLIENT_SECRET` + `VISTA_REFRESH_TOKEN` and refresh TID access tokens in memory
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
- Optional: `VISTA_ENTERPRISE_ID` to avoid passing `enterprise_id` on every scoped request
- Health tools do not require auth

## Run

From the repository root:

```bash
uv run server.main
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
uv run server.main
```

Set `VISTA_MCP_TRANSPORT=streamable-http` in `.env`, or set it in your shell before launching:

```powershell
$env:VISTA_MCP_TRANSPORT="streamable-http"
uv run server.main
```

```bash
export VISTA_MCP_TRANSPORT=streamable-http
uv run server.main
```

The MCP endpoint URL is typically:

`http://127.0.0.1:8000/mcp`

When exposing the server through ngrok, set `VISTA_MCP_HOST=0.0.0.0` so external Host headers are accepted.

For Agent Studio production usage, pair `streamable-http` with `VISTA_AUTH_MODE=delegated` or `hybrid`.
The server validates incoming bearer tokens against Trimble JWKS and forwards a validated delegated token to Vista API.

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
4. Start server with `uv run server.main` and call a Vista-backed tool.

## Agent Studio auth mode mapping

- If Agent Studio connection auth is `None`, run this server with `VISTA_AUTH_MODE=server-managed`.
- If Agent Studio connection auth is `On behalf of actor token` (or Agent token), run this server with `VISTA_AUTH_MODE=delegated` or `hybrid` and configure a real OAuth client in Agent Studio.
- A placeholder OAuth client in Agent Studio causes validation failures before MCP tool calls reach `/mcp`.

## Cursor MCP configuration

For stdio mode in Cursor MCP settings, use a command like:

- command: `uv`
- args: `--directory`, `C:\Users\cforey\Documents\vista-unapproved-invoice`, `run`, `server.main`

For streamable-http mode, configure Cursor to connect to the server URL (for example `http://127.0.0.1:8000/mcp`) instead of launching stdio.

Ensure env vars are defined in the environment/context Cursor uses to start or connect to the server.

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
- Required for authenticated API tools: one of `VISTA_BEARER_TOKEN` or `VISTA_API_KEY`
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

## Cursor MCP configuration

For stdio mode in Cursor MCP settings, use a command like:

- command: `uv`
- args: `--directory`, `C:\Users\cforey\Documents\vista-unapproved-invoice`, `run`, `server.main`

For streamable-http mode, configure Cursor to connect to the server URL (for example `http://127.0.0.1:8000/mcp`) instead of launching stdio.

Ensure env vars are defined in the environment/context Cursor uses to start or connect to the server.

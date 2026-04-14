# mcp/ — MCP Toolbox Configuration

This directory contains the configuration for Google MCP Toolbox for Databases, which provides the standard interface between the Oracle Forge agent and the DAB databases.

## What is MCP Toolbox?

MCP Toolbox for Databases (`github.com/googleapis/genai-toolbox`) is a binary that reads `tools.yaml` and exposes each defined tool as an endpoint the agent can call via the MCP protocol. The agent never writes raw database drivers — it calls tools defined here.

## Files

- **`tools.yaml`** — defines all database sources (connection strings) and tools (query interfaces). This is the single authoritative source for what databases the agent can access and how.

## Setup

```bash
# Download toolbox binary (check googleapis/genai-toolbox for latest version)
export VERSION=0.30.0
curl -O https://storage.googleapis.com/genai-toolbox/v$VERSION/linux/amd64/toolbox
chmod +x toolbox

# Start toolbox with this config
./toolbox --config mcp/tools.yaml
```

Expected tools in the output:
- `postgres_query`
- `mongo_aggregate`
- `mongo_find`
- `sqlite_query`
- `duckdb_query`
- `cross_db_merge`

If any tool is missing, check the corresponding `source` block in `tools.yaml` — a bad connection string will prevent the tool from loading.

## Deliverable vs Runtime Mode

For TRP1 submission alignment, `mcp/tools.yaml` is kept as the canonical four-database tool map (PostgreSQL, MongoDB, SQLite, DuckDB) with the expected tool names.

At runtime on this VPS, the team currently uses `mcp/mcp_server.py` for compatibility and stable `/v1/tools` + `/v1/tools/{tool}:invoke` endpoints:

```bash
source .venv/bin/activate
set -a && source .env && set +a
uvicorn mcp.mcp_server:app --port 5000
curl http://127.0.0.1:5000/v1/tools
```

This keeps implementation behavior stable while preserving the challenge-required MCP configuration artifact in `mcp/tools.yaml`.

## Environment Variables

Sensitive values (passwords, connection strings) are loaded from `.env` at the project root. Never hardcode credentials in `tools.yaml`. Required variables:

```
POSTGRES_PASSWORD=<your postgres password>
MONGO_PASSWORD=<your mongo password>
```

## Adding a New Tool

1. Add a new `source` block in `tools.yaml` if the tool connects to a new database instance.
2. Add a new entry under `tools:` with a name, kind, source, and description specific enough for the agent's tool-selection logic to match unambiguously.
3. Restart the toolbox and verify the new tool appears in `curl http://localhost:5000/v1/tools`.
4. Document the new tool in `utils/README.md` and the relevant `kb/architecture/tool_scoping.md` section.
5. Write a probe in `probes/probes.md` that tests the new tool is called correctly.
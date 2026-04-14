"""
mcp/mcp_server.py
-----------------
MCP-compatible server with full 5-DB coverage (PostgreSQL, MongoDB, SQLite,
DuckDB, cross-DB merge). The Google toolbox binary fails on this VPS due to
a Snowflake CGO bug, and the npm wrapper does not support DuckDB.

Exposes two equivalent APIs so either client style works:
  MCP JSON-RPC 2.0  POST /mcp              — used by query_executor.py
  REST (legacy)     POST /v1/tools/{n}:invoke

Usage:
    source .venv/bin/activate && source .env
    uvicorn mcp.mcp_server:app --port 5000
"""

import asyncio
import json
import os
import sqlite3
from typing import Any, Optional

import duckdb
import psycopg2
import psycopg2.extras
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# Config from environment (loaded via source .env before starting)
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB   = os.getenv("POSTGRES_DB", "yelp")
POSTGRES_USER = os.getenv("POSTGRES_USER", "oracle_forge")
POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "")

MONGO_HOST = os.getenv("MONGO_HOST", "127.0.0.1")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB   = "yelp_db"

SQLITE_PATH = os.getenv("SQLITE_PATH", "db/dab_sqlite.db")
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "db/yelp_user.db")

# Module-level MongoDB client — connection pool shared across all requests
_mongo_client: Optional[MongoClient] = None

# ---------------------------------------------------------------------------
app = FastAPI(title="Oracle Forge MCP Server", version="1.0.0")

TOOLS = [
    {
        "name": "postgres_query",
        "description": "Executes SQL against the PostgreSQL Yelp database.",
        "parameters": {"sql": {"type": "string"}},
    },
    {
        "name": "mongo_aggregate",
        "description": "Executes a MongoDB aggregation pipeline.",
        "parameters": {
            "collection": {"type": "string"},
            "pipeline": {"type": "string"},
        },
    },
    {
        "name": "mongo_find",
        "description": "Executes a MongoDB find query.",
        "parameters": {
            "collection": {"type": "string"},
            "filter": {"type": "string"},
            "projection": {"type": "string"},
        },
    },
    {
        "name": "sqlite_query",
        "description": "Executes SQL against the DAB SQLite database.",
        "parameters": {"sql": {"type": "string"}},
    },
    {
        "name": "duckdb_query",
        "description": "Executes analytical SQL against the DAB DuckDB database.",
        "parameters": {"sql": {"type": "string"}},
    },
    {
        "name": "cross_db_merge",
        "description": "Merges two result sets from different database tools.",
        "parameters": {
            "left_results":  {"type": "string"},
            "right_results": {"type": "string"},
            "left_key":      {"type": "string"},
            "right_key":     {"type": "string"},
            "left_db":       {"type": "string"},
            "right_db":      {"type": "string"},
        },
    },
]


def _get_mongo() -> MongoClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}/")
    return _mongo_client


def _safe_json(value: Any) -> Any:
    """Return parsed JSON if value is a string, otherwise return as-is."""
    return json.loads(value) if isinstance(value, str) else value


@app.get("/v1/tools")
def list_tools():
    return {"tools": TOOLS}


@app.post("/mcp")
async def mcp_rpc(body: Optional[dict] = None):
    """Minimal MCP JSON-RPC 2.0 endpoint supporting tools/list and tools/call."""
    req = body or {}
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {}) or {}

    if req.get("jsonrpc") != "2.0":
        return _rpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    if method == "tools/list":
        tools = []
        for tool in TOOLS:
            props = tool.get("parameters", {})
            tools.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": {
                        "type": "object",
                        "properties": props,
                        "required": list(props.keys()),
                    },
                }
            )
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        if not tool_name:
            return _rpc_error(req_id, -32602, "Invalid params: 'name' is required")
        try:
            result = await asyncio.to_thread(_dispatch, tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result)}]
                },
            }
        except ValueError as e:
            return _rpc_error(req_id, -32602, str(e))
        except Exception as e:
            return _rpc_error(req_id, -32000, str(e))

    return _rpc_error(req_id, -32601, f"Method not found: {method}")


@app.post("/v1/tools/{tool_name}:invoke")
async def invoke_tool(tool_name: str = Path(...), body: Optional[dict] = None):
    params = body or {}
    try:
        result = await asyncio.to_thread(_dispatch, tool_name, params)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return JSONResponse(status_code=200, content={"error": str(e)})


def _rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _dispatch(tool_name: str, params: dict) -> Any:
    handlers = {
        "postgres_query":  _postgres_query,
        "mongo_aggregate": _mongo_aggregate,
        "mongo_find":      _mongo_find,
        "sqlite_query":    _sqlite_query,
        "duckdb_query":    _duckdb_query,
        "cross_db_merge":  _cross_db_merge,
    }
    fn = handlers.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name!r}")
    return fn(params)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _postgres_query(params: dict) -> list[dict]:
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("Parameter 'sql' is required")
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _mongo_aggregate(params: dict) -> list[dict]:
    collection = params.get("collection", "")
    if not collection:
        raise ValueError("Parameter 'collection' is required")
    pipeline = _safe_json(params.get("pipeline", "[]"))
    db = _get_mongo()[MONGO_DB]
    return [_serialize_doc(d) for d in db[collection].aggregate(pipeline)]


def _mongo_find(params: dict) -> list[dict]:
    collection = params.get("collection", "")
    if not collection:
        raise ValueError("Parameter 'collection' is required")
    filter_doc = _safe_json(params.get("filter", "{}")) or {}
    projection = _safe_json(params.get("projection")) if params.get("projection") else None
    db = _get_mongo()[MONGO_DB]
    return [_serialize_doc(d) for d in db[collection].find(filter_doc, projection)]


def _sqlite_query(params: dict) -> list[dict]:
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("Parameter 'sql' is required")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _duckdb_query(params: dict) -> list[dict]:
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("Parameter 'sql' is required")
    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        result = conn.execute(sql)
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row)) for row in result.fetchall()]
    finally:
        conn.close()


def _cross_db_merge(params: dict) -> dict:
    left  = _safe_json(params.get("left_results",  "[]"))
    right = _safe_json(params.get("right_results", "[]"))
    left_key  = params.get("left_key",  "")
    right_key = params.get("right_key", "")

    if not left_key or not right_key:
        raise ValueError("left_key and right_key are required for cross_db_merge")

    right_index: dict[str, list] = {}
    for row in right:
        k = str(row.get(right_key, ""))
        right_index.setdefault(k, []).append(row)

    merged = []
    for left_row in left:
        matches = right_index.get(str(left_row.get(left_key, "")), [])
        if matches:
            for right_row in matches:
                merged.append({**left_row, **right_row})
        else:
            merged.append(left_row)

    return {"rows": merged, "count": len(merged)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_doc(doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = _serialize_doc(v)
        elif isinstance(v, list):
            out[k] = [_serialize_doc(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Entry point (for direct python execution)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)

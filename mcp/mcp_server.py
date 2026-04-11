"""
mcp/mcp_server.py
-----------------
Python replacement for the MCP Toolbox binary, which fails silently on this
server due to its embedded Snowflake CGO library calling exit(1) at startup
whenever a tools file is loaded.

Implements the same HTTP API the MCP Toolbox would expose:
  GET  /v1/tools                     — list available tools
  POST /v1/tools/{tool_name}:invoke  — execute a tool and return results

Usage:
    cd /home/natnael/oracle-forge
    source .venv/bin/activate
    source .env
    uvicorn mcp.mcp_server:app --port 5000

Tools implemented:
  - postgres_query    : SQL against PostgreSQL Yelp DB
  - mongo_aggregate   : MongoDB aggregation pipeline
  - mongo_find        : MongoDB find with filter + projection
  - sqlite_query      : SQL against DAB SQLite DB
  - duckdb_query      : Analytical SQL against DAB DuckDB DB
  - cross_db_merge    : In-process merge of two result sets
"""

import json
import os
import sqlite3
import sys
from typing import Any

import duckdb
import psycopg2
import psycopg2.extras
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


@app.get("/v1/tools")
def list_tools():
    return {"tools": TOOLS}


@app.post("/v1/tools/{tool_name}:invoke")
async def invoke_tool(tool_name: str = Path(...), body: dict = None):
    if body is None:
        body = {}
    try:
        result = _dispatch(tool_name, body)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return JSONResponse(status_code=200, content={"error": str(e)})


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
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


def _mongo_aggregate(params: dict) -> list[dict]:
    collection = params.get("collection", "")
    pipeline_raw = params.get("pipeline", "[]")
    if not collection:
        raise ValueError("Parameter 'collection' is required")
    pipeline = json.loads(pipeline_raw) if isinstance(pipeline_raw, str) else pipeline_raw
    client = MongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}/")
    try:
        db = client[MONGO_DB]
        docs = list(db[collection].aggregate(pipeline))
        # Convert ObjectIds to strings for JSON serialisation
        return [_serialize_doc(d) for d in docs]
    finally:
        client.close()


def _mongo_find(params: dict) -> list[dict]:
    collection = params.get("collection", "")
    filter_raw = params.get("filter", "{}")
    projection_raw = params.get("projection", None)
    if not collection:
        raise ValueError("Parameter 'collection' is required")
    filter_doc = json.loads(filter_raw) if isinstance(filter_raw, str) else (filter_raw or {})
    projection = None
    if projection_raw:
        projection = json.loads(projection_raw) if isinstance(projection_raw, str) else projection_raw
    client = MongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}/")
    try:
        db = client[MONGO_DB]
        cursor = db[collection].find(filter_doc, projection)
        return [_serialize_doc(d) for d in cursor]
    finally:
        client.close()


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
    left_raw  = params.get("left_results", "[]")
    right_raw = params.get("right_results", "[]")
    left_key  = params.get("left_key", "")
    right_key = params.get("right_key", "")

    left  = json.loads(left_raw)  if isinstance(left_raw,  str) else left_raw
    right = json.loads(right_raw) if isinstance(right_raw, str) else right_raw

    if not left_key or not right_key:
        raise ValueError("left_key and right_key are required for cross_db_merge")

    # Build lookup from right side
    right_index: dict[str, list] = {}
    for row in right:
        k = str(row.get(right_key, ""))
        right_index.setdefault(k, []).append(row)

    merged = []
    for left_row in left:
        lk = str(left_row.get(left_key, ""))
        matches = right_index.get(lk, [])
        if matches:
            for right_row in matches:
                combined = {**left_row, **right_row}
                merged.append(combined)
        else:
            merged.append(left_row)

    return {"rows": merged, "count": len(merged)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_doc(doc: dict) -> dict:
    """Convert non-JSON-serializable BSON types to strings."""
    out = {}
    for k, v in doc.items():
        if hasattr(v, "__class__") and v.__class__.__name__ == "ObjectId":
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

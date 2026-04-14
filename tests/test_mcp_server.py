"""tests/test_mcp_server.py — MCP server endpoint tests (no real DB connections)."""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from mcp.mcp_server import app

client = TestClient(app)


# ── REST endpoint ─────────────────────────────────────────────────────────────

def test_list_tools_returns_all_six():
    resp = client.get("/v1/tools")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()["tools"]]
    assert set(names) == {
        "postgres_query", "mongo_aggregate", "mongo_find",
        "sqlite_query", "duckdb_query", "cross_db_merge",
    }


def test_invoke_unknown_tool_returns_400():
    resp = client.post("/v1/tools/nonexistent_tool:invoke", json={})
    assert resp.status_code == 400


# ── MCP JSON-RPC endpoint ─────────────────────────────────────────────────────

def test_mcp_tools_list():
    payload = {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "1"
    tools = data["result"]["tools"]
    assert len(tools) == 6
    assert all("inputSchema" in t for t in tools)


def test_mcp_tools_list_input_schema_has_required():
    payload = {"jsonrpc": "2.0", "id": "2", "method": "tools/list", "params": {}}
    resp = client.post("/mcp", json=payload)
    tools = {t["name"]: t for t in resp.json()["result"]["tools"]}
    assert "sql" in tools["duckdb_query"]["inputSchema"]["properties"]
    assert "sql" in tools["duckdb_query"]["inputSchema"]["required"]


def test_mcp_invalid_jsonrpc_version():
    payload = {"jsonrpc": "1.0", "id": "3", "method": "tools/list", "params": {}}
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32600


def test_mcp_unknown_method():
    payload = {"jsonrpc": "2.0", "id": "4", "method": "unknown/method", "params": {}}
    resp = client.post("/mcp", json=payload)
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_mcp_tools_call_unknown_tool():
    payload = {
        "jsonrpc": "2.0", "id": "5",
        "method": "tools/call",
        "params": {"name": "bad_tool", "arguments": {}},
    }
    resp = client.post("/mcp", json=payload)
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32602


def test_mcp_tools_call_missing_name():
    payload = {
        "jsonrpc": "2.0", "id": "6",
        "method": "tools/call",
        "params": {"arguments": {}},
    }
    resp = client.post("/mcp", json=payload)
    data = resp.json()
    assert "error" in data


@patch("mcp.mcp_server._duckdb_query")
def test_mcp_tools_call_duckdb_success(mock_duckdb):
    mock_duckdb.return_value = [{"n": 42}]
    payload = {
        "jsonrpc": "2.0", "id": "7",
        "method": "tools/call",
        "params": {"name": "duckdb_query", "arguments": {"sql": "SELECT 42 AS n"}},
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    content = json.loads(data["result"]["content"][0]["text"])
    assert content == [{"n": 42}]


@patch("mcp.mcp_server._duckdb_query")
def test_mcp_tools_call_db_error_returns_rpc_error(mock_duckdb):
    mock_duckdb.side_effect = Exception("connection refused")
    payload = {
        "jsonrpc": "2.0", "id": "8",
        "method": "tools/call",
        "params": {"name": "duckdb_query", "arguments": {"sql": "SELECT 1"}},
    }
    resp = client.post("/mcp", json=payload)
    data = resp.json()
    assert "error" in data
    assert "connection refused" in data["error"]["message"]

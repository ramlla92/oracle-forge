import json

import httpx

from agent.models import SubQuery

MCP_BASE_URL = "http://localhost:5000"

# Maps DB type to MCP tool name (must match toolbox.runtime.yaml exactly)
DB_TYPE_TO_TOOL = {
    "mongodb":               "mongo_aggregate",
    "duckdb":                "duckdb_query",
    "postgresql":            "postgres_query",
    "postgresql_bookreview": "bookreview_query",
    "sqlite":                "sqlite_query",
    "github_repos_metadata":  "github_repos_metadata_query",
    "github_repos_artifacts": "github_repos_artifacts_query",
}

_rpc_id = 0


def _next_id() -> str:
    global _rpc_id
    _rpc_id += 1
    return str(_rpc_id)


class QueryExecutor:

    def __init__(self, mcp_base_url: str = MCP_BASE_URL, timeout: float = 30.0):
        self.endpoint = mcp_base_url.rstrip("/") + "/mcp"
        self.timeout = timeout

    def execute(self, sub_query: SubQuery) -> dict:
        """Execute a sub-query via MCP JSON-RPC. Raises on error — caller handles retry."""
        tool_name = DB_TYPE_TO_TOOL.get(sub_query.database_type)
        if not tool_name:
            raise ValueError(f"No MCP tool mapped for db_type '{sub_query.database_type}'")

        arguments = self._build_arguments(sub_query)
        return self._call_tool(tool_name, arguments)

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        response = httpx.post(self.endpoint, json=payload, timeout=self.timeout)

        if response.status_code != 200:
            raise RuntimeError(
                f"MCP tool '{tool_name}' returned HTTP {response.status_code}: {response.text}"
            )

        rpc = response.json()
        if "error" in rpc:
            raise RuntimeError(f"MCP RPC error: {rpc['error']}")

        content = rpc.get("result", {}).get("content", [])
        if not content:
            return {}

        text = content[0].get("text", "[]")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def _build_arguments(self, sub_query: SubQuery) -> dict:
        """Build tool arguments from the sub-query."""
        if sub_query.database_type == "mongodb":
            try:
                pipeline = json.loads(sub_query.query)
                if pipeline and isinstance(pipeline[0], dict) and "$collection" in pipeline[0]:
                    collection = pipeline.pop(0)["$collection"]
                else:
                    collection = "business"
                    print(
                        "WARNING: MongoDB pipeline missing $collection, "
                        f"defaulting to 'business'. Query prefix: {sub_query.query[:80]}",
                        flush=True,
                    )
            except (json.JSONDecodeError, IndexError):
                pipeline = sub_query.query
                collection = "business"
                print(
                    "WARNING: MongoDB pipeline parse error, "
                    f"defaulting to 'business'. Query prefix: {sub_query.query[:80]}",
                    flush=True,
                )
            serialized = pipeline if isinstance(pipeline, str) else json.dumps(pipeline)
            return {"collection": collection, "pipeline": serialized}

        return {"sql": sub_query.query}

    def merge(self, left: dict, right: dict, left_key: str, right_key: str,
              left_db: str, right_db: str) -> dict:
        """Merge two result sets locally — cross_db_merge is not in the toolbox."""
        left_list  = left  if isinstance(left,  list) else left.get("rows",  [])
        right_list = right if isinstance(right, list) else right.get("rows", [])

        right_index: dict[str, list] = {}
        for row in right_list:
            k = str(row.get(right_key, ""))
            right_index.setdefault(k, []).append(row)

        merged = []
        for left_row in left_list:
            matches = right_index.get(str(left_row.get(left_key, "")), [])
            if matches:
                for right_row in matches:
                    merged.append({**left_row, **right_row})
            else:
                merged.append(left_row)

        return {"rows": merged, "count": len(merged)}

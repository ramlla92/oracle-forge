from pydantic import BaseModel
from typing import Optional, Any


class QueryRequest(BaseModel):
    question: str
    available_databases: list[str]
    session_id: str


class SubQuery(BaseModel):
    database_type: str  # "postgresql" | "sqlite" | "mongodb" | "duckdb"
    query: str
    intent: str


class QueryTrace(BaseModel):
    timestamp: str
    sub_queries: list[SubQuery]
    databases_used: list[str]
    self_corrections: list[dict]
    raw_results: dict[str, Any]
    merge_operations: list[str]


class AgentResponse(BaseModel):
    answer: str
    query_trace: QueryTrace
    confidence: float  # 0.0–1.0
    error: Optional[str] = None

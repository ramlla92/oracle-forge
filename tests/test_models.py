"""tests/test_models.py — Pydantic data contract validation."""
import pytest

from agent.models import AgentResponse, QueryRequest, QueryTrace, SubQuery


def test_query_request_requires_fields():
    with pytest.raises(Exception):
        QueryRequest()  # missing required fields


def test_query_request_valid():
    r = QueryRequest(
        question="How many businesses?", available_databases=["mongodb"], session_id="s1"
    )
    assert r.question == "How many businesses?"
    assert r.available_databases == ["mongodb"]


def test_sub_query_valid():
    sq = SubQuery(database_type="duckdb", query="SELECT 1", intent="test")
    assert sq.database_type == "duckdb"


def test_agent_response_defaults():
    from datetime import datetime
    trace = QueryTrace(
        timestamp=datetime.utcnow().isoformat(),
        sub_queries=[],
        databases_used=[],
        self_corrections=[],
        raw_results={},
        merge_operations=[],
    )
    resp = AgentResponse(answer="42", query_trace=trace, confidence=0.9)
    assert resp.error is None
    assert resp.confidence == 0.9


def test_agent_response_serializable():
    import json
    from datetime import datetime
    trace = QueryTrace(
        timestamp=datetime.utcnow().isoformat(),
        sub_queries=[SubQuery(database_type="mongodb", query="[]", intent="x")],
        databases_used=["mongodb"],
        self_corrections=[],
        raw_results={"mongodb": []},
        merge_operations=[],
    )
    resp = AgentResponse(answer="test", query_trace=trace, confidence=0.5)
    data = resp.model_dump()
    json.dumps(data)  # must not raise

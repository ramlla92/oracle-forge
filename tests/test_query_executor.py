"""tests/test_query_executor.py — QueryExecutor argument building and merge logic."""
import json

import pytest

from agent.models import SubQuery
from agent.query_executor import QueryExecutor


@pytest.fixture
def executor():
    return QueryExecutor()


# ── _build_arguments ─────────────────────────────────────────────────────────

class TestBuildArguments:
    def test_sql_dbs_return_sql_key(self, executor):
        for db_type in ("duckdb", "postgresql", "sqlite"):
            sq = SubQuery(database_type=db_type, query="SELECT 1", intent="test")
            args = executor._build_arguments(sq)
            assert "sql" in args
            assert args["sql"] == "SELECT 1"

    def test_mongodb_with_collection_prefix(self, executor):
        pipeline = json.dumps([{"$collection": "business"}, {"$match": {"is_open": 1}}])
        sq = SubQuery(database_type="mongodb", query=pipeline, intent="test")
        args = executor._build_arguments(sq)
        assert args["collection"] == "business"
        assert "$collection" not in args["pipeline"]
        assert "$match" in args["pipeline"]

    def test_mongodb_defaults_to_business_collection(self, executor):
        pipeline = json.dumps([{"$match": {"is_open": 1}}])
        sq = SubQuery(database_type="mongodb", query=pipeline, intent="test")
        args = executor._build_arguments(sq)
        assert args["collection"] == "business"

    def test_mongodb_invalid_json_uses_raw(self, executor):
        sq = SubQuery(database_type="mongodb", query="not valid json", intent="test")
        args = executor._build_arguments(sq)
        assert args["collection"] == "business"
        assert args["pipeline"] == "not valid json"


# ── merge ────────────────────────────────────────────────────────────────────

class TestMerge:
    def test_basic_merge(self, executor):
        left = [{"business_id": "b1", "name": "Acme"}]
        right = [{"business_ref": "b1", "avg_rating": 3.5}]
        result = executor.merge(left, right, "business_id", "business_ref", "mongodb", "duckdb")
        assert result["count"] == 1
        assert result["rows"][0]["name"] == "Acme"
        assert result["rows"][0]["avg_rating"] == 3.5

    def test_unmatched_left_rows_included(self, executor):
        left = [{"id": "a"}, {"id": "b"}]
        right = [{"id": "a", "score": 10}]
        result = executor.merge(left, right, "id", "id", "db1", "db2")
        assert result["count"] == 2
        ids = [r["id"] for r in result["rows"]]
        assert "b" in ids  # unmatched row still included

    def test_one_to_many_join(self, executor):
        left = [{"id": "x"}]
        right = [{"id": "x", "val": 1}, {"id": "x", "val": 2}]
        result = executor.merge(left, right, "id", "id", "db1", "db2")
        assert result["count"] == 2

    def test_accepts_dict_with_rows_key(self, executor):
        left = {"rows": [{"id": "1"}]}
        right = {"rows": [{"id": "1", "extra": "data"}]}
        result = executor.merge(left, right, "id", "id", "db1", "db2")
        assert result["count"] == 1
        assert result["rows"][0]["extra"] == "data"

    def test_empty_inputs(self, executor):
        result = executor.merge([], [], "id", "id", "db1", "db2")
        assert result == {"rows": [], "count": 0}

    def test_right_empty_returns_left_rows(self, executor):
        left = [{"id": "1", "name": "A"}]
        result = executor.merge(left, [], "id", "id", "db1", "db2")
        assert result["count"] == 1
        assert result["rows"][0]["name"] == "A"

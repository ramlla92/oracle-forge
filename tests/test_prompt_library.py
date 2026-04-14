"""tests/test_prompt_library.py — Prompt generation correctness."""
import pytest

from agent.prompt_library import PromptLibrary


@pytest.fixture
def lib():
    return PromptLibrary()


def test_intent_analysis_contains_question(lib):
    prompt = lib.intent_analysis("How many businesses?", ["mongodb", "duckdb"])
    assert "How many businesses?" in prompt
    assert "mongodb" in prompt
    assert "duckdb" in prompt


def test_intent_analysis_requests_json(lib):
    prompt = lib.intent_analysis("test", ["mongodb"])
    assert "target_databases" in prompt
    assert "requires_join" in prompt


def test_nl_to_sql_includes_schema_and_question(lib):
    prompt = lib.nl_to_sql("Count rows", "TABLE: review(id, rating)", dialect="duckdb")
    assert "Count rows" in prompt
    assert "TABLE: review" in prompt
    assert "DUCKDB" in prompt


def test_nl_to_sql_dialect_rules(lib):
    pg_prompt = lib.nl_to_sql("q", "schema", dialect="postgresql")
    sq_prompt = lib.nl_to_sql("q", "schema", dialect="sqlite")
    assert "ILIKE" in pg_prompt
    assert "ILIKE" not in sq_prompt


def test_nl_to_mongodb_requires_collection_prefix(lib):
    prompt = lib.nl_to_mongodb("Count businesses", "business schema")
    assert "$collection" in prompt
    assert "business_id" in prompt


def test_nl_to_sql_with_refs_injects_refs(lib):
    prompt = lib.nl_to_sql_with_refs(
        "avg rating", "review(rating, business_ref)",
        "'businessref_1', 'businessref_2'"
    )
    assert "businessref_1" in prompt
    assert "business_ref IN" in prompt


def test_self_correct_includes_error(lib):
    prompt = lib.self_correct("q", "SELECT bad", "syntax error near bad", "duckdb", "schema")
    assert "syntax error near bad" in prompt
    assert "SELECT bad" in prompt


def test_synthesize_response_includes_results(lib):
    results = {"duckdb": [{"avg": 3.5}]}
    prompt = lib.synthesize_response("What is the avg?", results, {})
    assert "What is the avg?" in prompt
    assert "3.5" in prompt


def test_synthesize_truncates_large_results(lib):
    big_results = {"duckdb": [{"text": "x" * 10000}]}
    prompt = lib.synthesize_response("q", big_results, {})
    # Should not raise and should be under some reasonable length
    assert len(prompt) < 20000

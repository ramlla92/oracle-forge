"""tests/test_context_manager.py — ContextManager layer loading and schema extraction."""
import os
import tempfile

import pytest

from agent.context_manager import ContextManager


@pytest.fixture
def tmp_files():
    """Create temporary AGENT.md, corrections, and domain KB files."""
    with tempfile.TemporaryDirectory() as d:
        agent_md = os.path.join(d, "AGENT.md")
        corrections = os.path.join(d, "corrections.md")
        domain_kb = os.path.join(d, "domain.md")

        with open(agent_md, "w") as f:
            f.write("""# Agent Context

## Database Schemas

### MongoDB — Yelp
business_id, name, description

### DuckDB — Yelp
review: review_id, rating, business_ref

## Behavioral Rules
1. Always trace queries
""")
        with open(corrections, "w") as f:
            f.write(
                "# Corrections Log\n"
                "| COR-001 | 2026-04-11 | test query | syntax_error"
                " | — | bad query | fixed | pass |\n"
            )
        with open(domain_kb, "w") as f:
            f.write("# Domain Knowledge\nYelp star ratings are 1-5.")

        yield agent_md, corrections, domain_kb


def test_get_full_context_includes_all_layers(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    full = ctx.get_full_context()
    assert "Agent Context" in full
    assert "Corrections Log" in full
    assert "Domain Knowledge" in full


def test_get_full_context_missing_files_graceful(tmp_files):
    agent_md, _, _ = tmp_files
    ctx = ContextManager(agent_md, "/nonexistent/corrections.md", "/nonexistent/domain.md")
    full = ctx.get_full_context()
    assert "Agent Context" in full  # Layer 1 still loads
    assert "Not yet populated" in full or "No corrections" in full


def test_get_schema_for_db_mongodb(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    schema = ctx.get_schema_for_db("mongodb")
    assert "MongoDB" in schema
    assert "business_id" in schema
    assert "DuckDB" not in schema  # should not bleed into next section


def test_get_schema_for_db_duckdb(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    schema = ctx.get_schema_for_db("duckdb")
    assert "DuckDB" in schema
    assert "review" in schema


def test_get_schema_for_db_unknown_returns_full(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    schema = ctx.get_schema_for_db("unknowndb")
    assert "Agent Context" in schema  # returns full content


def test_token_budget_truncation(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    full = ctx.get_full_context(token_budget=10)  # very small budget
    assert len(full) <= 10 * 4 + 100  # allow for truncation message overhead


def test_add_to_session_and_retrieve(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    ctx.add_to_session("How many businesses?", "100 businesses found")
    session = ctx.get_session_context()
    assert "How many businesses?" in session


def test_session_history_capped_at_10(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    for i in range(15):
        ctx.add_to_session(f"query {i}", f"result {i}")
    assert len(ctx._session_history) == 10


def test_append_correction_writes_to_file(tmp_files):
    agent_md, corrections, domain_kb = tmp_files
    ctx = ContextManager(agent_md, corrections, domain_kb)
    ctx.append_correction(
        query="test query",
        what_went_wrong="syntax error",
        correct_approach="fixed query",
        failure_category="syntax_error",
    )
    with open(corrections) as f:
        content = f.read()
    assert "test query" in content
    assert "syntax_error" in content

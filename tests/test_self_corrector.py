"""tests/test_self_corrector.py — SelfCorrector failure diagnosis and fix strategies."""
from unittest.mock import MagicMock

import pytest

from agent.prompt_library import PromptLibrary
from agent.self_corrector import SelfCorrector, _strip_markdown


@pytest.fixture
def corrector():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="SELECT COUNT(*) FROM review"))]
    )
    return SelfCorrector(PromptLibrary(), mock_client)


# ── _strip_markdown ──────────────────────────────────────────────────────────

def test_strip_markdown_plain_sql():
    assert _strip_markdown("SELECT 1") == "SELECT 1"


def test_strip_markdown_fenced_sql():
    text = "```sql\nSELECT 1\n```"
    assert _strip_markdown(text) == "SELECT 1"


def test_strip_markdown_fenced_json():
    text = "```json\n[{\"$match\": {}}]\n```"
    assert _strip_markdown(text) == '[{"$match": {}}]'


def test_strip_markdown_no_closing_fence():
    text = "```sql\nSELECT 1"
    assert _strip_markdown(text) == "SELECT 1"


def test_strip_markdown_embedded_fence():
    text = "Here is the query:\n```sql\nSELECT 1\n```"
    assert _strip_markdown(text) == "SELECT 1"


def test_strip_markdown_preserves_multiline():
    text = "```sql\nSELECT\n  AVG(rating)\nFROM review\n```"
    result = _strip_markdown(text)
    assert "SELECT" in result
    assert "AVG(rating)" in result
    assert "```" not in result


# ── diagnose_failure ─────────────────────────────────────────────────────────

def test_diagnose_syntax_error(corrector):
    assert corrector.diagnose_failure("syntax error at or near 'sql'", "") == "syntax_error"


def test_diagnose_wrong_table(corrector):
    assert corrector.diagnose_failure("relation 'reviews' does not exist", "") == "wrong_table"


def test_diagnose_join_key_format(corrector):
    result = corrector.diagnose_failure("operator does not exist: integer = text", "")
    assert result == "join_key_format"


def test_diagnose_domain_knowledge_gap(corrector):
    assert corrector.diagnose_failure("no results found", "") == "domain_knowledge_gap"


def test_diagnose_unknown(corrector):
    assert corrector.diagnose_failure("connection timeout", "") == "unknown"


# ── get_fix_strategy ─────────────────────────────────────────────────────────

def test_fix_strategy_syntax(corrector):
    strategy = corrector.get_fix_strategy("syntax_error", "syntax error near x", "schema")
    assert "syntax" in strategy.lower() or "fix" in strategy.lower()


def test_fix_strategy_wrong_table(corrector):
    strategy = corrector.get_fix_strategy("wrong_table", "table not found", "TABLE: review")
    assert "TABLE: review" in strategy


def test_fix_strategy_join_key(corrector):
    strategy = corrector.get_fix_strategy("join_key_format", "type mismatch", "schema")
    assert "cast" in strategy.lower() or "normalize" in strategy.lower()


# ── correct() strips markdown from output ────────────────────────────────────

def test_correct_strips_markdown_from_llm_output(corrector):
    corrector.client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="```sql\nSELECT COUNT(*) FROM review\n```"))]
    )
    result = corrector.correct("q", "bad query", "syntax error", "duckdb", "schema", 0)
    assert not result.startswith("```")
    assert "SELECT" in result

"""tests/test_agent_core_utils.py — Agent core utility functions (no LLM calls)."""
from agent.agent_core import _extract_business_refs, _looks_like_query, _strip_markdown

# ── _strip_markdown ──────────────────────────────────────────────────────────

class TestStripMarkdown:
    def test_plain_text_unchanged(self):
        assert _strip_markdown("SELECT 1") == "SELECT 1"

    def test_sql_fence(self):
        assert _strip_markdown("```sql\nSELECT 1\n```") == "SELECT 1"

    def test_json_fence(self):
        assert _strip_markdown('```json\n[{"$match": {}}]\n```') == '[{"$match": {}}]'

    def test_fence_no_lang(self):
        assert _strip_markdown("```\nSELECT 1\n```") == "SELECT 1"

    def test_no_closing_fence(self):
        result = _strip_markdown("```sql\nSELECT 1")
        assert "SELECT 1" in result
        assert "```" not in result

    def test_embedded_fence_after_text(self):
        text = "Here is a query:\n```sql\nSELECT 1\n```"
        result = _strip_markdown(text)
        assert result == "SELECT 1"

    def test_strips_leading_trailing_whitespace(self):
        result = _strip_markdown("```sql\n  SELECT 1  \n```")
        assert result == "SELECT 1"

    def test_multiline_sql_preserved(self):
        sql = "SELECT\n  AVG(rating)\nFROM review\nWHERE business_ref = 'x'"
        fenced = f"```sql\n{sql}\n```"
        result = _strip_markdown(fenced)
        assert result == sql


# ── _looks_like_query ────────────────────────────────────────────────────────

class TestLooksLikeQuery:
    def test_select_is_sql(self):
        assert _looks_like_query("SELECT COUNT(*) FROM review", "duckdb") is True

    def test_with_cte_is_sql(self):
        assert _looks_like_query("WITH cte AS (SELECT 1) SELECT * FROM cte", "duckdb") is True

    def test_json_array_is_mongodb(self):
        assert _looks_like_query('[{"$match": {}}]', "mongodb") is True

    def test_json_object_is_mongodb(self):
        assert _looks_like_query('{"$collection": "business"}', "mongodb") is True

    def test_text_is_not_sql(self):
        assert _looks_like_query("I cannot generate this query because...", "duckdb") is False

    def test_fence_is_not_query(self):
        assert _looks_like_query("```sql\nSELECT 1\n```", "duckdb") is False

    def test_empty_string_is_not_query(self):
        assert _looks_like_query("", "duckdb") is False


# ── _extract_business_refs ───────────────────────────────────────────────────

class TestExtractBusinessRefs:
    def test_basic_conversion(self):
        docs = [{"business_id": "businessid_52"}, {"business_id": "businessid_84"}]
        refs = _extract_business_refs(docs)
        assert refs == ["businessref_52", "businessref_84"]

    def test_ignores_docs_without_business_id(self):
        docs = [{"name": "Acme"}, {"business_id": "businessid_10"}]
        refs = _extract_business_refs(docs)
        assert refs == ["businessref_10"]

    def test_ignores_wrong_prefix(self):
        docs = [{"business_id": "someotherid_10"}]
        refs = _extract_business_refs(docs)
        assert refs == []

    def test_empty_input(self):
        assert _extract_business_refs([]) == []

    def test_handles_dict_with_rows_key(self):
        result = {"rows": [{"business_id": "businessid_1"}]}
        refs = _extract_business_refs(result)
        assert refs == ["businessref_1"]

    def test_preserves_numeric_suffix(self):
        docs = [{"business_id": "businessid_999"}]
        assert _extract_business_refs(docs) == ["businessref_999"]

    def test_multiple_businesses(self):
        docs = [{"business_id": f"businessid_{i}"} for i in range(5)]
        refs = _extract_business_refs(docs)
        assert len(refs) == 5
        assert "businessref_0" in refs
        assert "businessref_4" in refs

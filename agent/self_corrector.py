import re

from openai import OpenAI

from agent import llm_client
from agent.prompt_library import PromptLibrary

_MARKDOWN_FENCE = re.compile(r"```[\w]*\n?([\s\S]*?)```")


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing fence
        return "\n".join(lines).strip()
    match = _MARKDOWN_FENCE.search(text)
    return match.group(1).strip() if match else text


class SelfCorrector:

    def __init__(self, prompt_library: PromptLibrary, client: OpenAI):
        self.prompts = prompt_library
        self.client = client
        self.max_retries = 3

    def correct(self, original_question: str, failed_query: str, error: str,
                db_type: str, schema: str, attempt: int) -> str:
        """Generate a corrected query. Diagnoses failure type first to pick the right strategy."""
        failure_type = self.diagnose_failure(error, failed_query)
        fix_strategy = self.get_fix_strategy(failure_type, error, schema)
        prompt = self.prompts.self_correct(
            original_question, failed_query, error, db_type, schema, fix_strategy
        )
        return _strip_markdown(llm_client.call(self.client, prompt, max_tokens=512))

    def diagnose_failure(self, error: str, query: str) -> str:
        """Categorize the failure into one of 4 types to guide correction strategy."""
        e = error.lower()
        syntax_kws = ["syntax error", "parse error", "unexpected token", "invalid input syntax"]
        cast_kws = ["type mismatch", "cannot cast", "operator does not exist", "invalid cast"]
        table_kws = ["table", "relation", "collection", "does not exist", "unknown field"]
        if any(k in e for k in syntax_kws):
            return "syntax_error"
        if any(k in e for k in cast_kws):
            return "join_key_format"
        if any(k in e for k in table_kws):
            return "wrong_table"
        if any(k in e for k in ["no results", "empty", "null", "zero rows"]):
            return "domain_knowledge_gap"
        return "unknown"

    def get_fix_strategy(self, failure_type: str, error: str, schema: str) -> str:
        strategies = {
            "syntax_error": (
                f"Fix SQL/query syntax. Error: {error}. "
                "If the error is near an apostrophe (e.g. \"Children's\"), "
                "use doubled single quotes in SQL: 'Children''s Books' — NEVER backslash escaping."
            ),
            "wrong_table": (
                f"Check schema for correct table/collection names.\nSchema:\n{schema}\n"
                "IMPORTANT: PostgreSQL and SQLite are separate databases — "
                "do NOT write a single SQL query that references tables from both. "
                "Query each database independently."
            ),
            "join_key_format": (
                "Normalize join key types (e.g., cast integer to varchar or vice versa)"
            ),
            "domain_knowledge_gap": (
                "Check domain KB for correct field values, status codes, or fiscal periods"
            ),
            "unknown": f"Analyze error and regenerate query. Error: {error}",
        }
        return strategies[failure_type]

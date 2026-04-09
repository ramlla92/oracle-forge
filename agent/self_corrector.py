from openai import OpenAI
from agent.prompt_library import PromptLibrary
from agent import llm_client


class SelfCorrector:

    def __init__(self, prompt_library: PromptLibrary, client: OpenAI):
        self.prompts = prompt_library
        self.client = client
        self.max_retries = 3

    def correct(self, original_question: str, failed_query: str, error: str,
                db_type: str, schema: str, attempt: int) -> str:
        """Generate a corrected query. Diagnoses failure type first to pick the right fix strategy."""
        failure_type = self.diagnose_failure(error, failed_query)
        fix_strategy = self.get_fix_strategy(failure_type, error, schema)
        prompt = self.prompts.self_correct(
            original_question, failed_query, error, db_type, schema, fix_strategy
        )
        return llm_client.call(self.client, prompt, max_tokens=512)

    def diagnose_failure(self, error: str, query: str) -> str:
        """Categorize the failure into one of 4 types to guide correction strategy."""
        e = error.lower()
        if any(k in e for k in ["syntax error", "parse error", "unexpected token", "invalid input syntax"]):
            return "syntax_error"
        if any(k in e for k in ["type mismatch", "cannot cast", "operator does not exist", "invalid cast"]):
            return "join_key_format"
        if any(k in e for k in ["table", "relation", "collection", "does not exist", "unknown field"]):
            return "wrong_table"
        if any(k in e for k in ["no results", "empty", "null", "zero rows"]):
            return "domain_knowledge_gap"
        return "unknown"

    def get_fix_strategy(self, failure_type: str, error: str, schema: str) -> str:
        strategies = {
            "syntax_error": f"Fix SQL/query syntax. Error: {error}",
            "wrong_table": f"Check schema for correct table/collection names.\nSchema:\n{schema}",
            "join_key_format": "Normalize join key types (e.g., cast integer to varchar or vice versa)",
            "domain_knowledge_gap": "Check domain KB for correct field values, status codes, or fiscal periods",
            "unknown": f"Analyze error and regenerate query. Error: {error}",
        }
        return strategies[failure_type]

import json
import os
from datetime import datetime

from agent.models import QueryRequest, AgentResponse, QueryTrace, SubQuery
from agent.prompt_library import PromptLibrary
from agent.context_manager import ContextManager
from agent.self_corrector import SelfCorrector
from agent import llm_client


class AgentCore:

    def __init__(self, context_manager: ContextManager, prompt_library: PromptLibrary):
        self.client = llm_client.get_client()
        self.ctx = context_manager
        self.prompts = prompt_library
        self.corrector = SelfCorrector(prompt_library, self.client)

    def analyze_intent(self, question: str, available_databases: list[str]) -> dict:
        """Call LLM to identify which DBs to query and extract structured intent.

        Returns: {"target_databases": [...], "intent_summary": str, "requires_join": bool, "data_fields_needed": [...]}
        """
        system_context = self.ctx.get_full_context()
        prompt = self.prompts.intent_analysis(question, available_databases)
        text = llm_client.call(self.client, prompt, system=system_context, max_tokens=1024)
        return json.loads(text)

    def decompose_query(self, question: str, intent: dict) -> list[SubQuery]:
        """Break multi-DB intent into one SubQuery per target database."""
        sub_queries = []
        for db_type in intent.get("target_databases", []):
            query = self._generate_query_for_db(question, db_type, intent)
            sub_queries.append(SubQuery(
                database_type=db_type,
                query=query,
                intent=intent.get("intent_summary", question),
            ))
        return sub_queries

    def _generate_query_for_db(self, question: str, db_type: str, intent: dict) -> str:
        """Generate a query string for a specific database type."""
        # Schema is loaded from context — stub returns placeholder until AGENT.md has real schema
        schema = self._get_schema_for_db(db_type)
        if db_type == "mongodb":
            prompt = self.prompts.nl_to_mongodb(question, schema)
        else:
            prompt = self.prompts.nl_to_sql(question, schema, dialect=db_type)

        return llm_client.call(self.client, prompt, max_tokens=512)

    def _get_schema_for_db(self, db_type: str) -> str:
        """Return schema string for the given DB type. Populated once AGENT.md has real schemas."""
        # TODO (Day 5): replace with real schema parsed from AGENT.md via ContextManager
        return f"# Schema for {db_type}\n(See AGENT.md for full schema — populate before first run)"

    async def run(self, request: QueryRequest, query_executor=None) -> AgentResponse:
        """Main orchestration loop: analyze → decompose → execute → synthesize → log."""
        self_corrections: list[dict] = []
        raw_results: dict = {}
        merge_operations: list[str] = []

        intent = self.analyze_intent(request.question, request.available_databases)
        sub_queries = self.decompose_query(request.question, intent)

        for sq in sub_queries:
            result, corrections = self._execute_with_retry(sq, request.question)
            raw_results[sq.database_type] = result
            self_corrections.extend(corrections)

        answer = self._synthesize(request.question, raw_results)

        trace = QueryTrace(
            timestamp=datetime.utcnow().isoformat(),
            sub_queries=sub_queries,
            databases_used=list(raw_results.keys()),
            self_corrections=self_corrections,
            raw_results=raw_results,
            merge_operations=merge_operations,
        )
        response = AgentResponse(answer=answer, query_trace=trace, confidence=0.8)
        self._log_run(request, response, intent, sub_queries, self_corrections)
        self.ctx.add_to_session(request.question, answer[:200])
        return response

    def _execute_with_retry(self, sub_query: SubQuery, original_question: str):
        """Execute a sub-query, retrying up to max_retries on failure with self-correction."""
        corrections = []
        current_query = sub_query.query
        schema = self._get_schema_for_db(sub_query.database_type)

        for attempt in range(self.corrector.max_retries + 1):
            try:
                result = self._call_mcp(sub_query.database_type, current_query)
                return result, corrections
            except Exception as e:
                error_str = str(e)
                if attempt == self.corrector.max_retries:
                    return {"error": error_str}, corrections

                corrected = self.corrector.correct(
                    original_question, current_query, error_str,
                    sub_query.database_type, schema, attempt
                )
                failure_type = self.corrector.diagnose_failure(error_str, current_query)
                corrections.append({
                    "attempt": attempt + 1,
                    "failure_type": failure_type,
                    "original_query": current_query,
                    "corrected_query": corrected,
                    "error": error_str,
                })
                self.ctx.append_correction(
                    query=original_question,
                    what_went_wrong=f"{failure_type}: {error_str}",
                    correct_approach=corrected,
                )
                current_query = corrected

        return {"error": "max retries exceeded"}, corrections

    def _call_mcp(self, db_type: str, query: str) -> dict:
        """Call MCP Toolbox over HTTP. Driver 1's QueryExecutor replaces this stub."""
        # TODO (Driver 1): replace with real MCP HTTP call via QueryExecutor
        raise NotImplementedError(f"MCP call not wired yet for {db_type}")

    def _synthesize(self, question: str, raw_results: dict) -> str:
        prompt = self.prompts.synthesize_response(question, raw_results, {})
        return llm_client.call(self.client, prompt, max_tokens=512)

    def _log_run(self, request: QueryRequest, response: AgentResponse,
                 intent: dict, sub_queries: list[SubQuery], self_corrections: list[dict]):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": request.question,
            "identified_databases": intent.get("target_databases", []),
            "sub_queries": [sq.model_dump() for sq in sub_queries],
            "self_corrections": self_corrections,
            "answer": response.answer,
            "confidence": response.confidence,
            "error": response.error,
        }
        os.makedirs("eval/run_logs", exist_ok=True)
        fname = f"eval/run_logs/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(fname, "w") as f:
            json.dump(log_entry, f, indent=2)

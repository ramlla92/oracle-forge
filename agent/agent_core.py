import json
import os
import re
from datetime import datetime

from agent import llm_client
from agent.context_manager import ContextManager
from agent.models import AgentResponse, QueryRequest, QueryTrace, SubQuery
from agent.prompt_library import PromptLibrary
from agent.query_executor import QueryExecutor
from agent.self_corrector import SelfCorrector


class AgentCore:

    def __init__(self, context_manager: ContextManager, prompt_library: PromptLibrary):
        self.client = llm_client.get_client()
        self.ctx = context_manager
        self.prompts = prompt_library
        self.corrector = SelfCorrector(prompt_library, self.client)
        self.executor = QueryExecutor()

    def analyze_intent(self, question: str, available_databases: list[str]) -> dict:
        """Call LLM to identify which DBs to query and extract structured intent.

        Returns: {"target_databases": [...], "intent_summary": str,
                  "requires_join": bool, "data_fields_needed": [...]}
        """
        system_context = self.ctx.get_full_context()
        prompt = self.prompts.intent_analysis(question, available_databases)
        text = llm_client.call(self.client, prompt, system=system_context, max_tokens=1024)
        return json.loads(_strip_markdown(text))

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
        schema = self.ctx.get_schema_for_db(db_type)
        system_context = self.ctx.get_full_context()
        if db_type == "mongodb":
            prompt = self.prompts.nl_to_mongodb(question, schema)
        else:
            prompt = self.prompts.nl_to_sql(question, schema, dialect=db_type)

        raw = llm_client.call(self.client, prompt, system=system_context, max_tokens=512)
        cleaned = _strip_markdown(raw)
        if not _looks_like_query(cleaned, db_type):
            raise ValueError(f"LLM returned non-query text for {db_type}: {cleaned[:120]}")
        return cleaned

    async def run(self, request: QueryRequest, query_executor=None) -> AgentResponse:
        """Main orchestration loop: analyze → decompose → execute → synthesize → log."""
        self_corrections: list[dict] = []
        raw_results: dict = {}
        merge_operations: list[str] = []

        intent = self.analyze_intent(request.question, request.available_databases)
        sub_queries = self.decompose_query(request.question, intent)

        mongo_sq = next((sq for sq in sub_queries if sq.database_type == "mongodb"), None)
        duck_sq  = next((sq for sq in sub_queries if sq.database_type == "duckdb"),  None)

        if mongo_sq and duck_sq:
            # Sequential join: run MongoDB first, translate business_ids → business_refs,
            # regenerate DuckDB query filtered to exactly those refs.
            mongo_result, mongo_corr = self._execute_with_retry(mongo_sq, request.question)
            raw_results["mongodb"] = mongo_result
            self_corrections.extend(mongo_corr)

            business_refs = _extract_business_refs(mongo_result)
            if business_refs:
                try:
                    new_query = self._generate_duckdb_with_refs(
                        request.question, intent, business_refs
                    )
                    duck_sq = SubQuery(
                        database_type="duckdb",
                        query=new_query,
                        intent=duck_sq.intent,
                    )
                    merge_operations.append(
                        f"mongo→duckdb join on {len(business_refs)} business_refs"
                    )
                except ValueError:
                    # LLM returned non-query — keep original duck_sq
                    pass
            duck_result, duck_corr = self._execute_with_retry(duck_sq, request.question)
            raw_results["duckdb"] = duck_result
            self_corrections.extend(duck_corr)

            # Replace duck_sq in sub_queries for the trace
            sub_queries = [mongo_sq if sq.database_type == "mongodb" else duck_sq
                           for sq in sub_queries]
        else:
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
        schema = self.ctx.get_schema_for_db(sub_query.database_type)

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
                    what_went_wrong=error_str,
                    correct_approach=corrected,
                    failure_category=failure_type,
                )
                current_query = corrected

        return {"error": "max retries exceeded"}, corrections

    def _generate_duckdb_with_refs(
        self, question: str, intent: dict, business_refs: list[str]
    ) -> str:
        """Generate a DuckDB query pre-filtered to specific business_refs from MongoDB results."""
        refs_sql = ", ".join(f"'{r}'" for r in business_refs)
        schema = self.ctx.get_schema_for_db("duckdb")
        system_context = self.ctx.get_full_context()
        prompt = self.prompts.nl_to_sql_with_refs(question, schema, refs_sql)
        raw = llm_client.call(self.client, prompt, system=system_context, max_tokens=512)
        cleaned = _strip_markdown(raw)
        if not _looks_like_query(cleaned, "duckdb"):
            raise ValueError(f"LLM returned non-query text for duckdb: {cleaned[:120]}")
        return cleaned

    def _call_mcp(self, db_type: str, query: str) -> dict:
        """Call the MCP server (Python replacement for toolbox binary) via QueryExecutor."""
        sub_query = SubQuery(database_type=db_type, query=query, intent="")
        return self.executor.execute(sub_query)

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


_MARKDOWN_FENCE = re.compile(r"```[\w]*\n?([\s\S]*?)```")


def _strip_markdown(text: str) -> str:
    """Strip markdown code fences. Line-based for fences at start, regex for embedded fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence line (```lang)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing fence
        return "\n".join(lines).strip()
    # LLM may prepend explanation text before the fence — extract the fenced block
    match = _MARKDOWN_FENCE.search(text)
    return match.group(1).strip() if match else text


def _looks_like_query(text: str, db_type: str) -> bool:
    """Return False if the text looks like LLM reasoning rather than a query."""
    t = text.strip().lower()
    if db_type == "mongodb":
        return t.startswith("[") or t.startswith("{")
    return any(t.startswith(k) for k in ("select", "with", "insert", "update", "delete", "explain"))


def _extract_business_refs(mongo_result) -> list[str]:
    """Convert MongoDB business_id values to DuckDB business_ref format."""
    docs = mongo_result if isinstance(mongo_result, list) else mongo_result.get("rows", [])
    refs = []
    for doc in docs:
        bid = doc.get("business_id", "")
        if bid.startswith("businessid_"):
            n = bid.split("businessid_", 1)[1]
            refs.append(f"businessref_{n}")
    return refs



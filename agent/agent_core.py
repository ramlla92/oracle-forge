import json
import os
import re
from collections import defaultdict
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
        intent = json.loads(_strip_markdown(text))
        return _enforce_intent_db_coverage(question, available_databases, intent)

    def decompose_query(self, question: str, intent: dict) -> list[SubQuery]:
        """Break multi-DB intent into one SubQuery per target database."""
        requires_join = intent.get("requires_join", False)
        join_direction = intent.get("join_direction", "mongodb_first")
        sub_queries = []
        for db_type in intent.get("target_databases", []):
            if requires_join and join_direction == "mongodb_first" and db_type == "duckdb":
                # Placeholder — DuckDB query regenerated with business_refs after MongoDB runs
                sub_queries.append(SubQuery(
                    database_type=db_type,
                    query="SELECT 1",
                    intent=intent.get("intent_summary", question),
                ))
            elif requires_join and join_direction == "duckdb_first" and db_type == "mongodb":
                # Placeholder — MongoDB query regenerated with business_ids after DuckDB runs
                _placeholder_query = (
                    '[{"$collection": "business"}, '
                    '{"$project": {"business_id": 1, "name": 1, "description": 1}}]'
                )
                sub_queries.append(SubQuery(
                    database_type=db_type,
                    query=_placeholder_query,
                    intent=intent.get("intent_summary", question),
                ))
            elif requires_join and join_direction == "duckdb_first" and db_type == "duckdb":
                # Placeholder — DuckDB query will be generated/overridden in run() once
                # the direction is confirmed and the correct template is chosen (e.g.
                # deterministic user-category query). This prevents a LLM ValueError here
                # from crashing the whole run before run() can apply the right override.
                sub_queries.append(SubQuery(
                    database_type=db_type,
                    query="SELECT 1",
                    intent=intent.get("intent_summary", question),
                ))
            else:
                try:
                    query = self._generate_query_for_db(question, db_type, intent)
                except ValueError:
                    # LLM returned unparseable output — use a safe no-op placeholder so
                    # the run() orchestration can still decide what to do.
                    query = "SELECT 1" if db_type != "mongodb" else (
                        '[{"$collection": "business"}, '
                        '{"$project": {"business_id": 1, "name": 1, "description": 1}}]'
                    )
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
            base_prompt = self.prompts.nl_to_mongodb(question, schema)
        else:
            base_prompt = self.prompts.nl_to_sql(question, schema, dialect=db_type)

        last_error = None
        for attempt in range(3):
            prompt = base_prompt
            if attempt > 0 and last_error:
                prompt += (
                    f"\n\nPrevious attempt was rejected: {last_error}. "
                    f"Fix the issue and return only a valid {db_type} query."
                )
            raw = llm_client.call(self.client, prompt, system=system_context, max_tokens=512)
            cleaned = _strip_markdown(raw)
            try:
                if not _looks_like_query(cleaned, db_type):
                    raise ValueError(f"LLM returned non-query text for {db_type}: {cleaned[:120]}")
                _validate_query_semantics(question, db_type, cleaned)
                return cleaned
            except ValueError as exc:
                last_error = exc
                continue
        raise ValueError(
            f"Could not generate a valid {db_type} query after 3 attempts. Last error: {last_error}"
        ) from last_error

    async def run(self, request: QueryRequest, query_executor=None) -> AgentResponse:
        """Main orchestration loop: analyze → decompose → execute → synthesize → log."""
        self_corrections: list[dict] = []
        raw_results: dict = {}
        merge_operations: list[str] = []

        intent = self.analyze_intent(request.question, request.available_databases)
        is_category_q = intent.get("is_category_question", False)
        sub_queries = self.decompose_query(request.question, intent)

        mongo_sq = next((sq for sq in sub_queries if sq.database_type == "mongodb"), None)
        duck_sq  = next((sq for sq in sub_queries if sq.database_type == "duckdb"),  None)

        join_direction = intent.get("join_direction", "mongodb_first")

        q_lower_check = request.question.lower()
        # State aggregation always requires MongoDB data (attribute filter + description for state).
        # Override any duckdb_first direction the LLM may have chosen for state questions.
        if _is_state_aggregation_question(q_lower_check):
            join_direction = "mongodb_first"
        # User-based category questions (e.g. "categories most reviewed by users registered in
        # YEAR") require DuckDB first to identify business_refs from user/review tables.
        elif _is_user_category_question(q_lower_check):
            join_direction = "duckdb_first"

        if mongo_sq and duck_sq and join_direction == "duckdb_first":
            # DuckDB-first join: run DuckDB first to find top business_refs,
            # then look up MongoDB for names/categories.

            # For user-category questions (e.g. "categories most reviewed by users
            # registered in 2016"), generate a deterministic DuckDB query that groups
            # by business_ref — NOT by category (categories live in MongoDB, not DuckDB).
            if _is_user_category_question(request.question.lower()):
                year_match = re.search(r'\b(20\d\d|19\d\d)\b', request.question)
                year = year_match.group(1) if year_match else ""
                year_filter = f"AND u.yelping_since LIKE '%{year}%'" if year else ""
                user_cat_query = (
                    "SELECT r.business_ref, COUNT(*) AS review_count "
                    "FROM review r JOIN user u ON r.user_id = u.user_id "
                    f"WHERE 1=1 {year_filter} "
                    "GROUP BY r.business_ref ORDER BY review_count DESC"
                )
                duck_sq = SubQuery(
                    database_type="duckdb",
                    query=user_cat_query,
                    intent=duck_sq.intent,
                )

            # If the direction was overridden to duckdb_first AFTER decompose_query already
            # placed a SELECT 1 placeholder for DuckDB (because the LLM returned mongodb_first),
            # we need to regenerate a real DuckDB query now.
            elif duck_sq.query.strip().upper() == "SELECT 1":
                try:
                    real_duck_query = self._generate_query_for_db(
                        request.question, "duckdb", intent
                    )
                    duck_sq = SubQuery(
                        database_type="duckdb",
                        query=real_duck_query,
                        intent=duck_sq.intent,
                    )
                except ValueError:
                    pass  # fall through with SELECT 1 — will still fail gracefully

            # If this is a category-ranking question, remove any LIMIT from the DuckDB query
            # so we get ALL business_refs (category aggregation needs all, not just top N).
            if is_category_q:
                duck_sq = SubQuery(
                    database_type=duck_sq.database_type,
                    query=_remove_limit_clause(duck_sq.query),
                    intent=duck_sq.intent,
                )
            duck_result, duck_corr = self._execute_with_retry(duck_sq, request.question)
            raw_results["duckdb"] = duck_result
            self_corrections.extend(duck_corr)

            duck_refs = _extract_refs_from_duck_result(duck_result)
            if duck_refs:
                try:
                    new_mongo_query = self._generate_mongodb_with_ids(
                        request.question, intent, duck_refs
                    )
                    mongo_sq = SubQuery(
                        database_type="mongodb",
                        query=new_mongo_query,
                        intent=mongo_sq.intent,
                    )
                    merge_operations.append(
                        f"duckdb→mongo lookup on {len(duck_refs)} business_refs"
                    )
                except ValueError:
                    pass  # keep placeholder MongoDB query
            mongo_result, mongo_corr = self._execute_with_retry(mongo_sq, request.question)
            raw_results["mongodb"] = mongo_result
            self_corrections.extend(mongo_corr)

            # Replace sub_queries for the trace
            sub_queries = [duck_sq if sq.database_type == "duckdb" else mongo_sq
                           for sq in sub_queries]

        elif mongo_sq and duck_sq:
            # MongoDB-first join: run MongoDB first, translate business_ids → business_refs,
            # regenerate DuckDB query filtered to exactly those refs.
            q_lower = request.question.lower()

            # For state questions, force MongoDB to return individual docs (no $group)
            if _is_state_aggregation_question(q_lower):
                mongo_sq = _strip_state_grouping(mongo_sq)

            mongo_result, mongo_corr = self._execute_with_retry(mongo_sq, request.question)
            raw_results["mongodb"] = mongo_result
            self_corrections.extend(mongo_corr)

            # For category-ranking questions, use Python extraction instead of MongoDB grouping
            if is_category_q:
                cat_refs, top_cat_name, top_cat_count = _compute_top_category_refs(mongo_result)
                if cat_refs:
                    business_refs = cat_refs
                    raw_results["mongodb"] = {
                        "top_category": top_cat_name,
                        "business_count": top_cat_count,
                        "category_analysis": "Python-extracted from descriptions",
                    }
                    merge_operations.append(
                        f"python category analysis → {top_cat_name} ({top_cat_count} refs)"
                    )
                else:
                    business_refs = _extract_business_refs(mongo_result)

            elif _is_state_aggregation_question(q_lower):
                # Python state aggregation — avoid unreliable MongoDB $addFields/$split
                state_to_refs = _group_refs_by_state(mongo_result)

                if _needs_review_count_for_state(q_lower):
                    # "most reviews" question: need DuckDB counts to rank states
                    all_refs = [r for refs in state_to_refs.values() for r in refs]
                    if not all_refs:
                        # MongoDB failed to return usable results — skip DuckDB and synthesize error
                        raw_results["mongodb"] = {"error": "No state data returned from MongoDB"}
                        answer = self._synthesize(request.question, raw_results)
                        trace = QueryTrace(
                            timestamp=datetime.utcnow().isoformat(),
                            sub_queries=sub_queries,
                            databases_used=list(raw_results.keys()),
                            self_corrections=self_corrections,
                            raw_results=raw_results,
                            merge_operations=merge_operations,
                        )
                        response = AgentResponse(answer=answer, query_trace=trace, confidence=0.3)
                        self._log_run(request, response, intent, sub_queries, self_corrections)
                        self.ctx.add_to_session(request.question, answer[:200])
                        return response
                    refs_sql = ", ".join(f"'{r}'" for r in all_refs)
                    count_sql = (
                        f"SELECT business_ref, COUNT(*) AS review_count, "
                        f"AVG(rating) AS avg_rating FROM review "
                        f"WHERE business_ref IN ({refs_sql}) GROUP BY business_ref"
                    )
                    count_result = self._call_mcp("duckdb", count_sql)
                    top_state, top_refs, review_count, avg_rating = (
                        _compute_top_state_by_reviews(state_to_refs, count_result)
                    )
                    if top_state:
                        raw_results["mongodb"] = {
                            "top_state": top_state,
                            "review_count": review_count,
                        }
                        raw_results["duckdb"] = {
                            "avg_rating": round(avg_rating, 6),
                            "review_count": review_count,
                        }
                        merge_operations.append(
                            f"python state aggregation (reviews) → {top_state} "
                            f"({review_count} reviews, avg {avg_rating:.4f})"
                        )
                        # Both results already set — skip normal DuckDB execution
                        sub_queries = [mongo_sq if sq.database_type == "mongodb" else duck_sq
                                       for sq in sub_queries]
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
                else:
                    # "most businesses with attribute X per state" — just count MongoDB docs
                    if state_to_refs:
                        top_state = max(state_to_refs, key=lambda s: len(state_to_refs[s]))
                        business_refs = state_to_refs[top_state]
                        raw_results["mongodb"] = {
                            "top_state": top_state,
                            "business_count": len(business_refs),
                        }
                        merge_operations.append(
                            f"python state aggregation (count) → {top_state} "
                            f"({len(business_refs)} businesses)"
                        )
                    else:
                        business_refs = _extract_business_refs(mongo_result)
            else:
                business_refs = _extract_business_refs(mongo_result)
            # True when Python has already resolved the group (top state or top category)
            # and DuckDB only needs to compute a single AVG(rating) across those refs.
            _needs_deterministic_avg = is_category_q or (
                _is_state_aggregation_question(q_lower_check)
                and not _needs_review_count_for_state(q_lower_check)
                and ("average rating" in q_lower_check or "avg rating" in q_lower_check)
            )

            if business_refs:
                if _needs_deterministic_avg:
                    # Group already resolved by Python. DuckDB only needs AVG(rating).
                    # Use a deterministic template — LLM can't accidentally emit COUNT/GROUP BY.
                    refs_sql = ", ".join(f"'{r}'" for r in business_refs)
                    avg_query = (
                        f"SELECT AVG(rating) AS avg_rating "
                        f"FROM review WHERE business_ref IN ({refs_sql})"
                    )
                    duck_sq = SubQuery(
                        database_type="duckdb",
                        query=avg_query,
                        intent=duck_sq.intent,
                    )
                    merge_operations.append(
                        f"deterministic avg_rating over {len(business_refs)} refs"
                    )
                try:
                    if not _needs_deterministic_avg:
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
                    # LLM returned non-query with refs — generate a plain DuckDB query
                    try:
                        fallback_query = self._generate_query_for_db(
                            request.question, "duckdb", intent
                        )
                        duck_sq = SubQuery(
                            database_type="duckdb",
                            query=fallback_query,
                            intent=duck_sq.intent,
                        )
                    except ValueError:
                        pass  # keep placeholder, execution will return an error
            else:
                # No refs from MongoDB — generate a plain DuckDB query (no join filter)
                try:
                    fallback_query = self._generate_query_for_db(
                        request.question, "duckdb", intent
                    )
                    duck_sq = SubQuery(
                        database_type="duckdb",
                        query=fallback_query,
                        intent=duck_sq.intent,
                    )
                except ValueError:
                    pass
            duck_result, duck_corr = self._execute_with_retry(duck_sq, request.question)
            raw_results["duckdb"] = duck_result
            self_corrections.extend(duck_corr)

            # Replace duck_sq in sub_queries for the trace
            sub_queries = [mongo_sq if sq.database_type == "mongodb" else duck_sq
                           for sq in sub_queries]
        else:
            # Generic multi-DB path — handles postgresql+sqlite, and any other combination
            pg_sq   = next(
                (sq for sq in sub_queries
                 if sq.database_type in ("postgresql", "postgresql_bookreview")),
                None,
            )
            sql_sq  = next((sq for sq in sub_queries if sq.database_type == "sqlite"), None)

            if pg_sq and sql_sq:
                # PostgreSQL-first: get IDs from PostgreSQL, filter SQLite by those IDs
                pg_result, pg_corr = self._execute_with_retry(pg_sq, request.question)
                raw_results["postgresql"] = pg_result
                self_corrections.extend(pg_corr)

                # Extract book_ids from PostgreSQL result and convert to purchase_ids for SQLite
                pg_ids = _extract_pg_ids(pg_result)
                if pg_ids:
                    try:
                        purchase_ids_sql = ", ".join(f"'purchaseid_{i}'" for i in pg_ids)
                        new_sql_query = self._generate_sqlite_with_ids(
                            request.question, self.ctx.get_schema_for_db("sqlite"),
                            purchase_ids_sql
                        )
                        sql_sq = SubQuery(
                            database_type="sqlite",
                            query=new_sql_query,
                            intent=sql_sq.intent,
                        )
                        merge_operations.append(
                            f"postgresql→sqlite join on {len(pg_ids)} book ids"
                        )
                    except ValueError:
                        pass

                sql_result, sql_corr = self._execute_with_retry(sql_sq, request.question)
                self_corrections.extend(sql_corr)

                # Python merge: join PostgreSQL book metadata with SQLite avg_rating results.
                # review.purchase_id = "purchaseid_N" matches books_info.book_id = "bookid_N".
                merged_books = _merge_pg_sqlite_results(pg_result, sql_result)
                if merged_books:
                    raw_results["books"] = merged_books
                    raw_results.pop("postgresql", None)
                else:
                    # No matches — keep both raw results so synthesizer can explain
                    raw_results["sqlite"] = sql_result

                sub_queries = [
                    pg_sq if sq.database_type in ("postgresql", "postgresql_bookreview")
                    else sql_sq
                    for sq in sub_queries
                ]
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
                try:
                    self.ctx.append_correction(
                        query=original_question,
                        what_went_wrong=error_str,
                        correct_approach=corrected,
                        failure_category=failure_type,
                    )
                except OSError:
                    pass  # never let corrections I/O crash a query
                current_query = corrected

        return {"error": "max retries exceeded"}, corrections

    def _generate_mongodb_with_ids(
        self, question: str, intent: dict, business_refs: list[str]
    ) -> str:
        """Generate a MongoDB lookup pipeline for specific business_refs from DuckDB results.
        Built directly in Python to avoid LLM token limits with large ID lists."""
        business_ids = [f"businessid_{r.split('businessref_')[1]}" for r in business_refs]
        pipeline = [
            {"$collection": "business"},
            {"$match": {"business_id": {"$in": business_ids}}},
            {"$project": {"business_id": 1, "name": 1, "description": 1}},
        ]
        return json.dumps(pipeline)

    def _generate_duckdb_with_refs(
        self, question: str, intent: dict, business_refs: list[str]
    ) -> str:
        """Generate a DuckDB query pre-filtered to specific business_refs from MongoDB results."""
        refs_sql = ", ".join(f"'{r}'" for r in business_refs)
        schema = self.ctx.get_schema_for_db("duckdb")
        system_context = self.ctx.get_full_context()
        base_prompt = self.prompts.nl_to_sql_with_refs(question, schema, refs_sql)
        last_error = None
        for attempt in range(3):
            prompt = base_prompt
            if attempt > 0 and last_error:
                prompt += (
                    f"\n\nPrevious attempt was rejected: {last_error}. "
                    "Fix the issue and return only a valid DuckDB SELECT query."
                )
            raw = llm_client.call(self.client, prompt, system=system_context, max_tokens=512)
            cleaned = _strip_markdown(raw)
            try:
                if not _looks_like_query(cleaned, "duckdb"):
                    raise ValueError(f"LLM returned non-query text for duckdb: {cleaned[:120]}")
                _validate_query_semantics(question, "duckdb", cleaned)
                return cleaned
            except ValueError as exc:
                last_error = exc
                continue
        raise ValueError(
            f"Could not generate a valid duckdb query after 3 attempts. Last error: {last_error}"
        ) from last_error

    def _call_mcp(self, db_type: str, query: str) -> dict:
        """Call the MCP server (Python replacement for toolbox binary) via QueryExecutor."""
        sub_query = SubQuery(database_type=db_type, query=query, intent="")
        return self.executor.execute(sub_query)

    def _generate_sqlite_with_ids(self, question: str, schema: str, purchase_ids_sql: str) -> str:
        """Generate a SQLite query filtered to specific purchase_ids from PostgreSQL results."""
        prompt = f"""Generate a SQLite query for this question.
The books have already been filtered by PostgreSQL. Now compute per-book rating metrics.
The query MUST use: WHERE purchase_id IN ({purchase_ids_sql})

Schema:
{schema}

Question: {question}

Rules:
- Use purchase_id IN (...) as the primary filter — this is mandatory
- Apply ALL other filters from the question (rating threshold, date range, etc.)
- For rating filters: GROUP BY purchase_id HAVING AVG(rating) >= threshold  (or = 5.0 for perfect)
- For date filters: use strftime('%Y', review_time) >= 'YEAR'
- CRITICAL: Return purchase_id and AVG(rating) as avg_rating ONLY — do NOT select the title
  column (review.title is a review headline written by users, NOT the book title;
  book titles come from PostgreSQL and will be joined back in Python)
- Return only the SQL query, no explanation, no markdown code fences"""
        raw = llm_client.call(self.client, prompt,
                              system=self.ctx.get_full_context(), max_tokens=512)
        cleaned = _strip_markdown(raw)
        if not _looks_like_query(cleaned, "sqlite"):
            raise ValueError(f"LLM returned non-query for sqlite: {cleaned[:120]}")
        return cleaned

    def _synthesize(self, question: str, raw_results: dict) -> str:
        enriched = _augment_with_category_aggregation(raw_results)
        prompt = self.prompts.synthesize_response(question, enriched, {})
        return llm_client.call(self.client, prompt, max_tokens=1024)

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


_CAT_EXTRACT_PATTERNS = [
    # Most-specific patterns first (avoid substring-of-phrase traps)
    r"in the categor(?:y|ies) of '([^']+)'",            # "in the category of 'X, Y'" (quoted)
    r'in the categor(?:y|ies) of ([^.\'"]+)\.',          # "in the category of X, Y." (unquoted)
    r'categories such as ([^.]+?)(?:\s+for\s|\s+to\s|\.)', # "categories such as X"
    r'eatery specializes in ([^.]+),',
    r'specializes in ([^.]+)\.',
    r'for ([^,]+(?:, [^,]+)*), perfect for',
    # Generic connectors (reliable and common — placed before optional connectors)
    r'including ([^.]+)\.',
    r'featuring ([^.]+)\.',
    # Less reliable connectors (may match non-category phrases — placed last)
    r'for enjoying ([^.]+)\.',                           # "for enjoying X, Y, Z."
    r'for those seeking ([^.]+)\.',                      # "for those seeking X, Y."
    r'options for ([A-Z][^.!]+)[.!]',                   # "options for X, Y." (must start capital)
    r'selection of ([^.]+?)\s+for\s+all',               # "selection of X for all"
    r'mix of ([^.]+?)(?:,\s*making|\s+making|\.)',      # "mix of X, Y, making"
    r'ranging from ([^.]+?)(?:\s+for\s+all|\s+to\s+meet|\s+making)',
    r'diverse experience with ([^.]+)\.',
]



def _compute_top_category_refs(mongo_result) -> tuple[list[str], str, int]:
    """From a list of business docs with descriptions, find the top category by business count.
    Returns: (refs_for_top_category, top_category_name, business_count)

    Confidence check: if parse yield is <30% of total docs, logs a warning so callers
    can decide whether to trust the result.
    """
    docs = mongo_result if isinstance(mongo_result, list) else mongo_result.get("rows", [])
    cat_to_refs: dict[str, list[str]] = defaultdict(list)
    parsed_count = 0
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        bid = doc.get("business_id", "")
        if not bid.startswith("businessid_"):
            continue
        bref = bid.replace("businessid_", "businessref_")
        desc = doc.get("description", "")
        cats = _extract_categories_from_description(desc)
        if cats:
            parsed_count += 1
        for cat in cats:
            cat_to_refs[cat].append(bref)

    total_docs = sum(
        1 for d in docs
        if isinstance(d, dict) and d.get("business_id", "").startswith("businessid_")
    )
    if total_docs > 0 and parsed_count / total_docs < 0.30:
        print(
            f"WARNING: category extraction low confidence — "
            f"parsed {parsed_count}/{total_docs} docs ({100*parsed_count//total_docs}%)",
            flush=True,
        )

    if not cat_to_refs:
        return [], "", 0

    # Merge plural/singular pairs that both appear in the data
    # (e.g. "Restaurant" + "Restaurants" → "Restaurant").
    # Only triggers when BOTH forms exist — "Arts", "News", "Business" are safe.
    for cat in list(cat_to_refs.keys()):
        if cat.endswith("s") and len(cat) > 3:
            singular = cat[:-1]
            if singular in cat_to_refs:
                cat_to_refs[singular].extend(cat_to_refs.pop(cat))

    # Find category with most businesses
    top_cat = max(cat_to_refs, key=lambda c: len(cat_to_refs[c]))
    top_refs = cat_to_refs[top_cat]
    top_count = len(top_refs)
    print(
        f"DEBUG category: top='{top_cat}' count={top_count} "
        f"parsed={parsed_count}/{total_docs}",
        flush=True,
    )
    return top_refs, top_cat, top_count


def _remove_limit_clause(sql: str) -> str:
    """Remove LIMIT N clause from a SQL query (used when we need all rows, not top N)."""
    return re.sub(r'\s+LIMIT\s+\d+\s*;?\s*$', '', sql, flags=re.IGNORECASE).strip()


def _extract_categories_from_description(desc: str) -> list[str]:
    """Extract category list from a MongoDB business description using a two-stage approach.

    Stage 1: Locate the category phrase span by finding the last occurrence of a
             known connector keyword. The categories always appear at the end of the
             description, so taking the substring after the last connector is robust.
    Stage 2: Split the span on commas, strip noise tokens, canonicalize to Title Case.

    Falls back to single-pass regex patterns (_CAT_EXTRACT_PATTERNS) for descriptions
    that don't follow the standard "offers X, Y, Z." tail format.
    """
    # Stage 1 — find the category span tail.
    # Connectors ordered from most-specific to most-generic to pick the best anchor.
    _CONNECTOR_RE = re.compile(
        r'(?:specializes in|categories such as|categories of|category of'
        r'|for enjoying|for those seeking|featuring|including'
        r'|diverse experience with|selection of|mix of|ranging from'
        r'|offers)\s+',
        re.IGNORECASE,
    )
    best_match = None
    for m in _CONNECTOR_RE.finditer(desc):
        best_match = m  # keep the LAST match — categories always end the sentence
    if best_match:
        span = desc[best_match.end():]
        cats = _tokenize_category_span(span)
        if cats:
            return cats

    # Stage 2 fallback — single-pass regex library (for non-standard formats)
    for pattern in _CAT_EXTRACT_PATTERNS:
        m = re.search(pattern, desc, re.IGNORECASE)
        if m:
            cats = _tokenize_category_span(m.group(1))
            if cats:
                return cats
    return []


def _tokenize_category_span(span: str) -> list[str]:
    """Split a raw category span string into clean, canonicalized category names."""
    # Trim trailing sentence punctuation and surrounding quotes
    span = span.rstrip('.!? ').strip("'\"")
    # Split on commas and " and " conjunctions
    raw = re.split(r',\s*|\s+and\s+', span)
    cats = []
    for c in raw:
        c = c.strip().strip("'\"")                              # strip embedded quotes
        c = re.sub(r'^\s*and\s+', '', c, flags=re.IGNORECASE)  # leading "and"
        # If the token contains a connective preposition, split further and check each part.
        # e.g. "Restaurants for all your dining needs" → ["Restaurants", "all your..."]
        # e.g. "options for Restaurants" → ["options", "Restaurants"]
        fragments = re.split(r'\s+(?:for|per|to)\s+', c, flags=re.IGNORECASE)
        for frag in fragments:
            frag = frag.strip().title()
            if not frag:
                continue
            # Discard noise: 2-letter state codes, address fragments, numeric strings,
            # overly long phrases (>40 chars = prose), >4-word phrases (= sentence fragment)
            if (len(frag) < 2 or len(frag) > 40
                    or len(frag.split()) > 4
                    or re.match(r'^[A-Z]{2}$', frag)
                    or re.search(r'\b(St\.|Dr\.|Ave|Blvd|Rd|Hwy)\b', frag)
                    or re.search(r'\d', frag)
                    or re.match(r'^(Options|Provides|Menu|Dishes|Items|Needs)$',
                                frag, re.IGNORECASE)):
                continue
            cats.append(frag)
    return cats


def _augment_with_category_aggregation(raw_results: dict) -> dict:
    """If results contain business_ref+review_count from DuckDB and descriptions from MongoDB,
    extract and aggregate categories by review_count and add to results."""
    mongo_data = raw_results.get("mongodb", [])
    duck_data = raw_results.get("duckdb", {})
    if not mongo_data or not duck_data:
        return raw_results

    # Build ref->count mapping from DuckDB rows
    duck_rows = duck_data if isinstance(duck_data, list) else duck_data.get("rows", [])
    ref_to_count: dict[str, int] = {}
    for row in duck_rows:
        if isinstance(row, dict):
            ref = row.get("business_ref", "")
            count = row.get("review_count", 0)
            if ref and isinstance(count, (int, float)):
                ref_to_count[ref] = int(count)

    if not ref_to_count:
        return raw_results

    # Extract categories from MongoDB descriptions, weighted by review_count
    cat_counts: dict[str, int] = defaultdict(int)
    mongo_rows = mongo_data if isinstance(mongo_data, list) else mongo_data.get("rows", [])
    for doc in mongo_rows:
        if not isinstance(doc, dict):
            continue
        bid = doc.get("business_id", "")
        bref = bid.replace("businessid_", "businessref_")
        count = ref_to_count.get(bref, 0)
        if count == 0:
            continue
        desc = doc.get("description", "")
        for cat in _extract_categories_from_description(desc):
            cat_counts[cat] += count

    if not cat_counts:
        return raw_results

    top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    enriched = dict(raw_results)
    enriched["category_aggregation"] = [
        {"category": k, "total_reviews": v} for k, v in top_cats
    ]
    return enriched


def _extract_refs_from_duck_result(duck_result) -> list[str]:
    """Extract business_ref values from a DuckDB result set (for duckdb_first joins)."""
    rows = duck_result if isinstance(duck_result, list) else duck_result.get("rows", [])
    refs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = row.get("business_ref") or row.get("ref") or row.get("business_ref_0")
        if ref and isinstance(ref, str) and ref.startswith("businessref_"):
            refs.append(ref)
    seen = set()
    return [r for r in refs if not (r in seen or seen.add(r))]


def _extract_business_refs(mongo_result) -> list[str]:
    """Convert MongoDB business_id values to DuckDB business_ref format.

    Handles both:
    - business_id: "businessid_N"  (single string, from $project or $first)
    - business_ids: ["businessid_N", ...]  (array, from $push — captures all IDs in a group)
    """
    docs = mongo_result if isinstance(mongo_result, list) else mongo_result.get("rows", [])
    refs = []
    for doc in docs:
        # Handle array of business_ids ($push case)
        bids = doc.get("business_ids", [])
        if isinstance(bids, list):
            for bid in bids:
                if isinstance(bid, str) and bid.startswith("businessid_"):
                    n = bid.split("businessid_", 1)[1]
                    refs.append(f"businessref_{n}")
        # Handle single business_id ($first or $project case)
        bid = doc.get("business_id", "")
        if isinstance(bid, str) and bid.startswith("businessid_"):
            n = bid.split("businessid_", 1)[1]
            refs.append(f"businessref_{n}")
    # Deduplicate while preserving order
    seen = set()
    return [r for r in refs if not (r in seen or seen.add(r))]


# ── State aggregation helpers ──────────────────────────────────────────────────

def _is_state_aggregation_question(q_lower: str) -> bool:
    """True when the question asks which state has the most of something."""
    return "state" in q_lower and ("highest" in q_lower or "most" in q_lower)


def _is_user_category_question(q_lower: str) -> bool:
    """True when question asks about categories reviewed by users filtered by registration/activity.
    These require DuckDB first (user/review tables) then MongoDB category lookup."""
    has_user_filter = "registered" in q_lower or "yelping since" in q_lower or "joined" in q_lower
    return "categor" in q_lower and has_user_filter


def _needs_review_count_for_state(q_lower: str) -> bool:
    """True when ranking states by review count (not by business count)."""
    return "review" in q_lower and _is_state_aggregation_question(q_lower)


def _extract_state_from_description(desc: str) -> str:
    """Extract 2-letter US state code from a business description.

    Handles both address formats found in the dataset:
      '...in City, XX, ...'   →  standard address with trailing comma
      '...City, XX location...' →  Uber-style without trailing comma
    """
    m = re.search(r',\s*([A-Z]{2})(?:,| )', desc)
    return m.group(1) if m else ""


def _group_refs_by_state(mongo_result) -> dict[str, list[str]]:
    """Build {state_code: [businessref_N, ...]} from MongoDB result docs."""
    docs = mongo_result if isinstance(mongo_result, list) else mongo_result.get("rows", [])
    state_to_refs: dict[str, list[str]] = defaultdict(list)
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        bid = doc.get("business_id", "")
        if not bid.startswith("businessid_"):
            continue
        bref = bid.replace("businessid_", "businessref_")
        state = _extract_state_from_description(doc.get("description", ""))
        if state:
            state_to_refs[state].append(bref)
    return dict(state_to_refs)


_NONEXISTENT_MONGO_FIELDS = {"state", "city", "zip", "zipcode", "address", "country"}


def _strip_state_grouping(mongo_sq: "SubQuery") -> "SubQuery":
    """Remove unreliable pipeline stages used to aggregate by state.

    Always strips: $addFields, $group, $sort, $limit, $project (replaced with plain $project).
    Also strips: $match stages that filter on fields that don't exist in the MongoDB schema
    (e.g. 'state', 'city') — these silently return zero results.
    """
    try:
        pipeline = json.loads(mongo_sq.query)
    except (json.JSONDecodeError, TypeError):
        return mongo_sq

    def _is_phantom_match(stage: dict) -> bool:
        """True if $match filters on a field that doesn't exist in MongoDB business docs."""
        match_doc = stage.get("$match", {})
        return bool(set(match_doc.keys()) & _NONEXISTENT_MONGO_FIELDS)

    has_addfields = any("$addFields" in stage for stage in pipeline)
    has_group = any("$group" in stage for stage in pipeline)
    has_phantom = any("$match" in stage and _is_phantom_match(stage) for stage in pipeline)
    if not (has_addfields or has_group or has_phantom):
        return mongo_sq  # nothing to strip

    new_pipeline = []
    for stage in pipeline:
        if "$collection" in stage:
            new_pipeline.append(stage)
        elif "$match" in stage and not _is_phantom_match(stage):
            new_pipeline.append(stage)
        # Drop $addFields, $group, $sort, $limit, $project, and phantom $match — replaced below
    new_pipeline.append({"$project": {"business_id": 1, "description": 1}})

    from agent.models import SubQuery as _SubQuery
    return _SubQuery(
        database_type="mongodb",
        query=json.dumps(new_pipeline),
        intent=mongo_sq.intent,
    )


def _compute_top_state_by_reviews(
    state_to_refs: dict[str, list[str]],
    duck_count_result,
) -> tuple[str, list[str], int, float]:
    """Given a state→refs map and DuckDB per-business review counts,
    find the state with the most total reviews and its weighted avg rating.

    Returns: (top_state, refs_for_top_state, total_review_count, weighted_avg_rating)
    """
    rows = (
        duck_count_result
        if isinstance(duck_count_result, list)
        else duck_count_result.get("rows", [])
    )
    # Build ref → (count, avg) from DuckDB result
    ref_stats: dict[str, tuple[int, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = row.get("business_ref", "")
        cnt = row.get("review_count", 0)
        avg = row.get("avg_rating", 0.0)
        if ref and cnt:
            ref_stats[ref] = (int(cnt), float(avg))

    # Sum reviews by state
    state_review_count: dict[str, int] = {}
    for state, refs in state_to_refs.items():
        state_review_count[state] = sum(ref_stats.get(r, (0, 0))[0] for r in refs)

    if not state_review_count:
        return "", [], 0, 0.0

    top_state = max(state_review_count, key=lambda s: state_review_count[s])
    top_refs = state_to_refs[top_state]
    total_cnt = state_review_count[top_state]

    # Weighted average rating across all businesses in the top state
    weight_sum = sum(
        ref_stats[r][0] * ref_stats[r][1] for r in top_refs if r in ref_stats
    )
    total_weight = sum(ref_stats[r][0] for r in top_refs if r in ref_stats)
    avg_rating = weight_sum / total_weight if total_weight else 0.0

    return top_state, top_refs, total_cnt, avg_rating



def _extract_pg_ids(pg_result) -> list[str]:
    """Extract the numeric suffix from PostgreSQL book_id values for SQLite join.
    Returns list of integer strings e.g. ['1', '5', '42'] from 'bookid_1', 'bookid_5', etc.
    """
    rows = pg_result if isinstance(pg_result, list) else pg_result.get("rows", [])
    ids = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        book_id = row.get("book_id", "")
        if isinstance(book_id, str) and book_id.startswith("bookid_"):
            n = book_id.split("bookid_", 1)[1]
            if n not in seen:
                seen.add(n)
                ids.append(n)
    return ids


def _merge_pg_sqlite_results(pg_result, sqlite_result) -> list[dict]:
    """Join PostgreSQL book metadata with SQLite per-book rating metrics.

    Matches bookid_N (PostgreSQL books_info.book_id) with purchaseid_N
    (SQLite review.purchase_id) via the shared integer suffix N.

    Returns combined rows: [{book_id, title, ..., avg_rating}, ...] for
    books that appear in BOTH result sets (inner join — SQLite already filtered
    by rating/date thresholds, so only qualifying books are present).
    """
    pg_rows = pg_result if isinstance(pg_result, list) else pg_result.get("rows", [])
    sql_rows = sqlite_result if isinstance(sqlite_result, list) else sqlite_result.get("rows", [])

    # Build PostgreSQL lookup by integer N
    pg_by_n: dict[str, dict] = {}
    for row in pg_rows:
        if not isinstance(row, dict):
            continue
        book_id = row.get("book_id", "")
        if isinstance(book_id, str) and book_id.startswith("bookid_"):
            n = book_id.split("bookid_", 1)[1]
            pg_by_n[n] = row

    if not pg_by_n:
        return []

    # Build SQLite lookup by integer N
    sql_by_n: dict[str, dict] = {}
    for row in sql_rows:
        if not isinstance(row, dict):
            continue
        purchase_id = row.get("purchase_id", "")
        if isinstance(purchase_id, str) and purchase_id.startswith("purchaseid_"):
            n = purchase_id.split("purchaseid_", 1)[1]
            sql_by_n[n] = row

    if not sql_by_n:
        return []

    # Inner join: keep books that appear in SQLite result (passed rating/date filter)
    merged = []
    for n, sql_row in sql_by_n.items():
        if n in pg_by_n:
            combined = {
                **pg_by_n[n],
                **{k: v for k, v in sql_row.items() if k != "purchase_id"},
            }
            merged.append(combined)
    return merged

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
        return json.loads(_strip_markdown(text))

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
                sub_queries.append(SubQuery(
                    database_type=db_type,
                    query='[{"$collection": "business"}, {"$project": {"business_id": 1, "name": 1, "description": 1}}]',
                    intent=intent.get("intent_summary", question),
                ))
            else:
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

        join_direction = intent.get("join_direction", "mongodb_first")

        if mongo_sq and duck_sq and join_direction == "duckdb_first":
            # DuckDB-first join: run DuckDB first to find top business_refs,
            # then look up MongoDB for names/categories.
            # If the question asks about categories, remove any LIMIT from the DuckDB query
            # so we get ALL business_refs (category aggregation needs all, not just top N).
            if "categor" in request.question.lower():
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
            # For category questions, force MongoDB to return individual docs (no $group)
            if "categor" in request.question.lower():
                mongo_sq = _strip_category_grouping(mongo_sq)
            mongo_result, mongo_corr = self._execute_with_retry(mongo_sq, request.question)
            raw_results["mongodb"] = mongo_result
            self_corrections.extend(mongo_corr)

            # For category-ranking questions, use Python extraction instead of MongoDB grouping
            if "categor" in request.question.lower():
                cat_refs, top_cat_name, top_cat_count = _compute_top_category_refs(mongo_result)
                if cat_refs:
                    business_refs = cat_refs
                    # Add top category info to mongo_result for synthesizer context
                    if isinstance(mongo_result, list):
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
            else:
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
        enriched = _augment_with_category_aggregation(raw_results)
        prompt = self.prompts.synthesize_response(question, enriched, {})
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


def _strip_category_grouping(mongo_sq: "SubQuery") -> "SubQuery":
    """If the MongoDB pipeline groups by categories (unreliable), replace with a simple
    filter+project so Python can do category extraction and aggregation."""
    try:
        pipeline = json.loads(mongo_sq.query)
    except (json.JSONDecodeError, TypeError):
        return mongo_sq

    # Check if pipeline has $group (category aggregation done in MongoDB)
    has_group = any("$group" in stage for stage in pipeline)
    has_unwind = any("$unwind" in stage for stage in pipeline)
    if not (has_group and has_unwind):
        return mongo_sq  # No category grouping, keep as is

    # Extract just the $collection and $match stages, add a simple $project
    new_pipeline = []
    for stage in pipeline:
        if "$collection" in stage:
            new_pipeline.append(stage)
        elif "$match" in stage:
            new_pipeline.append(stage)
        elif "$addFields" in stage or "$group" in stage or "$unwind" in stage or "$sort" in stage or "$limit" in stage or "$project" in stage:
            pass  # Skip category grouping stages
    new_pipeline.append({"$project": {"business_id": 1, "description": 1}})

    from agent.models import SubQuery
    return SubQuery(database_type="mongodb", query=json.dumps(new_pipeline), intent=mongo_sq.intent)


def _compute_top_category_refs(mongo_result) -> tuple[list[str], str, int]:
    """From a list of business docs with descriptions, find the top category by business count.
    Returns: (refs_for_top_category, top_category_name, business_count)"""
    docs = mongo_result if isinstance(mongo_result, list) else mongo_result.get("rows", [])
    cat_to_refs: dict[str, list[str]] = defaultdict(list)
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        bid = doc.get("business_id", "")
        if not bid.startswith("businessid_"):
            continue
        bref = bid.replace("businessid_", "businessref_")
        desc = doc.get("description", "")
        cats = _extract_categories_from_description(desc)
        for cat in cats:
            cat_to_refs[cat].append(bref)

    if not cat_to_refs:
        return [], "", 0

    # Find category with most businesses
    top_cat = max(cat_to_refs, key=lambda c: len(cat_to_refs[c]))
    return cat_to_refs[top_cat], top_cat, len(cat_to_refs[top_cat])


def _remove_limit_clause(sql: str) -> str:
    """Remove LIMIT N clause from a SQL query (used when we need all rows, not top N)."""
    return re.sub(r'\s+LIMIT\s+\d+\s*;?\s*$', '', sql, flags=re.IGNORECASE).strip()


def _extract_categories_from_description(desc: str) -> list[str]:
    """Extract comma-separated category list from a MongoDB business description."""
    for pattern in _CAT_EXTRACT_PATTERNS:
        m = re.search(pattern, desc, re.IGNORECASE)
        if m:
            cat_text = m.group(1)
            # Split on commas; strip leading "and " and trailing " and"
            raw_cats = re.split(r',\s*', cat_text)
            cats = []
            for c in raw_cats:
                c = c.strip()
                c = re.sub(r'^\s*and\s+', '', c)    # strip leading "and "
                c = re.sub(r'\s+and\s*$', '', c)    # strip trailing " and"
                c = c.strip().title()               # normalize to Title Case
                if c:
                    cats.append(c)
            # Only keep short category-like strings (no location words, verbs, or articles)
            filtered = [c for c in cats if c and 2 <= len(c) <= 40
                        and not re.search(r'\b(Offering|Array|Delightful|Perfect|Cozy|Wide|Range|Diverse|Menu|Cuisine|Atmosphere|Options|Experience|Selection|Establishment|Facility|Located|Services|Along|Lively|Vibrant|Great|Broad)\b', c)
                        and not re.match(r'^[A-Z]{2}$', c)  # skip 2-letter state codes
                        and not re.search(r'\b(St\.|Dr\.|Ave|Blvd|Rd|Hwy)\b', c)
                        and not re.search(r'\d', c)]  # skip strings with numbers (addresses)
            if filtered:
                return filtered
    return []


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



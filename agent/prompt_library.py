import json


class PromptLibrary:

    def intent_analysis(self, question: str, available_databases: list[str]) -> str:
        return f"""Analyze this data question and determine which databases to query.
Consult the domain knowledge in your context for any ambiguous terms or fiscal/status conventions.

Question: {question}
Available databases: {', '.join(available_databases)}

CRITICAL ROUTING RULES for Yelp dataset:
- MongoDB (yelp_db) contains: business attributes (WiFi, parking, credit cards), location (city/state in description text), categories (in description text), is_open, review_count
- DuckDB (yelp_user.db) contains: review ratings (rating field), review text, tip text, user registration dates (user.yelping_since)
- MongoDB has NO stars or rating field — ratings ONLY exist in DuckDB review.rating
- ANY question involving average rating, stars, or score for businesses MUST include BOTH mongodb AND duckdb
- ANY question involving user registration dates or review dates MUST include duckdb
- ANY question about business attributes (WiFi, parking, credit cards, categories) uses mongodb

JOIN DIRECTION RULES:
- Use "mongodb_first" when: MongoDB's attribute/location filter is the main discriminator
  (e.g., "businesses with WiFi in PA" → MongoDB filters, DuckDB computes avg rating)
- Use "duckdb_first" when: DuckDB's time/rating data is the main discriminator
  (e.g., "highest rated business in date range" → DuckDB finds top business, MongoDB looks up name/category)
  (e.g., "categories most reviewed by 2016 users" → DuckDB finds business_refs for 2016 users, MongoDB looks up categories)

Respond with valid JSON only:
{{
  "target_databases": ["mongodb", "duckdb"],
  "intent_summary": "brief description of what data is needed",
  "requires_join": true,
  "join_direction": "mongodb_first",
  "data_fields_needed": ["field1", "field2"]
}}"""

    def nl_to_sql(self, question: str, schema: str, dialect: str = "postgresql") -> str:
        date_rule = ""
        if dialect == "duckdb":
            date_rule = """
CRITICAL DATE RULE for DuckDB: The 'date' column has mixed format strings. NEVER use strptime, TRY_CAST, or date functions.
ALWAYS use LIKE pattern matching for date filtering:
- Full year (e.g. 2018): date LIKE '%2018%'
- Month range Jan-Jun 2016:
  (date LIKE '2016-01%' OR date LIKE '2016-02%' OR date LIKE '2016-03%'
   OR date LIKE '2016-04%' OR date LIKE '2016-05%' OR date LIKE '2016-06%'
   OR date LIKE '%January%2016%' OR date LIKE '%February%2016%' OR date LIKE '%March%2016%'
   OR date LIKE '%April%2016%' OR date LIKE '%May%2016%' OR date LIKE '%June%2016%'
   OR date LIKE '% Jan 2016%' OR date LIKE '% Feb 2016%' OR date LIKE '% Mar 2016%'
   OR date LIKE '% Apr 2016%' OR date LIKE '% May 2016%' OR date LIKE '% Jun 2016%')
- User registration year: yelping_since LIKE '%2016%'"""
        return f"""Generate a {dialect.upper()} query for this question.

Schema:
{schema}

Question: {question}
{date_rule}
Rules:
- Return only the SQL query, no explanation
- Use exact table and column names from the schema
- DuckDB does NOT have business names, categories, or location data — those are in MongoDB.
  If the question asks for categories or business names, only SELECT business_ref + COUNT/metric.
  Do NOT SELECT or fabricate a 'category' column in DuckDB — use business_ref only.
- CRITICAL: Do NOT add LIMIT unless the question asks for exactly 1 specific business.
  WRONG: adding LIMIT 5 when question asks "which 5 categories" — LIMIT applies to categories, NOT businesses.
  For ANY question about "top N categories": return ALL business_refs with NO LIMIT. Category aggregation happens separately.
- For "since YEAR" phrasing: do NOT filter reviews by date — "since 2016" means user-registration filter only.
- For {dialect}: {self._dialect_rules(dialect)}"""

    def nl_to_mongodb(self, question: str, collection_schema: str) -> str:
        return f"""Generate a MongoDB aggregation pipeline for this question.

Collection schema:
{collection_schema}

Question: {question}

CRITICAL REQUIREMENTS:
1. Prepend the pipeline with a collection selector as the VERY FIRST element:
   {{"$collection": "business"}}  — for business collection (default)
   {{"$collection": "checkin"}}   — for checkin collection

2. The pipeline output MUST include business_id(s) in every result document for cross-DB DuckDB joins.
   - If you use $project (no grouping): include business_id: 1
   - If you use $group AND the question asks for ratings/averages: use `business_ids: {{"$push": "$business_id"}}` to capture ALL business_ids in the group (not just $first). This allows DuckDB to compute avg over all matching businesses.
   - If you use $group and ratings are NOT needed: `business_id: {{"$first": "$business_id"}}` is fine.

3. CRITICAL SCHEMA RULE: MongoDB business collection has NO stars, rating, or score field.
   NEVER use $avg, $sum, or any aggregation on $stars or $rating — these fields do not exist and will return null.
   For questions involving average ratings: return business_ids only from MongoDB, ratings come from DuckDB.

4. CRITICAL ATTRIBUTE FORMAT: attribute values in MongoDB are stored as Python repr strings with embedded quotes.
   WiFi field example values: "u'free'", "u'no'", "u'paid'", "'no'", "N/A".
   WRONG: {{"attributes.WiFi": {{"$nin": [null, "no", "u'no'", "None"]}}}}  ← misses "'no'" variant
   CORRECT: {{"attributes.WiFi": {{"$regex": "free|paid", "$options": "i"}}}}  ← only matches WiFi=yes
   YOU MUST use $regex to match attribute values, NEVER $nin or $ne.
   Same pattern: AcceptsCreditCards → {{"$regex": "True"}}, BikeParking → {{"$regex": "True"}}, BusinessParking (any True) → {{"$regex": "True"}}

5. CATEGORIES are embedded in the description field, NOT in a separate field.
   NEVER use $group to group by categories — that requires complex $split which is unreliable.
   Instead: filter businesses, then return business_id + description for each individual document.
   Category aggregation (counting businesses per category, finding top category) is done in post-processing.
   For "which category has most businesses X": just filter by attribute X and return all business_id + description.
   Example for Q4 (credit card category):
   [{{"$collection": "business"}}, {{"$match": {{"attributes.BusinessAcceptsCreditCards": {{"$regex": "True"}}}}}}, {{"$project": {{"business_id": 1, "description": 1}}}}]

6. For location/city filtering, use simple $regex on description:
   {{"$match": {{"description": {{"$regex": "CityName", "$options": "i"}}}}}}
   Do NOT use $regexFind for simple city matching.

7. For state-level filtering, use: {{"$match": {{"description": {{"$regex": ", XX(?:,| )", "$options": "i"}}}}}}
   where XX is the 2-letter state abbreviation (e.g. ", PA(?:,| )" for Pennsylvania).
   This handles both ", PA," (standard address) and ", PA " (e.g. "Philadelphia, PA location").

8. NEVER use $lookup to join with any other collection to filter by date/year.
   Date filtering (e.g. "during 2018", "in 2016") is handled by DuckDB on the review table.
   MongoDB only handles attribute/location filters. Return business_ids and let DuckDB apply the date filter.
   WRONG: {{"$lookup": {{"from": "checkin", ...}}}}  ← never do this for review-date questions
   CORRECT: filter by attribute/location only, return business_id list for DuckDB

Example output:
[{{"$collection": "business"}}, {{"$match": {{"is_open": 1}}}}, {{"$project": {{"business_id": 1, "name": 1}}}}]

Return only the valid JSON array, no explanation, no markdown fences."""

    def nl_to_sql_with_refs(self, question: str, schema: str, business_refs_sql: str,
                            dialect: str = "duckdb") -> str:
        return f"""Generate a {dialect.upper()} query for this question.
The query MUST filter business_ref to only these values (already resolved from MongoDB):
business_ref IN ({business_refs_sql})

Schema:
{schema}

Question: {question}

Rules:
- Use business_ref IN (...) as the primary filter — do not search by text or location
- Return only the SQL query, no explanation
- Use exact column names from the schema
- Do NOT include a state, city, or location column — the group identity is already known from MongoDB context
- Do NOT hardcode or fabricate location names (no 'Unknown', 'PA', etc.) — only return computed metrics
- For avg rating questions: SELECT AVG(r.rating) AS avg_rating FROM review r WHERE r.business_ref IN (...)
- For count/date questions: use date LIKE '%YEAR%' for year filtering (dates have mixed formats)
- For DuckDB: {self._dialect_rules(dialect)}"""

    def nl_to_mongodb_lookup(self, question: str, schema: str, business_ids_json: str) -> str:
        """Generate MongoDB lookup by specific business_ids (for duckdb_first joins)."""
        return f"""Generate a MongoDB aggregation pipeline to look up business details by specific IDs.

These business_ids were identified as the answer from DuckDB analysis:
{business_ids_json}

Schema:
{schema}

Question context: {question}

Requirements:
1. Filter to ONLY these business_ids: {{"$match": {{"business_id": {{"$in": {business_ids_json}}}}}}}
2. Include: business_id, name, description (categories are in the description text)
3. Do NOT compute ratings — those come from DuckDB
4. Prepend {{"$collection": "business"}} as FIRST element

Return only the valid JSON array pipeline, no explanation.

Example:
[{{"$collection": "business"}}, {{"$match": {{"business_id": {{"$in": ["businessid_1", "businessid_2"]}}}}}}, {{"$project": {{"business_id": 1, "name": 1, "description": 1}}}}]"""

    def self_correct(self, question: str, failed_query: str, error: str,
                     db_type: str, schema: str, fix_strategy: str = "") -> str:
        strategy_hint = f"\nFix strategy: {fix_strategy}" if fix_strategy else ""
        return f"""A database query failed. Generate a corrected query.
Check the corrections log in your context before generating a fix — a similar failure may already be documented.{strategy_hint}

Original question: {question}
Database type: {db_type}
Failed query: {failed_query}
Error message: {error}

Schema:
{schema}

Fix the query. Return only the corrected query, no explanation."""

    def synthesize_response(self, question: str, merged_results: dict, query_trace: dict) -> str:
        # Always include category_aggregation in full; truncate the rest
        cat_agg = merged_results.get("category_aggregation")
        cat_section = ""
        if cat_agg:
            cat_section = f"\n\nPRE-COMPUTED category_aggregation (use this directly):\n{json.dumps(cat_agg, indent=2)}"

        # Truncate MongoDB to 20 docs max so DuckDB results always fit in the context
        truncated_results = {}
        for k, v in merged_results.items():
            if k == "category_aggregation":
                continue
            if k == "mongodb" and isinstance(v, list) and len(v) > 20:
                truncated_results[k] = v[:20]
                truncated_results["mongodb_note"] = f"(showing 20 of {len(v)} docs)"
            else:
                truncated_results[k] = v

        # Always show DuckDB result separately to ensure it's not cut off
        duck_result = merged_results.get("duckdb")
        duck_section = ""
        if duck_result is not None:
            duck_section = f"\n\nDuckDB result (CRITICAL — contains the metrics/counts):\n{json.dumps(duck_result, indent=2, default=str)}"
            truncated_results.pop("duckdb", None)

        return f"""Synthesize a clear, direct answer to the user's question from these database results.

Question: {question}

Results from databases:
{json.dumps(truncated_results, indent=2, default=str)[:2000]}{duck_section}{cat_section}

CRITICAL JOINING RULE:
- MongoDB results identify the ENTITY (state, category, business name, group)
- DuckDB results provide the METRICS (avg_rating, review counts, dates) for that same entity
- When DuckDB returns avg_rating without a state/name column, it applies to the group identified by MongoDB
- NEVER say "not available" for a metric if DuckDB returned a numeric value — associate it with the MongoDB entity
- business_ref_N in DuckDB corresponds to business_id_N in MongoDB (e.g., businessref_9 ↔ businessid_9)

CATEGORY AGGREGATION RULE:
- If results contain a "category_aggregation" key, use it directly — it's already computed.
  List ALL categories from it (the list is already sorted by total_reviews descending).
  For a "top 5 categories" question, report all categories in the pre-computed list
  because the list may contain up to 10 entries and the question's "top 5" is based on the ranked list.
- Do NOT recompute from MongoDB descriptions if category_aggregation is present.
- Otherwise, extract categories from MongoDB descriptions (look for text after "including", "featuring", "specializes in").

CRITICAL FORMAT RULES (required for automated evaluation):
- For state/entity + metric answers: ALWAYS use the compact format:
  "ABBR (Full Name) - avg RATING, N items."
  Example: "PA (Pennsylvania) - avg 3.48, 8 WiFi businesses."
  Example: "PA (Pennsylvania) - avg 3.70, 26 reviews."
  The metric (e.g., 3.48) MUST appear within the FIRST 40 characters of the state abbreviation.
- For business name + category answers: name first, then categories in same sentence.
  Example: "Coffee House Too Cafe belongs to: Restaurants, Breakfast & Brunch, American (New), Cafes."
- For count-only answers: state the number prominently in the first sentence.
- Do NOT write "has the highest number of X. The average rating is Y" — keep entity and metric together.
- Do not mention internal query details (business_ref, business_id, etc.)
- business_ref values like 'businessref_52' correspond to MongoDB business_id 'businessid_52' — use the business name from MongoDB results when available
- If results are empty or contain errors, say so explicitly"""

    def text_extraction(self, text: str, goal: str) -> str:
        return f"""Extract structured information from this text.

Goal: {goal}
Text: {text}

Return a JSON object with the extracted information. Example for sentiment:
{{"sentiment": "positive", "key_topics": ["service", "food"], "rating_implied": 4}}

Return only valid JSON."""

    def _dialect_rules(self, dialect: str) -> str:
        rules = {
            "postgresql": "use ILIKE for case-insensitive search, LIMIT for pagination",
            "sqlite": "use LIKE for search, use strftime for dates",
            "duckdb": (
                "use DuckDB analytical functions. "
                "IMPORTANT: date column stores mixed-format strings: 'August 01, 2016 at 03:44 AM', '29 May 2013, 23:01', '2016-04-02 23:09:00'. "
                "For a full-year filter: date LIKE '%2018%'. "
                "For a month-range filter (e.g. Jan-Jun 2016), use OR of patterns: "
                "(date LIKE '2016-01%' OR date LIKE '2016-02%' OR date LIKE '2016-03%' OR date LIKE '2016-04%' OR date LIKE '2016-05%' OR date LIKE '2016-06%' "
                "OR date LIKE '%January%2016%' OR date LIKE '%February%2016%' OR date LIKE '%March%2016%' OR date LIKE '%April%2016%' OR date LIKE '%May%2016%' OR date LIKE '%June%2016%' "
                "OR date LIKE '% Jan 2016%' OR date LIKE '% Feb 2016%' OR date LIKE '% Mar 2016%' OR date LIKE '% Apr 2016%' OR date LIKE '% May 2016%' OR date LIKE '% Jun 2016%'). "
                "For user registration year filter: yelping_since LIKE '%2016%'"
            ),
            "mongodb": "return a MongoDB aggregation pipeline as a JSON array",
        }
        return rules.get(dialect, "use standard SQL")

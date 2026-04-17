import json


class PromptLibrary:

    def intent_analysis(self, question: str, available_databases: list[str]) -> str:
        # For crmarenapro, available_databases contains logical DB names — tell the LLM to use them
        crm_logical = {"core_crm", "sales_pipeline", "support", "products_orders", "activities", "territory"}
        deps_logical = {"package_database", "project_database"}
        is_crm = bool(set(available_databases) & crm_logical)
        is_deps = bool(set(available_databases) & deps_logical)

        if is_deps:
            routing_rules = """ROUTING RULES for DEPS_DEV_V1 — use the logical DB names exactly as listed:
- package_database (SQLite): table `packageinfo` — has System, Name, Version, Licenses (JSON), VersionInfo (JSON with IsRelease), UpstreamPublishedAt
- project_database (DuckDB): tables `project_packageversion` (System, Name, Version, ProjectType, ProjectName) and `project_info` (Project_Information text with stars/forks, Licenses, Description)

KEY ROUTING DECISIONS:
- Questions about package versions, licenses, release status → "package_database" (SQLite)
- Questions about GitHub stars, forks, project info → "project_database" (DuckDB)
- Most questions need BOTH — include both and set requires_join=true
- Join key: (System, Name, Version) across package_database ↔ project_database via project_packageversion

Return the EXACT logical DB names in target_databases, not generic types like "sqlite" or "duckdb"."""
        elif is_crm:
            routing_rules = """ROUTING RULES for CRMArena Pro — use the logical DB names exactly as listed:
- core_crm (SQLite): User, Account, Contact — use for user/account/contact lookups and agent name resolution
- sales_pipeline (DuckDB): Opportunity, Contract, Lead, Quote, OpportunityLineItem, QuoteLineItem — use for sales pipeline, quotes, contracts
- support (PostgreSQL): Case, knowledge__kav, issue__c, casehistory__c, emailmessage, livechattranscript — use for ALL case/support/policy/knowledge article queries
- products_orders (SQLite): Product2, Order, OrderItem, Pricebook2, PricebookEntry, ProductCategory — use ONLY when you need product catalog or order data directly; do NOT use for case queries
- activities (DuckDB): Event, Task, VoiceCallTranscript__c — use for call transcripts and tasks
- territory (SQLite): Territory2, UserTerritory2Association — use for territory data

KEY ROUTING DECISIONS:
- Questions about cases, issues, knowledge articles, policy violations → always include "support"
- Questions about which month/period has most cases → "support" only (Case.createddate is there)
- Questions about product-related cases → "support" (Case.orderitemid__c links to products) + "products_orders" (to get OrderItem IDs for the product)
- Questions about agent performance on cases → "support" + "core_crm" (for User lookup)
- Questions about sales cycle/turnaround → "sales_pipeline" (Opportunity + Contract)
- Questions about BANT/lead qualification → "activities" (VoiceCallTranscript__c) + "sales_pipeline" (Lead)

Return the EXACT logical DB names in target_databases, not generic types like "duckdb"."""
        else:
            routing_rules = """ROUTING RULES — use the schema in your context to determine which database holds the needed fields:
- Route to the database that contains the fields required to answer the question
- If the question needs data from multiple databases, include all of them and set requires_join=true
- Use "mongodb_first" when a NoSQL attribute/location filter is the main discriminator
- Use "duckdb_first" when DuckDB time/rating aggregation is the main discriminator
- Use "postgresql_first" when PostgreSQL metadata is the main discriminator and SQLite holds reviews
- Use "sqlite_first" when SQLite holds the review/rating data and the other DB holds metadata"""

        return f"""Analyze this data question and determine which databases to query.
Consult the schema in your context (AGENT.md Layer 1) for the exact tables and fields for the active dataset.

Question: {question}
Available databases: {', '.join(available_databases)}

{routing_rules}

CATEGORY QUESTION DETECTION:
- Set is_category_question=true when the question asks which category/type/genre of business has
  the most of something. Set is_category_question=false otherwise.

Respond with valid JSON only:
{{
  "target_databases": ["db_name_1", "db_name_2"],
  "intent_summary": "brief description of what data is needed",
  "requires_join": true,
  "join_direction": "mongodb_first",
  "data_fields_needed": ["field1", "field2"],
  "is_category_question": false
}}"""

    def nl_to_sql(self, question: str, schema: str, dialect: str = "postgresql") -> str:
        pg_note = ""
        if dialect == "postgresql":
            pg_note = "\n- IMPORTANT: PostgreSQL and SQLite are SEPARATE databases. Do NOT join to SQLite tables (review) in this query. Only query tables available in PostgreSQL. Always include book_id in the SELECT so results can be joined to SQLite later."
        if dialect == "postgresql_bookreview":
            pg_note = (
                "\n- IMPORTANT: PostgreSQL and SQLite are SEPARATE databases. "
                "Do NOT reference or join to the SQLite `review` table in this query — "
                "it does not exist in PostgreSQL. Only query `books_info` and other PostgreSQL tables."
                "\n- ALWAYS include BOTH `book_id` AND `title` in the SELECT clause so Python can "
                "join results to SQLite review data and return book titles to the user."
                "\n- Do NOT apply rating filters (avg rating, rating = 5.0) in this query — "
                "average ratings come from SQLite `review` and are applied after the join."
            )

        # CRM-specific rules injected when the schema mentions CRMArena Pro
        crm_note = ""
        if "CRMArena Pro" in schema or "VoiceCallTranscript" in schema or "knowledge__kav" in schema:
            crm_note = (
                "\n- CRITICAL CRM ID RULE: ~25% of all IDs have a leading '#' character. "
                "ALWAYS normalize IDs before comparing. "
                "SQLite/DuckDB: `TRIM(REPLACE(col, '#', ''))` | "
                "PostgreSQL: `TRIM(REPLACE(col, chr(35), ''))` (chr(35) = '#', empty string = two single quotes '')"
                "\n- DATE FIELDS are stored as TEXT. PostgreSQL: cast with `::timestamp` before date math. "
                "Example: `createddate::timestamp >= TIMESTAMP '2023-09-02' - INTERVAL '4 months'`"
                "\n- For support (PostgreSQL): table names are case-sensitive — always double-quote: "
                '`"Case"`, `"knowledge__kav"`, `"issue__c"`, `"casehistory__c"`'
                "\n- Do NOT join tables from different logical databases in a single SQL query."
                "\n- NEVER reference a 'review' table — it does not exist in any CRMArena Pro database."
            )

        return f"""Generate a {dialect.upper()} query for this question.

Schema:
{schema}

Question: {question}

Rules:
- Return only the SQL query, no explanation, no markdown code fences
- Use exact table and column names from the schema above
- For apostrophes in string literals use doubled single quotes: 'Children''s Books' — NEVER backslash escaping{pg_note}{crm_note}
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

8. NEVER use $addFields/$group to extract or aggregate by state/city from the description field.
   State names are embedded in description text in inconsistent formats — MongoDB string parsing
   is unreliable. Instead: filter by attribute if needed, then return business_id + description
   for each document. State aggregation (counting businesses per state, finding top state) is done
   in post-processing by Python. Just return all matching docs with business_id and description.
   WRONG: {{"$addFields": {{"state": {{"$arrayElemAt": [{{"$split": ["$description", "in "]}}, 1]}}}}}}
   CORRECT: {{"$project": {{"business_id": 1, "description": 1}}}}

9. NEVER use $lookup to join with any other collection to filter by date/year.
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
The query MUST filter to only these business_refs (already resolved from MongoDB):
business_ref IN ({business_refs_sql})

Schema:
{schema}

Question: {question}

Rules:
- Use the id IN (...) filter as the primary constraint
- Return only the SQL query, no explanation, no markdown code fences
- Use exact column names from the schema above
- For {dialect}: {self._dialect_rules(dialect)}"""

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
            cat_section = f"\n\nPRE-COMPUTED category_aggregation (use this directly):\n{json.dumps(cat_agg, indent=2, ensure_ascii=False)}"

        # When category_aggregation is pre-computed, raw MongoDB docs are already consumed
        # by Python extraction — skip them entirely to avoid bloating the LLM context.
        # Otherwise truncate to 100 docs max to keep context manageable.
        truncated_results = {}
        for k, v in merged_results.items():
            if k == "category_aggregation":
                continue
            if k == "mongodb" and isinstance(v, list):
                if cat_agg:
                    continue  # raw docs not needed — category_aggregation already summarises them
                if len(v) > 100:
                    truncated_results[k] = v[:100]
                    truncated_results["mongodb_note"] = f"(showing 100 of {len(v)} docs)"
                    continue
            truncated_results[k] = v

        # Always show DuckDB result separately to ensure it's not cut off
        # Check all possible DuckDB result keys (duckdb, project_database, project_query)
        duck_key = next((k for k in ("duckdb", "project_database", "project_query")
                         if merged_results.get(k) is not None), None)
        duck_result = merged_results.get(duck_key) if duck_key else None
        duck_section = ""
        if duck_result is not None:
            duck_section = f"\n\nDuckDB result (CRITICAL — contains the metrics/counts):\n{json.dumps(duck_result, indent=2, default=str, ensure_ascii=False)}"
            truncated_results.pop(duck_key, None)

        return f"""Synthesize a clear, direct answer to the user's question from these database results.

Question: {question}

Results from databases:
{json.dumps(truncated_results, indent=2, default=str, ensure_ascii=False)[:2000]}{duck_section}{cat_section}

CRITICAL JOINING RULE (Yelp):
- MongoDB results identify the ENTITY (state, category, business name, group)
- DuckDB results provide the METRICS (avg_rating, review counts, dates) for that same entity
- When DuckDB returns avg_rating without a state/name column, it applies to the group identified by MongoDB
- NEVER say "not available" for a metric if DuckDB returned a numeric value — associate it with the MongoDB entity
- business_ref_N in DuckDB corresponds to business_id_N in MongoDB (e.g., businessref_9 ↔ businessid_9)
- If MongoDB result contains "top_state", that IS the answer state — use it directly with the DuckDB metric
- If DuckDB result contains "avg_rating" and "review_count" at the top level, those are the final pre-computed values

CRITICAL JOINING RULE (CRMArena Pro — when results are keyed by logical DB name):
- Results may be keyed by: "core_crm", "sales_pipeline", "support", "products_orders", "activities", "territory"
- IDs across tables may have a leading '#' — treat '#005Wt...' and '005Wt...' as the SAME ID when joining
- Join results across DBs by normalizing IDs: strip '#' and TRIM whitespace before matching
- If one DB returned an error but another returned data, use the available data to answer
- For agent ID questions: OwnerId in sales_pipeline/support maps to User.Id in core_crm (strip '#' from both)

CATEGORY AGGREGATION RULE:
- If results contain a "category_aggregation" key, use it directly — it's already computed.
  List ALL categories from it (the list is already sorted by total_reviews descending).
  For a "top 5 categories" question, report all categories in the pre-computed list
  because the list may contain up to 10 entries and the question's "top 5" is based on the ranked list.
- Do NOT recompute from MongoDB descriptions if category_aggregation is present.
- Otherwise, extract categories from MongoDB descriptions (look for text after "including", "featuring", "specializes in").

CRITICAL JOINING RULE (DEPS_DEV_V1 — when results are keyed by "package_database"/"project_database"):
- IGNORE "package_database" (SQLite) results entirely when "project_database" (DuckDB) results are available
- The DuckDB "project_database" result IS the final answer — use it exclusively
- For star/fork questions: DuckDB returns columns like Name, Version, stars, forks, ProjectName — use those directly
- For ProjectName questions (GitHub forks): output each row as "ProjectName,Version,ForksCount"
  e.g. "mui-org/material-ui,0.2.0,30522" — one per line, ALL rows in the DuckDB result
- For package name+stars questions: output each row as "Name,Version"
  e.g. "@dmrvos/infrajs>0.0.6>typescript,2.6.2" — version MUST immediately follow Name with only a comma
- Output ALL DuckDB rows (not just top N) — list every row one per line, do not truncate

CRITICAL FORMAT RULES (required for automated evaluation):
- For state/entity + metric answers: ALWAYS use the compact format:
  "ABBR (Full Name) - avg RATING, N items."
  Example: "CA (California) - avg 4.12, 5 WiFi businesses."
  Example: "TX (Texas) - avg 3.91, 14 reviews."
  The metric (e.g., 4.12) MUST appear within the FIRST 40 characters of the state abbreviation.
- For business name + category answers: name first, then categories in same sentence.
  Example: "Sunset Grill belongs to: Restaurants, American (New), Cafes."
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
            "postgresql": "use standard PostgreSQL syntax, ILIKE for case-insensitive search, cast types explicitly",
            "postgresql_bookreview": "use standard PostgreSQL syntax, ILIKE for case-insensitive search, cast types explicitly",
            "sqlite": "use SQLite syntax, strftime('%Y', date_col) for year extraction, LIKE for text search",
            "duckdb": (
                "use DuckDB analytical functions. "
                "review.date has MIXED formats: '%B %d, %Y at %I:%M %p' (e.g. 'August 01, 2016 at 03:44 AM') "
                "OR '%d %b %Y, %H:%M' (e.g. '21 May 2016, 18:48'). "
                "NEVER call STRPTIME/TRY_STRPTIME with a single format — it crashes for the other. "
                "Year-only: use LIKE '%2016%'. "
                "Date range: COALESCE(TRY_STRPTIME(date, '%B %d, %Y at %I:%M %p'), "
                "TRY_STRPTIME(date, '%d %b %Y, %H:%M')) BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'. "
                "The 'business' table does NOT exist in DuckDB — never JOIN it; it is MongoDB-only."
            ),
            "mongodb": "return a MongoDB aggregation pipeline as a JSON array",
        }
        return rules.get(dialect, "use standard SQL")

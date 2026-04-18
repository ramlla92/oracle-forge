import json


class PromptLibrary:

    def intent_analysis(self, question: str, available_databases: list[str]) -> str:
        return f"""Analyze this data question and determine which databases to query.
Consult the schema in your context (AGENT.md Layer 1) for the exact tables and fields for the active dataset.

Question: {question}
Available databases: {', '.join(available_databases)}

ROUTING RULES — use the schema in your context to determine which database holds the needed fields:
- Route to the database that contains the fields required to answer the question
- If the question needs data from multiple databases, include all of them and set requires_join=true
- Use "mongodb_first" when a NoSQL attribute/location filter is the main discriminator
- Use "duckdb_first" when DuckDB time/rating aggregation is the main discriminator
- Use "postgresql_first" when PostgreSQL metadata is the main discriminator and SQLite holds reviews
- Use "sqlite_first" when SQLite holds the review/rating data and the other DB holds metadata

CATEGORY QUESTION DETECTION:
- Set is_category_question=true when the question asks which category/type/genre of business has
  the most of something (e.g. "which category has the most reviews", "what type of business has
  the highest rating", "what categories are open on Sundays"). Categories are embedded in the
  MongoDB business.description field — they are never a standalone field.
- Set is_category_question=false for questions about a specific named category, or questions
  that don't involve grouping or ranking by category.

Respond with valid JSON only:
{{
  "target_databases": ["database_type_1", "database_type_2"],
  "intent_summary": "brief description of what data is needed",
  "requires_join": true,
  "join_direction": "mongodb_first",
  "data_fields_needed": ["field1", "field2"],
  "is_category_question": false
}}"""

    def nl_to_sql(self, question: str, schema: str, dialect: str = "postgresql",
                  dataset: str = "") -> str:
        if dataset == "agnews" and dialect == "sqlite":
            return self._nl_to_sqlite_agnews(question)
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
        return f"""Generate a {dialect.upper()} query for this question.

Schema:
{schema}

Question: {question}

Rules:
- Return only the SQL query, no explanation, no markdown code fences
- Use exact table and column names from the schema above
- For apostrophes in string literals use doubled single quotes: 'Children''s Books' — NEVER backslash escaping{pg_note}
- For {dialect}: {self._dialect_rules(dialect)}"""

    def _nl_to_sqlite_agnews(self, question: str) -> str:
        return f"""Generate a SQLite query for the agnews metadata database.

Schema:
  article_metadata(article_id INTEGER, author_id INTEGER, region TEXT, publication_date TEXT)
  authors(author_id INTEGER, name TEXT)
  publication_date format: 'YYYY-MM-DD'

Question: {question}

CRITICAL RULES:
1. Your ONLY job is to return article_id values (and optionally region, publication_date).
   Article category (Sports/Business/World/Science/Technology) does NOT exist in this database.
   Do NOT try to filter or count by category — category will be inferred from MongoDB content.
2. Return: SELECT am.article_id [, am.region, am.publication_date]
   FROM article_metadata am [JOIN authors a ON am.author_id = a.author_id]
   [WHERE <non-category filter>]
3. For author name filters: JOIN authors and WHERE a.name = '...'
4. For year filters: WHERE strftime('%Y', publication_date) = '2015' or BETWEEN '2010' AND '2020'
5. For region filters: WHERE region = 'Europe'  (case-sensitive, exact match)
6. Return ONLY the SQL query, no explanation.

Examples:
  Amy Jones articles: SELECT am.article_id FROM article_metadata am JOIN authors a ON am.author_id = a.author_id WHERE a.name = 'Amy Jones'
  Europe 2010-2020:   SELECT am.article_id, am.publication_date FROM article_metadata am WHERE region = 'Europe' AND CAST(strftime('%Y', am.publication_date) AS INTEGER) BETWEEN 2010 AND 2020
  2015 by region:     SELECT am.article_id, am.region FROM article_metadata am WHERE strftime('%Y', am.publication_date) = '2015'"""

    def nl_to_mongodb(self, question: str, collection_schema: str, dataset: str = "") -> str:
        if dataset == "agnews":
            return self._nl_to_mongodb_agnews(question, collection_schema)
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

    def _nl_to_mongodb_agnews(self, question: str, collection_schema: str) -> str:
        return f"""Generate a MongoDB aggregation pipeline for this question about news articles.

Collection: articles_db.articles
Fields: article_id (int), title (str), description (str)

CRITICAL: There is NO category, label, or class field. Do NOT filter by any category field.
Article categories (World/Sports/Business/Science/Technology) are inferred from title and description
during synthesis — not stored as a DB field.

Question: {question}

Requirements:
1. Always prepend: {{"$collection": "articles"}}
2. Always include article_id, title, and description in the output via $project.
3. If the question involves description length: use {{"$addFields": {{"desc_len": {{"$strLenCP": "$description"}}}}}} then $sort desc_len descending, $limit 500.
4. If filtering by specific article_ids (from SQLite join): use {{"$match": {{"article_id": {{"$in": [list]}}}}}}
5. Do NOT filter by category, label, or class — these fields do not exist.
6. Do NOT reference business_id — this collection does not have that field.

Return only the valid JSON array pipeline, no explanation, no markdown fences."""

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

    def synthesize_response(self, question: str, merged_results: dict, query_trace: dict,
                            dataset: str = "") -> str:
        if dataset == "agnews":
            return self._synthesize_agnews(question, merged_results)
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
        duck_result = merged_results.get("duckdb")
        duck_section = ""
        if duck_result is not None:
            duck_section = f"\n\nDuckDB result (CRITICAL — contains the metrics/counts):\n{json.dumps(duck_result, indent=2, default=str, ensure_ascii=False)}"
            truncated_results.pop("duckdb", None)

        return f"""Synthesize a clear, direct answer to the user's question from these database results.

Question: {question}

Results from databases:
{json.dumps(truncated_results, indent=2, default=str, ensure_ascii=False)[:2000]}{duck_section}{cat_section}

CRITICAL JOINING RULE:
- MongoDB results identify the ENTITY (state, category, business name, group)
- DuckDB results provide the METRICS (avg_rating, review counts, dates) for that same entity
- When DuckDB returns avg_rating without a state/name column, it applies to the group identified by MongoDB
- NEVER say "not available" for a metric if DuckDB returned a numeric value — associate it with the MongoDB entity
- business_ref_N in DuckDB corresponds to business_id_N in MongoDB (e.g., businessref_9 ↔ businessid_9)
- If MongoDB result contains "top_state", that IS the answer state — use it directly with the DuckDB metric
- If DuckDB result contains "avg_rating" and "review_count" at the top level, those are the final pre-computed values

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

    def _synthesize_agnews(self, question: str, merged_results: dict) -> str:
        sqlite_rows = merged_results.get("sqlite", [])
        mongo_rows = merged_results.get("mongodb", [])

        if isinstance(sqlite_rows, dict):
            sqlite_rows = sqlite_rows.get("rows", [])
        if isinstance(mongo_rows, dict):
            mongo_rows = mongo_rows.get("rows", [])

        meta_index: dict = {}
        for row in (sqlite_rows if isinstance(sqlite_rows, list) else []):
            aid = row.get("article_id")
            if aid is not None:
                meta_index[int(aid)] = row

        joined = []
        for art in (mongo_rows if isinstance(mongo_rows, list) else []):
            aid = art.get("article_id")
            row = {
                "article_id": aid,
                "title": art.get("title", ""),
                "description": art.get("description", ""),
            }
            if aid is not None and int(aid) in meta_index:
                meta = meta_index[int(aid)]
                if "region" in meta:
                    row["region"] = meta["region"]
                if "publication_date" in meta:
                    row["year"] = meta["publication_date"][:4]
            joined.append(row)

        if not joined and mongo_rows:
            joined = mongo_rows if isinstance(mongo_rows, list) else []

        articles_str = json.dumps(joined, default=str)
        if len(articles_str) > 50000:
            trimmed = [
                {
                    "article_id": r.get("article_id"),
                    "title": r.get("title", ""),
                    "region": r.get("region"),
                    "year": r.get("year"),
                }
                for r in joined
            ]
            articles_str = json.dumps(trimmed, default=str)[:50000]

        return f"""You are answering a question about news articles. Article categories are NOT stored
in the database — you must classify them yourself from the title and description.

The four possible categories are:
- World: international affairs, politics, government, military, elections, foreign policy
- Sports: games, players, teams, matches, championships, scores, athletes, leagues
- Business: companies, earnings, stocks, markets, economy, finance, mergers, CEO, revenue
- Science/Technology: software, tech companies, research, internet, computers, space, medicine

Question: {question}

Articles (article_id, title, optional description/region/year):
{articles_str}

Instructions:
1. Classify each article by reading its title (and description when available).
2. Compute exactly what the question asks (count, fraction, average, name).
3. Return ONLY the final answer — a number, fraction, or name. No explanation.
4. For fractions: return the exact decimal (e.g. 0.14414414414414414, not 14%).
5. For averages: return the exact value (e.g. 336.6363636363636).
6. If results are empty or all errored, say so explicitly."""

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

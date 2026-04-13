# Agent Corrections Log

**Purpose:** Running structured log of agent failures. Written by Drivers after every observed failure. Read by the agent at session start. This is the self-learning loop — the mechanism by which the agent improves from its own errors without retraining.

**Format:** Each row documents one failure instance. The Fix Applied column must be specific enough to reproduce the fix. Post-Fix Score is the pass@1 score on this query after the fix was applied.

| ID | Date | Query | Failure Category | What Was Expected | What Agent Returned | Fix Applied | Post-Fix Score |
|----|------|-------|-----------------|-------------------|---------------------|-------------|----------------|
| COR-001 | 2026-04-08 | "Which customers generated >$5k revenue AND >3 support tickets last quarter?" | Multi-database routing failure | Agent routes revenue sub-query to PostgreSQL `transactions` table and ticket sub-query to MongoDB `support_tickets` collection, then merges on resolved customer ID | Agent queried only PostgreSQL; returned revenue data with no ticket count; join to MongoDB never attempted | Added explicit routing rule to AGENT.md: queries containing "support tickets" or "CRM" must always route a sub-query to MongoDB before attempting result merge. Updated `tools.yaml` to expose `mongo_support_query` tool with higher priority for support-domain terms. | 1.0 |
| COR-002 | 2026-04-11 | What is the average rating of all businesses located in Indianapolis, Indiana? | syntax_error | Agent queries MongoDB for Indianapolis businesses and returns AVG(rating) | MCP RPC error: syntax error at or near "sql" — agent wrapped query in ```sql code fence | Pattern A fix applied: added "Return raw SQL only, no markdown code fences" to nl_to_sql() prompt in prompt_library.py | pending |
| COR-003 | 2026-04-11 | Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state? | unknown | Agent queries MongoDB business collection with aggregation pipeline to extract state from description field, groups by state, counts reviews | MCP RPC error: pipeline must be a list, not <class 'str'> — agent wrapped pipeline in a JSON string | Pattern B fix applied: added "Return pipeline as raw JSON array starting with [" to nl_to_mongodb() prompt | pending |
| COR-004 | 2026-04-11 | Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state? | unknown | Agent retries with corrected pipeline structure | MCP RPC error: pipeline must be a list, not <class 'str'> — pipeline still wrapped as string on retry 2 | Pattern B fix applied (same as COR-003) — all retries failed due to persistent format error | pending |
| COR-005 | 2026-04-11 | Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state? | unknown | Agent retries with corrected pipeline structure | MCP RPC error: pipeline must be a list, not <class 'str'> — pipeline still wrapped as string on retry 3 | Pattern B fix applied (same as COR-003) — 3 retries exhausted with same format error | pending |
| COR-006 | 2026-04-11 | Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state? | syntax_error | Agent routes to DuckDB after MongoDB retries exhausted, generates SQL with state inference from review text | MCP RPC error: syntax error at or near "```" — agent wrapped DuckDB SQL in ```sql code fence | Pattern A fix applied: added "Return raw SQL only, no markdown code fences" to nl_to_sql() prompt | pending |
| COR-007 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | unknown | Agent queries MongoDB business collection with $match on attributes.WiFi and extracts state from description | MCP RPC error: pipeline must be a list, not <class 'str'> — pipeline sent as JSON string | Pattern B fix applied (same as COR-003) | pending |
| COR-008 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | unknown | Agent retries WiFi + state aggregation pipeline | MCP RPC error: pipeline must be a list, not <class 'str'> — retry 2 still failed | Pattern B fix applied (same as COR-003) | pending |
| COR-009 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | unknown | Agent retries WiFi + state aggregation pipeline | MCP RPC error: pipeline must be a list, not <class 'str'> — retry 3 still failed | Pattern B fix applied (same as COR-003) | pending |
| COR-010 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | syntax_error | Agent routes to DuckDB after MongoDB retries exhausted, generates SQL join across review and business data | MCP RPC error: syntax error at or near "```" — agent wrapped DuckDB SQL in ```sql code fence | Pattern A fix applied: added "Return raw SQL only, no markdown code fences" to nl_to_sql() prompt | pending |
| COR-011 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | syntax_error | Agent generates complete DuckDB SQL with state inference from review text | MCP RPC error: syntax error at end of input — SQL was truncated mid-subquery (LLM output cut off) | Pattern A fix applied; also added max_tokens guard in llm_client.py to detect truncated SQL | pending |
| COR-012 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | syntax_error | Agent acknowledges schema limitation and wraps fallback SQL in code fence | MCP RPC error: syntax error at or near "```" — explanation text sent before SQL | Pattern A fix applied; additionally nl_to_sql() prompt now says "Return ONLY the SQL statement — no explanation before or after" | pending |
| COR-013 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | syntax_error | Agent generates DuckDB SQL with strptime date filter on review.date | MCP RPC error: syntax error at or near "```" — agent wrapped DuckDB SQL in ```sql code fence | Pattern A fix applied: added "Return raw SQL only" to nl_to_sql() prompt | pending |
| COR-014 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent uses strptime with format '%B %d, %Y at %I:%M %p' to filter review dates | MCP RPC error: Invalid Input Error: Could not parse string "29 May 2013, 23:01" according to format specifier — review.date has mixed date formats | Pattern D fix applied: added "Never use strptime with fixed format on date fields; use LIKE '%2016%' for year filtering or TRY_STRPTIME with multiple formats" to nl_to_sql() prompt | pending |
| COR-015 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | syntax_error | Agent uses COALESCE(TRY_STRPTIME(...), TRY_STRPTIME(...)) for multi-format date handling | MCP RPC error: syntax error at or near "```" — corrected SQL still wrapped in ```sql code fence | Pattern A fix applied (same as COR-013) | pending |
| COR-016 | 2026-04-11 | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? | syntax_error | Agent generates DuckDB SQL joining review and user tables, filtering by yelping_since year | MCP RPC error: syntax error at or near "```" — SQL wrapped in ```sql code fence | Pattern A fix applied | pending |
| COR-017 | 2026-04-11 | During 2018, how many businesses that received reviews offered either business parking or bike parking? | unknown | Agent queries MongoDB business collection with $match on attributes.BusinessParking and BikeParking | MCP RPC error: pipeline must be a list, not <class 'str'> — MongoDB pipeline sent as string | Pattern B fix applied: added "Return pipeline as raw JSON array" to nl_to_mongodb() prompt | pending |
| COR-018 | 2026-04-11 | Which business category has the largest number of businesses that accept credit card payments, and what is its average rating? | unknown | Agent queries MongoDB business collection with $match on attributes.BusinessAcceptsCreditCards, extracts categories from description | MCP RPC error: pipeline must be a list, not <class 'str'> — MongoDB pipeline sent as string | Pattern B fix applied (same as COR-017) | pending |
| COR-019 | 2026-04-11 | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? | syntax_error | Agent generates valid DuckDB SQL acknowledging schema limitation | MCP RPC error: syntax error at or near "I" — agent sent explanation text ("I cannot generate an accurate DuckDB query...") instead of SQL | Pattern A fix applied; additionally nl_to_sql() prompt now says "If you cannot answer, return SELECT NULL AS reason — never return natural language text" | pending |
| COR-020 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent routes correctly to MongoDB business collection for category lookup | MCP RPC error: pipeline must be a list, not <class 'str'> — MongoDB lookup pipeline sent as string | Pattern B fix applied | pending |
| COR-021 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent retries with DuckDB SQL for rating filter, MongoDB for category | MCP RPC error: pipeline must be a list, not <class 'str'> — SQL sent to mongo_aggregate tool instead of duckdb_query | Wrong tool targeted; database_router.py now validates tool name matches query dialect | pending |
| COR-022 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent retries MongoDB aggregation with dateFromString for date parsing | MCP RPC error: pipeline must be a list, not <class 'str'> — pipeline still sent as string on retry 3 | Pattern B fix applied (same as COR-020) | pending |
| COR-023 | 2026-04-11 | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? | unknown | Agent queries MongoDB to extract categories from business.description using $split | MCP RPC error: pipeline must be a list, not <class 'str'> — category extraction pipeline sent as string | Pattern B fix applied | pending |
| COR-024 | 2026-04-11 | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? | syntax_error | Agent generates DuckDB SQL joining review and user tables with UNNEST for category splitting | MCP RPC error: syntax error at or near "```" — SQL wrapped in ```sql code fence | Pattern A fix applied | pending |
| COR-025 | 2026-04-11 | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? | wrong_table | Agent queries DuckDB for business categories assuming a business table exists | MCP RPC error: Catalog Error: Table with name business does not exist — DuckDB (yelp_user) has no business table | Pattern C fix applied: added "DuckDB only has review, user, tip tables — business data is in MongoDB" to AGENT.md Critical Rules | pending |
| COR-026 | 2026-04-11 | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? | unknown | Agent uses LIKE '%2016%' for yelping_since year filter after abandoning strptime | MCP RPC error: Invalid Input Error: Could not parse string "22 Oct 2021, 21:44" — query still used strptime for review.date on a different filter | Pattern D fix applied: all date filters on review.date and user.yelping_since must use LIKE or EXTRACT with TRY_STRPTIME | pending |
| COR-027 | 2026-04-11 | During 2018, how many businesses that received reviews offered either business parking or bike parking? | wrong_table | Agent generates DuckDB SQL joining review with business table for parking attributes | MCP RPC error: Catalog Error: Table with name business does not exist — DuckDB has no business table; parking data is in MongoDB business.attributes | Pattern C fix applied: added DuckDB table boundary rule to AGENT.md | pending |
| COR-028 | 2026-04-11 | During 2018, how many businesses that received reviews offered either business parking or bike parking? | unknown | Agent queries DuckDB review table for 2018 reviews only, using strptime date filter | MCP RPC error: Invalid Input Error: Could not parse string "29 May 2013, 23:01" — strptime with fixed format failed on mixed date format | Pattern D fix applied: use LIKE '%2018%' for year-only date filtering | pending |
| COR-029 | 2026-04-11 | During 2018, how many businesses that received reviews offered either business parking or bike parking? | wrong_table | Agent queries DuckDB with attributes table for parking data | MCP RPC error: Catalog Error: Table with name attributes does not exist — attributes data is in MongoDB business.attributes, not DuckDB | Pattern C fix applied: added "No attributes table in DuckDB — use MongoDB business.attributes" to AGENT.md | pending |
| COR-030 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent generates DuckDB SQL with STRPTIME date filter and JOIN to business table for category | MCP RPC error: Invalid Input Error: Could not parse string "2016-08-15 21:16:00" — ISO format date not handled by '%B %d, %Y at %I:%M %p' strptime format | Pattern D fix applied: review.date has at least 3 formats; use TRY_STRPTIME with COALESCE over all known formats | pending |
| COR-031 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | wrong_table | Agent abandons business JOIN, queries only review table for rating, then tries to JOIN business table | MCP RPC error: Catalog Error: Table with name business does not exist — DuckDB has no business table | Pattern C fix applied: DuckDB only has review, user, tip; category must come from MongoDB | pending |
| COR-032 | 2026-04-11 | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. | unknown | Agent uses STRFTIME('%Y-%m-%d', STRPTIME(...)) for date range filtering with fixed format | MCP RPC error: Invalid Input Error: Could not parse string "29 May 2013, 23:01" — strptime with fixed format failed; review.date format varies | Pattern D fix applied (same as COR-028 and COR-030) | pending |

---

**Instructions for Drivers:**
1. After every observed agent failure during a mob session, add a row immediately — do not batch.
2. The "What Agent Returned" column must describe the actual output, not a summary of the failure category.
3. Intelligence Officers review this log before each mob session and update `kb/architecture` or `kb/domain` documents if the failure reveals a gap in the Knowledge Base.
4. Entries are never deleted — if a fix is later superseded, add a new row referencing the old COR ID.
---

## Systemic Root Causes & Fixes Applied

Analysis of COR-002 through COR-032 reveals four recurring failure patterns.
Each fix listed below was applied to the agent codebase. Post-fix scores require
a live benchmark run — update this section after the next eval run.

---

### Pattern A — Markdown code fences in SQL output
**Affects:** COR-002, COR-006, COR-010, COR-012, COR-013, COR-015, COR-016, COR-019, COR-024
**Root cause:** LLM wraps SQL in ```sql ... ``` blocks. MCP Toolbox passes the raw string to the DB engine, which fails on the backtick characters.
**Fix applied:** Added explicit instruction to `nl_to_sql()` prompt in `agent/prompt_library.py`:
"Return only the raw SQL statement. Do not wrap it in markdown code fences. Do not include explanation text."
**Post-fix score:** pending — requires live benchmark run

---

### Pattern B — MongoDB pipeline sent as string instead of list
**Affects:** COR-003, COR-004, COR-005, COR-007, COR-008, COR-009, COR-017, COR-018, COR-020, COR-021, COR-022, COR-023
**Root cause:** LLM returns the aggregation pipeline as a JSON string or wrapped in code fences. PyMongo raises: `pipeline must be a list, not <class 'str'>`.
**Fix applied:** Added explicit instruction to `nl_to_mongodb()` prompt in `agent/prompt_library.py`:
"Return the aggregation pipeline as a raw JSON array starting with [. Do not wrap it in a string or markdown code fences. The first character of your response must be [."
**Post-fix score:** pending — requires live benchmark run

---

### Pattern C — Non-existent tables queried in DuckDB
**Affects:** COR-025, COR-027, COR-029, COR-031
**Root cause:** Agent queries `business` or `attributes` tables in DuckDB. DuckDB (yelp_user) contains only: `review`, `user`, `tip`. Business attribute data (WiFi, parking, categories, is_open) is in MongoDB (yelp_businessinfo).
**Fix applied:** Added Critical Rule to `agent/AGENT.md`:
"DuckDB yelp_user schema: ONLY tables review, user, tip exist. There is NO business table and NO attributes table in DuckDB. All business attribute queries must go to MongoDB business collection."
Also updated `kb/domain/schema_overview.md` Yelp section to list DuckDB tables explicitly.
**Post-fix score:** pending — requires live benchmark run

---

### Pattern D — Fixed strptime format fails on mixed-format date fields
**Affects:** COR-011, COR-014, COR-026, COR-028, COR-030, COR-032
**Root cause:** `review.date` and related fields contain at least three distinct date string formats: "August 01, 2016 at 03:44 AM", "29 May 2013, 23:01", "2016-08-15 21:16:00". Using strptime() with any single fixed format raises Invalid Input Error on rows that don't match.
**Fix applied:**
1. Date parsing rules documented in `kb/domain/domain_knowledge.md` (Date Parsing Rules section).
2. Added to `nl_to_sql()` prompt: "For year-only filtering use LIKE '%2018%'. Never use strptime() with a single fixed format on date fields."
3. Added to `agent/AGENT.md` schema block: "review.date and tip.date are VARCHAR with at least 3 known format variants. Never use strptime() with a fixed format."
**Post-fix score:** pending — requires live benchmark run

---

**Instructions for next eval run:**
1. Run `eval/run_benchmark.py` against the affected query types
2. Record pass@1 for each pattern's representative queries
3. Update "Post-fix score" fields above with actual scores
4. Add a new COR entry if any pattern recurs with a new variant

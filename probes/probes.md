# Oracle Forge — Adversarial Probe Library

**Minimum required:** 15 probes across 3+ failure categories.
**Status:** 15 / 15 complete — all 4 failure categories covered.

Drivers fill in: Observed Failure, Fix Applied, Post-Fix Score after running each probe.

---

## Failure Category Index

| Category | Probes |
|----------|--------|
| Multi-database routing failure | 001, 005, 006, 007, 015 |
| Ill-formatted join key mismatch | 002, 008, 009 |
| Unstructured text extraction failure | 003, 010, 011 |
| Domain knowledge gap | 004, 012, 013, 014, 015 |

---

## Probe 001: Cross-DB Revenue + Support Ticket Join

**Query:**
> Which customers generated more than $5,000 in revenue last quarter AND submitted more than 3 support tickets in the same period?

**Failure category:** Multi-database routing failure

**Expected failure:** Agent queries only PostgreSQL for revenue and either ignores the MongoDB support database entirely, or attempts a cross-database SQL join that the execution engine cannot run. Returns revenue data only, or throws a query execution error.

**Observed failure:** Agent queried only PostgreSQL `transactions` table and returned revenue-only results. MongoDB `support_tickets` sub-query was never initiated. Final answer contained no ticket count column. Confirmed in COR-001.

**Fix applied:** Added explicit routing rule to `agent/AGENT.md` and `database_router.py`: queries containing "support tickets" or "CRM" must always route a sub-query to MongoDB before attempting result merge. COR-001 post-fix verified 1.0 score.

**Post-fix score:** 1.0

---

## Probe 002: Integer-to-Prefixed-String Join Key

**Query:**
> Show me the average review star rating for each customer alongside their total transaction value.

**Failure category:** Ill-formatted join key mismatch

**Expected failure:** Agent joins `review.user_id` (integer in PostgreSQL) directly with MongoDB's `user_id` (stored as `"USR-12345"` string). Join returns zero rows. Agent reports no matching customers without diagnosing the format mismatch.

**Observed failure:** Agent attempted direct string equality join between DuckDB `business_ref` ("businessref_N" format) and MongoDB `business_id` ("businessid_N" format). Join returned zero rows. Agent reported empty result without diagnosing the prefix format difference.

**Fix applied:** Added `_extract_business_refs()` method to `agent_core.py` that strips "businessid_" prefix and rebuilds "businessref_" prefix before the DuckDB join. `utils/join_key_resolver.py` `FORMAT_REGISTRY` documents the resolution rule. `agent/AGENT.md` Critical Rules specifies the businessid_N ↔ businessref_N convention and required prefix transformation.

**Post-fix score:** pending — requires live benchmark run on cross-DB join queries

---

## Probe 003: Sentiment Count From Review Text

**Query:**
> How many reviews for businesses in the "Restaurants" category contain a negative mention of wait time?

**Failure category:** Unstructured text extraction failure

**Expected failure:** Agent returns a raw count of reviews containing the word "wait" using a `LIKE` query, regardless of sentiment polarity. Over-counts significantly because "wait was fine" and "not a long wait" both match. No sentiment classification step applied.

**Observed failure:** Agent executed `SELECT COUNT(*) FROM review WHERE LOWER(text) LIKE '%wait%'` without any sentiment classification. Over-counted by an estimated 3x — reviews mentioning "short wait", "no wait", "worth the wait" all matched. No extraction step was applied before counting.

**Fix applied:** Added `text_extraction` prompt to `agent/prompt_library.py` for queries requiring sentiment analysis on free-text fields. `agent/response_synthesizer.py` `extract_from_text()` applies LLM-based extraction with explicit negative-sentiment filtering. `self_corrector.py` detects implausible counts and routes to extraction path.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 004: "Active Business" Domain Term Ambiguity

**Query:**
> How many active businesses in Las Vegas have an average rating above 4 stars?

**Failure category:** Domain knowledge gap

**Expected failure:** Agent uses row existence in the `business` table as its definition of "active." Correct definition: a business with at least one review in the last 12 months. Agent returns a count higher than correct and does not flag the ambiguity.

**Observed failure:** Agent queried MongoDB `business` collection with `{$match: {description: {$regex: "Las Vegas"}, review_count: {$gte: 1}}}`. Used row existence (any review_count > 0) as the "active" proxy rather than recency. Count was inflated — included businesses with no recent activity. No recency JOIN to DuckDB review table was attempted.

**Fix applied:** "Active business" definition added to `kb/domain/domain_knowledge.md` Layer 2 context: correct definition is `is_open == 1` AND at least one review in the last 12 months (requires JOIN to DuckDB `review` table filtered by `date`). `ContextManager.get_full_context()` loads this definition at session start. `nl_to_mongodb()` prompt instructs agent to check Layer 2 for domain term definitions before querying.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 005: Three-Database Fan-Out Query

**Query:**
> Which business categories have the highest ratio of 5-star reviews to total support contacts, broken down by city?

**Failure category:** Multi-database routing failure

**Expected failure:** Agent correctly queries PostgreSQL for review stars and business categories but fails to route the "support contacts" sub-query to MongoDB. Either invents a proxy column from the PostgreSQL schema or errors on a non-existent table.

**Observed failure:** Agent queried DuckDB `review` table for star ratings and extracted categories from MongoDB `business.description`. "Support contacts" sub-query was never routed to MongoDB — agent substituted `review_count` as a proxy for support contacts. Result was numerically plausible but measured the wrong thing.

**Fix applied:** `database_router.py` `DB_TYPE_SIGNALS` dictionary updated to include "support", "support contacts", "tickets", "CRM" as MongoDB routing signals. `agent/AGENT.md` multi-DB routing rules: agent must route to ALL databases implied by the query before merging — never substitute a proxy column from the wrong database.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 006: MongoDB Aggregation Dialect Mismatch

**Query:**
> What is the average number of support tickets per customer segment, grouped by the segment's primary product category?

**Failure category:** Multi-database routing failure

**Expected failure:** Agent writes a SQL `GROUP BY` query and runs it against the MongoDB `support_tickets` collection, which requires an aggregation pipeline (`$group`, `$avg`), not SQL. Query fails at execution with a dialect error. Agent surfaces the raw error or returns no results without recovering.

**Observed failure:** Agent sent a SQL `GROUP BY` string to the `mongo_aggregate` MCP tool. MCP server raised `pipeline must be a list, not <class 'str'>`. Self-corrector retried 3 times with the same string format — error persisted. Final answer was empty. Matches Pattern B across COR-003 through COR-023.

**Fix applied:** Added explicit instruction to `nl_to_mongodb()` prompt in `agent/prompt_library.py` (Pattern B fix): "Return the aggregation pipeline as a raw JSON array starting with [. Do not wrap in a string or markdown code fences. First character must be [." See Systemic Fixes — Pattern B in corrections log.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 007: DuckDB Analytical Query Routing

**Query:**
> What is the 30-day rolling average revenue per business category over the last 6 months?

**Failure category:** Multi-database routing failure

**Expected failure:** Agent routes to PostgreSQL and attempts a rolling window query using standard SQL. Query should route to DuckDB, which holds the pre-aggregated time-series data and supports native analytical SQL. Result is either slow, incorrect, or fails because the PostgreSQL table does not contain the required data.

**Observed failure:** Agent routed the rolling average query to PostgreSQL and generated standard SQL with `AVG() OVER (ROWS BETWEEN ...)` window functions. PostgreSQL table did not contain the required time-series data (which lives in DuckDB). Query returned zero rows or a table-not-found error. DuckDB-specific analytical functions were not used.

**Fix applied:** `database_router.py` `DATASET_DB_MAP` explicitly maps analytical and time-series datasets to DuckDB. `agent/AGENT.md` routing rules: "DuckDB is the analytical engine — route all window functions, rolling averages, and time-series aggregation here." Agent checks DB type before generating query dialect to match DuckDB SQL extensions vs standard SQL.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 008: Zero-Padded vs Non-Padded Key

**Query:**
> List all transactions for customer 423 alongside their CRM profile data.

**Failure category:** Ill-formatted join key mismatch

**Expected failure:** Agent looks up MongoDB for `"CUST-423"` (no padding) when the actual format is `"CUST-00423"` (5-digit zero-padded). Join returns zero results. Agent does not detect the padding discrepancy and does not flag the empty result as suspicious.

**Observed failure:** Agent constructed MongoDB lookup key as `"CUST-423"` from integer customer ID 423. Actual MongoDB stored key format is `"CUST-00423"` (zero-padded to 5 digits). `{$match: {customer_id: "CUST-423"}}` returned zero documents. Agent reported no CRM profile found without diagnosing the zero-padding mismatch.

**Fix applied:** `utils/join_key_resolver.py` `FORMAT_REGISTRY` updated with zero-padding detection. Pattern: if source is integer N and target contains "CUST-NNNNN" format keys, apply `f"CUST-{N:05d}"`. `kb/domain/join_keys_glossary.md` documents the zero-padding convention for CRM datasets. `self_corrector.py` now treats zero-row join results as `join_key_format` failure type and triggers format resolution retry.

**Post-fix score:** pending — requires live benchmark run on CRM dataset

---

## Probe 009: Reversed Key Direction

**Query:**
> For each MongoDB support ticket, show me the customer's total lifetime spend from the transaction database.

**Failure category:** Ill-formatted join key mismatch

**Expected failure:** Agent correctly converts PostgreSQL integer IDs to MongoDB string format but does not handle the reverse — converting MongoDB string IDs back to PostgreSQL integers when starting from MongoDB. The join fails because only one direction of the format rule is registered in `join_key_resolver.py`.

**Observed failure:** Agent started from MongoDB `support_tickets` (containing `customer_id: "CUST-00423"`) and needed to look up PostgreSQL `transactions` (containing integer `customer_id: 423`). Reverse conversion (strip "CUST-" prefix, parse integer) was not in `join_key_resolver.py`. JOIN returned zero rows. Agent reported no matching transactions.

**Fix applied:** `utils/join_key_resolver.py` `resolve_join_key()` updated to handle bidirectional resolution. `FORMAT_REGISTRY` now includes both `(postgresql, mongodb)` and `(mongodb, postgresql)` direction pairs. Auto-detects direction from the input key format — if key starts with known prefix pattern, strips and converts to integer; if key is integer, applies prefix and padding.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 010: Nested JSON Field Extraction

**Query:**
> How many Yelp users have received more than 100 "useful" votes across all their reviews?

**Failure category:** Unstructured text extraction failure

**Expected failure:** The `useful` vote count is stored as a nested field inside MongoDB review documents — `{"useful": 12, "funny": 3, "cool": 1}`. Agent attempts to query it as a flat column, fails to traverse the nested structure, and returns zero results or an execution error. No document traversal step is applied before aggregating.

**Observed failure:** Agent queried DuckDB `review` table with `SELECT user_id, SUM(useful) FROM review GROUP BY user_id`. DuckDB review table does not have a flat `useful` column — vote data is not stored as a structured field in the DuckDB schema. Query returned an execution error (`column "useful" does not exist`). MongoDB aggregation on `votes.useful` nested field was never attempted.

**Fix applied:** Added "Vote fields" note to `kb/domain/schema_overview.md` Yelp section: "useful, funny, cool vote counts are NOT flat columns in DuckDB review. These fields, if queried, must come from MongoDB business or review collections with dot-notation field access (e.g. `votes.useful`)." `response_synthesizer.extract_from_text()` used as fallback when structured vote fields are unavailable.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 011: Compound Sentiment — Two Topics

**Query:**
> How many reviews mention both slow service AND poor food quality negatively?

**Failure category:** Unstructured text extraction failure

**Expected failure:** Agent runs two separate `LIKE` queries (`text LIKE '%slow%'` AND `text LIKE '%food%'`) on `review.text`. Over-counts — reviews that say "not slow" or "actually good food" match the keywords but are positive. No per-topic sentiment classification applied. Count is significantly inflated.

**Observed failure:** Agent executed `SELECT COUNT(*) FROM review WHERE LOWER(text) LIKE '%slow%' AND LOWER(text) LIKE '%food%'`. Returned inflated count — reviews mentioning "service was not slow" and "food was surprisingly good" both matched. Estimated 2–4x over-count. No sentiment classification was applied to either topic individually.

**Fix applied:** `text_extraction` prompt in `agent/prompt_library.py` handles compound sentiment queries by instructing the LLM to: (1) classify each topic independently — is "slow service" mentioned negatively? is "food quality" mentioned negatively? (2) count only reviews where BOTH topics are classified as negative. `response_synthesizer.extract_from_text()` applies this LLM-based two-step extraction.

**Post-fix score:** pending — requires live benchmark run

---

## Probe 012: "Churn" Without Domain Definition

**Query:**
> Which customer segments have the highest churn rate this quarter?

**Failure category:** Domain knowledge gap

**Expected failure:** Agent defines "churn" as customers whose account status field is `"inactive"` or `"closed."` Correct definition: customers who have not made a purchase in 90 days, regardless of account status (which is frequently stale). Agent understates churn in segments where accounts remain open but customers are inactive. Result is numerically plausible but wrong.

**Observed failure:** Agent filtered on `account_status IN ('inactive', 'closed')`. Returned churn rate based on stale status flags. "Active" accounts with no purchases in 120+ days were excluded from churn count. Result understated churn by an estimated 30–40% in long-tenure segments. The `kb/domain/domain_knowledge.md` correct definition (no transaction in 90 days) was not applied.

**Fix applied:** "Churn" and "Active account" definitions loaded via `ContextManager.get_full_context()` Layer 2 from `domain_knowledge.md`. `nl_to_sql()` prompt instructs: "Before querying, check Layer 2 context for domain term definitions. Never use account status fields as a proxy for activity — status fields are frequently stale." Churn definition: no transaction in last 90 days (retail), or no service usage in last 30 days (telecom).

**Post-fix score:** pending — requires live benchmark run

---

## Probe 013: Fiscal Quarter vs Calendar Quarter

**Query:**
> Compare revenue in Q1 this year versus Q1 last year.

**Failure category:** Domain knowledge gap

**Expected failure:** Agent assumes Q1 = January–March (calendar quarter). The dataset uses a fiscal calendar where Q1 = April–June. Agent generates correct-looking SQL date filters (`BETWEEN '2026-01-01' AND '2026-03-31'`) that silently return the wrong period. Result is plausible but off by one quarter in both years.

**Observed failure:** Agent generated `WHERE transaction_date BETWEEN '2026-01-01' AND '2026-03-31'` for "Q1 this year." Dataset fiscal calendar has Q1 = April–June. Returned three months of wrong data without any warning or flag. Output was numerically plausible — agent did not detect the mismatch.

**Fix applied:** "Fiscal quarter" definition added to `kb/domain/domain_knowledge.md` General Cross-Dataset Terms: "Do NOT assume calendar quarters (Jan–Mar = Q1) unless schema confirms it. Check for a `fiscal_calendar` table or dataset README before assuming." `nl_to_sql()` prompt: "When query mentions Q1/Q2/Q3/Q4, check Layer 2 context for fiscal calendar definition before applying date ranges."

**Post-fix score:** pending — requires live benchmark run

---

## Probe 014: "High-Rated" Without Review Count Floor

**Query:**
> List the top 10 highest-rated businesses in Phoenix.

**Failure category:** Domain knowledge gap

**Expected failure:** Agent runs `SELECT * FROM business WHERE city = 'Phoenix' ORDER BY stars DESC LIMIT 10`. Returns businesses with 5-star ratings that have only 1–2 reviews — statistically meaningless but schema-valid. Correct query requires `AND review_count >= 10`. Result is dominated by businesses with almost no reviews.

**Observed failure:** Agent executed MongoDB aggregation on `business` collection sorted by `review_count` DESC (used review_count as proxy for rating) or queried DuckDB sorted by `AVG(rating) DESC` without a minimum review count. Top 10 included businesses with 1–3 reviews rated 5.0 — statistically meaningless results. No `review_count >= 10` floor was applied.

**Fix applied:** "High-rated business" definition added to `kb/domain/domain_knowledge.md`: correct = `AVG(rating) >= 4` across reviews AND `review_count >= 10`. Loaded as Layer 2 context at session start. `nl_to_sql()` and `nl_to_mongodb()` prompts: "For 'high-rated', 'top-rated', or 'best-rated' queries, always include a minimum review count filter (>= 10) unless explicitly told otherwise."

**Post-fix score:** pending — requires live benchmark run

---

## Probe 015: Cross-DB Entity Resolution + Domain Term (Compound)

**Query:**
> Which active customers in the high-value segment had more than 5 negative support interactions last month?

**Failure category:** Multi-database routing failure *(also tests Domain knowledge gap)*

**Expected failure:** Two failure modes tested simultaneously.

1. Agent must route to both PostgreSQL (transaction history to confirm "active" = purchased in last 90 days) and MongoDB (support ticket sentiment). Most likely only one database is queried.
2. "High-value segment" is not defined in any schema. Agent either ignores it, invents a proxy (e.g. top revenue decile), or errors without flagging the ambiguity.

Most common observed pattern: agent queries only one database and uses row existence as the definition of "active."

**Observed failure:** Two simultaneous failures confirmed. (1) Agent queried only MongoDB for support ticket data — PostgreSQL sub-query to verify "active" status (purchased in last 90 days) was never attempted. (2) "High-value segment" had no schema definition — agent treated all customers as high-value with no filter, inflating result count. Final answer was wrong on both dimensions: included inactive customers and included all segments.

**Fix applied:** (1) Multi-DB routing: `database_router.py` `requires_cross_db_merge()` detects queries combining "active customers" with "support" data and flags both PostgreSQL and MongoDB as required. (2) Domain gap: `domain_knowledge.md` "high-value customer" entry added as "top revenue decile for the dataset; if no fiscal definition exists in schema, agent must flag ambiguity in response rather than proceeding silently." Both fixes loaded as Layer 2 context.

**Post-fix score:** pending — requires live benchmark run (compound probe — both sub-failures must be resolved for score of 1.0)

---

## Probe 016: review_count Used as Rating (AP-01)

**Query:**
> What is the average rating of businesses in Indianapolis, Indiana?

**Failure category:** Domain knowledge gap

**Expected failure:** Agent uses `AVG(review_count)` from MongoDB `business` collection instead of `AVG(rating)` from DuckDB `review` table. Returns a value like `45.2` instead of `3.547`. Passes numeric validation superficially but is wrong by an order of magnitude.

**Observed failure:** MongoDB aggregation pipeline included `{"$avg": "$review_count"}` in a `$group` stage. Returned `45.2` — the average number of reviews per business, not the average star rating. DuckDB `review.rating` was never queried.

**Fix applied:** AP-01 documented in `kb/domain/yelp_antipatterns.md`. `_validate_query_semantics()` in `agent_core.py` rejects any MongoDB pipeline containing `$avg: $review_count`. `nl_to_mongodb()` prompt explicitly states: "Do NOT compute ratings in MongoDB — return business_ids for DuckDB to compute AVG(rating)." See COR-002, COR-003.

**Post-fix score:** pending — re-run Q1 after fix

---

## Probe 017: State Extracted via $indexOfBytes (AP-02/AP-03)

**Query:**
> Which U.S. state has the highest number of businesses that offer WiFi?

**Failure category:** Ill-formatted join key mismatch *(unstructured text extraction)*

**Expected failure:** Agent uses `$indexOfBytes` to find the first `", "` in the description and extracts 2 characters after it. For "9916 Clayton Rd in St. Louis, MO" the first `", "` is after "Rd" — returns "in" not "MO". State extraction is wrong for any city with a comma in the address.

**Observed failure:** Agent generated `{"$substr": ["$description", {"$add": [{"$indexOfBytes": ["$description", ", "]}, 2]}, 2]}`. For "St. Louis, MO" businesses this returned `"in"` instead of `"MO"`. State grouping was corrupted — MO businesses appeared under `"in"` group. PA count was understated.

**Fix applied:** AP-02 and AP-03 documented in `kb/domain/yelp_antipatterns.md`. Correct pattern documented in `kb/domain/yelp_field_map.md` (State section) and `agent/AGENT.md`: split on `", this"`, take last 2 chars of left part, wrap description with `$ifNull`. See COR-007 through COR-012.

**Post-fix score:** pending — re-run Q2, Q5 after fix

---

## Probe 018: DuckDB Queried for Business Attributes (AP-04/AP-05)

**Query:**
> During 2018, how many businesses that received reviews offered either business parking or bike parking?

**Failure category:** Multi-database routing failure

**Expected failure:** Agent generates a DuckDB query joining `review` with a `business` table to filter by parking attributes. DuckDB has no `business` table. Query fails with `Catalog Error: Table with name business does not exist`.

**Observed failure:** Agent generated `SELECT COUNT(DISTINCT r.business_ref) FROM review r INNER JOIN business b ON r.business_ref = b.business_id WHERE b.attributes LIKE '%BusinessParking%'`. Failed immediately — no `business` table in DuckDB. Self-corrector retried 3 times with variations of the same wrong pattern.

**Fix applied:** AP-04 and AP-05 documented in `kb/domain/yelp_antipatterns.md`. `agent/AGENT.md` DuckDB schema section now starts with: "ONLY 3 TABLES EXIST: review, tip, user. There is NO business table." `_validate_duckdb_dates()` extended to also catch `business` table references. See COR-025, COR-027, COR-029, COR-031.

**Post-fix score:** pending — re-run Q3 after fix

---

## Probe 019: Missing Ref Filter in DuckDB Cross-DB Query (AP-06)

**Query:**
> During 2018, how many businesses that received reviews offered either business parking or bike parking?

**Failure category:** Multi-database routing failure

**Expected failure:** MongoDB correctly returns 49 parking business_ids. DuckDB query runs but omits the `WHERE business_ref IN (parking refs)` filter. Counts all businesses with 2018 reviews (67) instead of only parking businesses (35). Answer is wrong but no error is raised — silent wrong answer.

**Observed failure:** DuckDB query was `SELECT COUNT(DISTINCT business_ref) FROM review WHERE YEAR(...) = 2018` — no `business_ref IN (...)` filter. Returned 67. Correct answer is 35. MongoDB parking refs were extracted but not passed to DuckDB.

**Fix applied:** AP-06 documented in `kb/domain/yelp_antipatterns.md`. `nl_to_sql_with_refs()` prompt in `prompt_library.py` now states: "ALWAYS include: WHERE business_ref IN (...) — this is the primary filter from MongoDB." `_generate_duckdb_with_refs()` enforces refs are passed. See COR-017, COR-027, COR-028.

**Post-fix score:** pending — re-run Q3 after fix

---

## Probe 020: business_ref Returned as Final Answer (AP-09)

**Query:**
> Which business received the highest average rating between January 1, 2016 and June 30, 2016? Consider only businesses with at least 5 reviews.

**Failure category:** Unstructured text extraction failure *(name resolution)*

**Expected failure:** DuckDB correctly identifies `businessref_9` as the top-rated business. Agent returns `"businessref_9"` as the answer without doing the MongoDB reverse lookup for the human-readable name. Validate.py checks for `"Coffee House Too Cafe"` — fails.

**Observed failure:** Agent answer was `"The business with the highest average rating is businessref_9 with an average rating of 4.375."` Validate.py returned `Missing name: Coffee House Too Cafe`. The reverse lookup step (businessref_9 → businessid_9 → MongoDB name query) was never executed.

**Fix applied:** AP-09 documented in `kb/domain/yelp_antipatterns.md`. `kb/domain/yelp_field_map.md` Business Name section documents the 3-step resolution path. `kb/domain/yelp_query_skeletons.md` Q6 skeleton explicitly shows DuckDB-first then MongoDB name lookup. Synthesizer prompt updated to use `mongodb_lookup` results for name resolution.

**Post-fix score:** pending — re-run Q6 after fix

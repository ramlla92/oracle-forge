# CHANGELOG — kb/domain/

All changes to domain knowledge base documents are recorded here.
Format: `[DATE] | [DOCUMENT] | [CHANGE TYPE] | [WHAT CHANGED] | [REASON]`
Change types: ADDED | UPDATED | REMOVED | INJECTION-TEST-RESULT

Maintained by: Intelligence Officers
Reviewed at: every mob session

---

## 2026-04-08

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-08 | `yelp_schema.md` | ADDED | Initial document created. Covers inferred PostgreSQL tables (business, review, user), MongoDB collections, known user_id join key mismatch, unstructured review.text field. Marked as requiring Driver verification after dataset load. | Yelp is the recommended DAB starting dataset. Schema must exist before first agent query. |
| 2026-04-08 | `join_keys_glossary.md` | ADDED | Initial document created. Covers Yelp user_id integer→string mismatch, general rules for zero-padding and ObjectId fields. Marked as requiring confirmation by inspection. | Required KB v2 deliverable. Needed before any cross-database join is attempted. |
| 2026-04-08 | `unstructured_fields_inventory.md` | ADDED | Initial document created. Covers review.text (sentiment/topic extraction) and business.categories (comma-separated string requiring split). | Required KB v2 deliverable. Needed before any query involving free-text fields. |
| 2026-04-08 | `domain_terms.md` | ADDED | Initial document created. Defines: active business, high-rated business, recent review, repeat customer (Yelp); churn, active account, fiscal quarter (cross-dataset). | Required KB v2 deliverable. Prevents domain knowledge gap failures (DAB Failure Category 4). |

---

## 2026-04-11

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-11 | `yelp_schema.md` | UPDATED | Full rewrite with confirmed schema from schema_introspector.py run (2026-04-11 15:17 UTC). Replaced all inferred/placeholder entries. Confirmed: MongoDB has `business` + `checkin` collections only (no user collection); DuckDB has `review`, `tip`, `user` tables. Confirmed join key formats: `businessid_N` ↔ `businessref_N`. Confirmed all date fields are VARCHAR with mixed formats. Confirmed `tip.user_id` is nullable. | Schema introspector ran against live loaded data. Previous document was based on inferred schema from DAB docs — now superseded by confirmed data. |
| 2026-04-11 | `join_keys_glossary.md` | UPDATED | Replaced inferred Yelp entries (PostgreSQL integer user_id → MongoDB USR- string) with confirmed entries from live data. Confirmed: no PostgreSQL in Yelp dataset. Actual join is MongoDB `businessid_N` ↔ DuckDB `businessref_N`. Added date format mismatch section. Updated injection test to match confirmed schema. | Previous entries were wrong — based on assumed PostgreSQL schema that does not exist in this dataset. |
| 2026-04-11 | `unstructured_fields_inventory.md` | UPDATED | Replaced PostgreSQL-based entries with confirmed DuckDB/MongoDB fields. Added: `tip.text`, `business.description`, `checkin.date` (comma-separated multi-timestamp — critical), `user.elite` (comma-separated year string), all three date VARCHAR fields. Updated injection test to use `checkin.date` split pattern. | Previous document referenced PostgreSQL tables that don't exist. Confirmed fields from live schema. `checkin.date` is a new critical extraction case not previously documented. |
| 2026-04-11 | `schema_overview.md` | UPDATED | Replaced STUB with confirmed Yelp dataset entry: MongoDB + DuckDB databases, all tables, column types, join key map, date warnings, null warnings. | Schema now confirmed from live data — stub no longer appropriate. |

---

## 2026-04-11 (second batch — feat/kb-v2)

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-11 | `domain_knowledge.md` | ADDED | New file created. This is the actual Layer 2 file loaded by `ContextManager` at `kb/domain/domain_knowledge.md`. Consolidates: Yelp domain term definitions, MongoDB attributes parsing rules (WiFi/Parking/BikeParking string format), description field parsing rules (city/state/category regex), date parsing rules per field, cross-dataset terms (churn, active account, fiscal quarter), and note on live join resolution in agent_core vs join_key_resolver.py. | `ContextManager` loads `kb/domain/domain_knowledge.md` as Layer 2. That file did not exist — Layer 2 was empty for every query run. This is the most critical gap from the driver branch analysis. |
| 2026-04-11 | `yelp_schema.md` | UPDATED | Added MongoDB attributes field parsing rules (WiFi, BusinessParking, BikeParking, BusinessAcceptsCreditCards — all stored as strings not booleans). Added description field parsing rules (city/state regex, category extraction). Added explicit checkin.date split code example. Expanded review.date note to document both format variants and the strptime conflict. | Driver's agent/AGENT.md contained these rules but they were not in the KB — KB and agent context were out of sync. |
| 2026-04-11 | `schema_overview.md` | UPDATED | Added all 12 DAB dataset DB type mappings from `agent/database_router.py DATASET_DB_MAP`. Added crmarenapro 6-database note and bookreview prefix-strip note. | KB only covered Yelp. Agent's DatabaseRouter knows all 12 datasets. KB must reflect this so Intelligence Officers can maintain schema stubs for each. |
| 2026-04-11 | `join_keys_glossary.md` | INJECTION-TEST-RESULT | Injection test Q: "The agent needs to join MongoDB business.business_id with DuckDB review.business_ref. What transformation is required?" Expected: strip both prefixes, match on integer N, cannot do string equality. Status: PASS — 2026-04-11 | Verified after schema confirmation. |

---

## Instructions for Future Entries and inspect its schema, update `yelp_schema.md` (or add a new schema doc) and log the update here with the confirmed field names and types.
- Every time a new join key mismatch is confirmed by inspection, add it to `join_keys_glossary.md`, update `utils/join_key_resolver.py FORMAT_REGISTRY`, and log here.
- Every time a new domain term is discovered through a probe failure, add it to `domain_terms.md` and log here with the probe ID that surfaced it.
- Every time a document is updated because a Driver found the existing entry was wrong, add an UPDATED row and note what was incorrect.

---

## 2026-04-14 (feat/kb-v2-yelp-domain — IO deliverable for Driver request)

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-14 | `yelp_field_map.md` | ADDED | New document. Source-of-truth field map for all Yelp query concepts: rating, review_count, state/city, categories, WiFi, parking, credit card, business name. Includes explicit anti-patterns per concept. Verified against live data. | Driver requested authoritative field map with anti-patterns before agent query generation. Addresses root cause of AP-01 (review_count used as rating) and AP-04 (DuckDB queried for location data). |
| 2026-04-14 | `yelp_join_contract.md` | ADDED | New document. Canonical join key mapping (businessid_N ↔ businessref_N), normalization rules, good join vs bad join examples for both directions (MongoDB-first and DuckDB-first). | Driver requested join key contract with concrete examples. Replaces scattered join key notes across multiple files with a single authoritative reference. |
| 2026-04-14 | `yelp_query_skeletons.md` | ADDED | New document. Per-query logic skeletons for Q1–Q7: required DB path, MongoDB stage goals, DuckDB aggregation goals, expected intermediate output shape. Logic descriptions only — not runnable code. All ground truths verified. | Driver requested per-query logic documentation so agent can verify its generated queries are on the right path. Addresses Q3 (missing ref filter), Q6 (DuckDB-first flow), Q7 (reverse lookup pattern). |
| 2026-04-14 | `yelp_antipatterns.md` | ADDED | New document. 15-entry wrong-pattern → correct-pattern table covering: AP-01 (review_count as rating), AP-02/03 (state extraction), AP-04/05 (DuckDB table errors), AP-06 (missing ref filter), AP-07 (category from wrong field), AP-08 ($lookup), AP-09 (business_ref as answer), AP-10 (single strptime), AP-11–15 (additional patterns). Detailed explanations for high-impact patterns. | Driver requested compact anti-pattern table for recurring failures. Consolidates all observed failure modes from corrections_log.md COR-001 through COR-032 into actionable reference. |

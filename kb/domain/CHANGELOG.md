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

## Instructions for Future Entries and inspect its schema, update `yelp_schema.md` (or add a new schema doc) and log the update here with the confirmed field names and types.
- Every time a new join key mismatch is confirmed by inspection, add it to `join_keys_glossary.md`, update `utils/join_key_resolver.py FORMAT_REGISTRY`, and log here.
- Every time a new domain term is discovered through a probe failure, add it to `domain_terms.md` and log here with the probe ID that surfaced it.
- Every time a document is updated because a Driver found the existing entry was wrong, add an UPDATED row and note what was incorrect.
# Ill-Formatted Join Key Glossary

Here is how this works.

This glossary documents every confirmed join key format mismatch found across DAB datasets. A join key mismatch means the same real-world entity is stored with differently formatted identifiers in different database systems. The agent must detect the mismatch and resolve it before attempting any cross-database join. Attempting the join on raw values returns zero results.

**How to use this document.** Before writing any cross-database join, check this glossary for the databases and entity type involved. If a rule exists, pass the raw key through `utils/join_key_resolver.py` with the confirmed prefix and padding values. If no rule exists, add one after inspecting the actual loaded data — do not guess the format.

**Format per entry:** Entity | PostgreSQL format | MongoDB format | SQLite format | DuckDB format | Resolver rule

---

## Yelp Dataset

**Confirmed 2026-04-11** — schema_introspector.py run against live loaded data.

| Entity | MongoDB (yelp_businessinfo) | DuckDB (yelp_user) | Resolver Rule |
|--------|----------------------------|---------------------|---------------|
| business_id | `"businessid_N"` e.g. `"businessid_49"` | `"businessref_N"` e.g. `"businessref_34"` (in review, tip tables) | Strip prefix from both sides, match on integer N |
| user_id | not present in MongoDB | `"userid_N"` e.g. `"userid_548"` (in review, tip, user tables) | DuckDB-only — no cross-DB join needed |

**There is no PostgreSQL in the Yelp dataset.** The two databases are MongoDB and DuckDB only.
Previous entries referencing PostgreSQL integer user_id were based on inferred schema — now superseded.

**business_id join rule (critical):**
- MongoDB: `business.business_id` = `"businessid_49"` → extract integer: `49`
- DuckDB: `review.business_ref` = `"businessref_34"` → extract integer: `34`
- Match on the integer. Do NOT attempt string equality — `"businessid_49" != "businessref_49"`.
- Resolver call: `resolve_join_key(val, "mongodb_business", "duckdb_review")`

**tip.user_id nullable:**
- `tip.user_id` contains NULL values. Always add `WHERE user_id IS NOT NULL` before joining tip to user.

**Date fields — not a join key but a known mismatch:**
- `checkin.date` (MongoDB): ISO format `"2011-03-18 21:32:32"` — but stored as a single comma-separated string of multiple timestamps.
- `review.date` (DuckDB): mixed formats — `"August 01, 2016 at 03:44 AM"`, `"29 May 2013, 23:01"`.
- `tip.date` (DuckDB): mixed formats — `"28 Apr 2016, 19:31"`, `"2013-12-04 02:46:01"`.
- `user.yelping_since` (DuckDB): mixed formats — `"15 Jan 2009, 16:40"`, `"2010-09-07 23:24:36"`.
- Rule: use `dateutil.parser.parse()` for ALL date fields in this dataset. Never use strptime with a fixed format.

---

## General Rules (apply across datasets)

- Integer-to-prefixed-string is the most common mismatch pattern. The prefix varies per dataset — never assume it is `"USR-"` without confirming.
- Zero-padding varies: some datasets use `"CUST-00123"` (5-digit padded), others use `"CUST-123"` (no padding). The `pad_width` field in `FORMAT_REGISTRY` controls this.
- MongoDB ObjectId fields are never directly joinable to SQL integer keys — these require a separate lookup step, not a direct format conversion.

---

**Drivers:** Every new mismatch discovered must be added here AND to `FORMAT_REGISTRY` in `utils/join_key_resolver.py` AND logged in `kb/corrections/corrections_log.md` with the probe that surfaced it.

---

## Injection Test

**Test question:** The agent needs to join MongoDB `business.business_id` with DuckDB `review.business_ref`. What transformation is required and why can't it do a direct string equality join?

**Expected answer:** MongoDB stores the key as `"businessid_N"` and DuckDB stores it as `"businessref_N"`. The prefixes differ so string equality always returns zero rows. The agent must strip both prefixes to extract integer N and match on that. Call `resolve_join_key(val, "mongodb_business", "duckdb_review")` from `utils/join_key_resolver.py`.

**Test question 2:** A query starts from MongoDB `support_tickets` (containing `customer_id: "CUST-00423"`) and needs to look up PostgreSQL `transactions` (containing integer `customer_id: 423`). What does the agent need to do, and is this direction registered in `join_key_resolver.py`?

**Expected answer:** The agent must strip the `"CUST-"` prefix and parse the remaining zero-padded digits as an integer (423). This is the reverse direction (MongoDB → PostgreSQL) of the standard PostgreSQL → MongoDB rule. Per the General Rules in this glossary, both directions must be registered in `FORMAT_REGISTRY`. If only one direction is present, the reverse-direction join returns zero rows — a known failure mode documented in Probe 009 of the adversarial probe library.
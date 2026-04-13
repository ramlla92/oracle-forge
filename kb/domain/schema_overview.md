 # DAB Schema Overview

> KB v2 — Domain Layer | Oracle Forge
> Status: STUB — populate with actual schema as each dataset is loaded.
> Load this file at every session (listed in AGENT.md always-load).

---

## How to Use This File

For each dataset loaded, add an entry below following the template.
Pull schema details by running: `list_db` on each database, then `SELECT * LIMIT 3` on each table.

---

## Template

```
### [dataset_name]
Databases: [db1_name] ([system]) + [db2_name] ([system])
Domain: [what this dataset is about]

[db1_name]:
  [table_name]: [col1 (type)], [col2 (type)], ...

[db2_name]:
  [table_name]: [col1 (type)], [col2 (type)], ...

Join key: [col in db1] ↔ [col in db2] — [note any format difference]
```

---

## Datasets

### yelp
Databases: yelp_businessinfo (mongodb) + yelp_user (duckdb)
Domain: Business reviews, check-ins, user profiles, tips

yelp_businessinfo (MongoDB):
  business: business_id (str, "businessid_N"), name (str), review_count (int), is_open (int), attributes (dict), hours (dict), description (str)
  checkin: business_id (str, "businessid_N"), date (str — comma-separated multi-timestamp)

yelp_user (DuckDB):
  review: review_id (VARCHAR), user_id (VARCHAR, "userid_N"), business_ref (VARCHAR, "businessref_N"), rating (BIGINT), text (VARCHAR), date (VARCHAR — mixed formats)
  tip: user_id (VARCHAR, nullable), business_ref (VARCHAR, "businessref_N"), text (VARCHAR), date (VARCHAR — mixed formats), compliment_count (BIGINT)
  user: user_id (VARCHAR, "userid_N"), name (VARCHAR), review_count (BIGINT), yelping_since (VARCHAR — mixed formats), elite (VARCHAR — comma-separated years)

Join key: MongoDB business.business_id ("businessid_N") ↔ DuckDB review.business_ref ("businessref_N")
  — strip both prefixes, match on integer N. No direct string equality join possible.

Date warning: All date fields are VARCHAR with mixed formats. Always use dateutil.parser, never strptime with fixed format.
Null warning: tip.user_id contains NULL values. Filter WHERE user_id IS NOT NULL before joining.

---

## All 12 DAB Datasets — Database Type Map

Source: `agent/database_router.py DATASET_DB_MAP` (confirmed from DAB db_config.yaml files).
Use this to route queries to the correct database type before generating any query.

| Dataset | DB 1 | Type | DB 2 | Type |
|---------|------|------|------|------|
| yelp | yelp_businessinfo | mongodb | yelp_user | duckdb |
| agnews | articles_database | mongodb | metadata_database | sqlite |
| bookreview | books_database | postgresql | review_database | sqlite |
| googlelocal | business_database | postgresql | review_database | sqlite |
| music_brainz | tracks_database | sqlite | sales_database | duckdb |
| stockindex | indexinfo_database | sqlite | indextrade_database | duckdb |
| stockmarket | stockinfo_database | sqlite | stocktrade_database | duckdb |
| pancancer | clinical_database | postgresql | molecular_database | duckdb |
| deps_dev | package_database | sqlite | project_database | duckdb |
| github_repos | metadata_database | sqlite | artifacts_database | duckdb |
| patents | publication_database | sqlite | CPCDefinition_database | postgresql |
| crmarenapro | core_crm (sqlite), sales_pipeline (duckdb), support (postgresql), products_orders (sqlite), activities (duckdb), territory (sqlite) | — | 6 databases | — |

**crmarenapro note:** 6 databases across 3 DB types. Known issue: TRIM() all ID fields before
joining — 25% of IDs have trailing spaces. This is documented in `kb/AGENT.md` Critical Rules.

**bookreview note:** Strip `bid_` / `bref_` prefixes before joining `book_id` to `purchase_id`.
This is documented in `kb/AGENT.md` Critical Rules.

**Schema stubs for non-Yelp datasets:** Add confirmed schema entries here as each dataset is
loaded and introspected. Follow the Yelp template above.

---

## Injection Test

**Test question:** A query asks "How many businesses in Nevada have at least 10 reviews?" An agent using this schema file routes the query only to DuckDB. What is wrong, and what should the agent do instead?

**Expected answer:** Wrong — Nevada (state filter) and review_count are stored in the MongoDB business collection (yelp_businessinfo), not in DuckDB (yelp_user). DuckDB's review table has individual review rows, not per-business counts or location data. The correct routing is: (1) query MongoDB business collection with {$match: {description: {$regex: ", NV,"}, review_count: {$gte: 10}}}, then (2) return the count directly from MongoDB without needing a DuckDB sub-query.

**Test question 2:** An agent tries `SELECT * FROM business WHERE ...` against DuckDB. What error will it get and why?

**Expected answer:** `Catalog Error: Table with name business does not exist!` — DuckDB (yelp_user) contains only review, user, and tip tables. The business collection is in MongoDB (yelp_businessinfo). Any query needing business attributes, categories, WiFi, parking, is_open, or location must go to MongoDB.

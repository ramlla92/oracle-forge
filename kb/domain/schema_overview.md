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

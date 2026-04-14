# DuckDB Failure Modes in Multi-Database Agent Contexts

Here is how this works.

DuckDB is one of the four database systems in DAB. It is an in-process analytical SQL engine optimised for columnar, OLAP-style queries — rolling averages, window functions, large aggregations. It is not a transactional database. Agents that treat DuckDB like PostgreSQL will produce wrong results or execution errors.

**Failure Mode 1 — Wrong database routed.** The agent sends an analytical query (rolling averages, percentiles, time-series aggregations) to PostgreSQL instead of DuckDB. PostgreSQL can run window functions but is slower and may not have the pre-aggregated time-series tables that DAB's DuckDB datasets contain. Result: query runs but returns wrong data because the tables don't exist in PostgreSQL, or the agent silently queries the wrong dataset.

**Failure Mode 2 — SQL dialect mismatch.** DuckDB supports analytical SQL extensions not available in standard PostgreSQL — for example `QUALIFY`, `PIVOT`, `UNPIVOT`, and certain `ASOF JOIN` syntax. If the agent generates standard SQL and executes it against DuckDB, some queries fail with syntax errors. The reverse is also true: DuckDB-specific syntax sent to PostgreSQL will fail.

**Failure Mode 3 — Schema assumption mismatch.** DuckDB datasets in DAB are often pre-aggregated or structured for analytical access — wide tables with many columns, denormalised. Agents trained on normalised PostgreSQL schemas may attempt joins that are unnecessary (the data is already joined) or miss columns that exist only in DuckDB.

**Failure Mode 4 — MCP tool not called.** The agent generates a DuckDB-compatible query but calls the PostgreSQL MCP tool instead of the DuckDB tool defined in `tools.yaml`. This is a tool selection error, not a query error. The query trace will show the correct SQL but the wrong tool invocation.

**Detection:** Check the query trace. If a DuckDB analytical query (window function, rolling average, time-series) was routed through `postgres_query` instead of `duckdb_query`, this is Failure Mode 4. If the tool was correct but results are wrong, check for schema assumption mismatch.

**Fix direction:** Add explicit routing rules to AGENT.md: analytical queries involving rolling windows, percentiles, or time-series must route to DuckDB. Ensure `tools.yaml` defines a `duckdb_query` tool with a clear description that the agent's tool-selection logic can match.

---

**Failure Mode 5 — Non-existent table queried (wrong_table).** The agent generates SQL referencing a table that does not exist in DuckDB. For the Yelp dataset, DuckDB (yelp_user) contains ONLY three tables: `review`, `tip`, `user`. There is NO `business` table and NO `attributes` table in DuckDB. Business data (name, city, state, categories, WiFi, parking, is_open, attributes) lives exclusively in MongoDB (yelp_businessinfo). Queries that join or filter on `business` in DuckDB will always fail with `Catalog Error: Table with name business does not exist`.

**Detection:** Error message contains `Catalog Error: Table with name X does not exist`. Check which table name X is — if it is `business` or `attributes`, this is Failure Mode 5.

**Fix direction:** Route all business attribute lookups to MongoDB. Retrieve `business_ref` IDs from DuckDB first if needed, then resolve business details via MongoDB aggregation pipeline.

---

**Failure Mode 6 — Fixed strptime format fails on mixed-format date fields.** DuckDB date columns in the Yelp dataset (`review.date`, `tip.date`, `user.yelping_since`) are VARCHAR with at least two known format variants:
- `'August 01, 2016 at 03:44 AM'` (format: `'%B %d, %Y at %I:%M %p'`)
- `'29 May 2013, 23:01'` (format: `'%d %B %Y, %H:%M'`)

Using `strptime()` with any single fixed format raises `Invalid Input Error: Could not parse string` on rows that use the other format.

**Detection:** Error message contains `Invalid Input Error: Could not parse string "X" according to format specifier`.

**Fix direction:** Always use `COALESCE(TRY_STRPTIME(date_col, '%B %d, %Y at %I:%M %p'), TRY_STRPTIME(date_col, '%d %B %Y, %H:%M'))` for date parsing. For year-only filtering, use `LIKE '%2018%'` — it is safe across all format variants and avoids parsing entirely.

---

**Injection test question:** An agent runs a 30-day rolling average query and gets a syntax error. The query trace shows it called `postgres_query`. Which DuckDB failure mode is this and what is the fix?

**Expected answer:** This is Failure Mode 4 — the correct MCP tool was not called. The agent routed an analytical query to the PostgreSQL tool instead of the DuckDB tool. The fix is to add a routing rule to AGENT.md specifying that rolling window and time-series queries must invoke `duckdb_query`, and to verify the DuckDB tool description in `tools.yaml` is specific enough for the agent's tool-selection logic to match it.

---

**Injection test question 2:** An agent generates `SELECT * FROM business WHERE city = 'Phoenix'` against DuckDB. What failure mode is this and what is the correct approach?

**Expected answer:** Failure Mode 5 — non-existent table. DuckDB (yelp_user) has no `business` table. Business data is in MongoDB (yelp_businessinfo). The correct approach is to query MongoDB with `{$match: {description: {$regex: "Phoenix", $options: "i"}}}` against the `business` collection.

---

**Injection test question 3:** An agent filters DuckDB reviews with `WHERE strptime(date, '%B %d, %Y at %I:%M %p') >= '2016-01-01'` and gets `Invalid Input Error`. What failure mode is this and what is the fix?

**Expected answer:** Failure Mode 6 — fixed strptime format fails on mixed-format date fields. The `review.date` column has at least two format variants. The fix is to use `COALESCE(TRY_STRPTIME(date, '%B %d, %Y at %I:%M %p'), TRY_STRPTIME(date, '%d %B %Y, %H:%M'))` for full date parsing, or `LIKE '%2016%'` for year-only filtering.
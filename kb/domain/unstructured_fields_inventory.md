# Unstructured Fields Inventory

Here is how this works.

This document lists every field across DAB datasets that contains unstructured or semi-structured text requiring an extraction step before it can be used in a calculation or aggregation. Querying these fields without extraction produces wrong answers — the agent either returns raw text or aggregates over the wrong unit.

**The rule:** Any query that asks for a count, average, classification, or comparison involving a field listed here must include an extraction step before the aggregation step. The extraction step converts free text into a structured fact (a label, a number, a boolean) that can then be counted or grouped.

**Format per entry:** Dataset | Database | Table/Collection | Field | Content type | Required extraction | Example query that needs extraction

---

## Yelp Dataset

**Confirmed 2026-04-11** — all entries verified against live loaded data.

| Field | Database | Table | Content Type | Required Extraction | Example Query |
|-------|----------|-------|-------------|--------------------|--------------------|
| `review.text` | DuckDB | review | Free-form customer review prose | Sentiment classification, topic detection | "How many reviews mention slow service negatively?" |
| `tip.text` | DuckDB | tip | Free-form short tip prose | Sentiment classification, keyword extraction | "How many tips mention parking?" |
| `business.description` | MongoDB | business | Free-form business description | Entity/attribute extraction if structured facts needed | "Which businesses describe themselves as family-friendly?" |
| `checkin.date` | MongoDB | checkin | Comma-separated multi-timestamp string | Split on `","` before counting or filtering by date | "How many check-ins did business X have in 2013?" |
| `user.elite` | DuckDB | user | Comma-separated year string e.g. `"2010,2011,2012"` | Split on `","` before filtering or counting elite years | "How many users were elite in 2015?" |
| `review.date` | DuckDB | review | VARCHAR with mixed date formats | `dateutil.parser.parse()` before any date comparison | "How many reviews were posted in Q3 2021?" |
| `tip.date` | DuckDB | tip | VARCHAR with mixed date formats | `dateutil.parser.parse()` before any date comparison | "How many tips were posted last year?" |
| `user.yelping_since` | DuckDB | user | VARCHAR with mixed date formats | `dateutil.parser.parse()` before any date comparison | "How many users joined before 2012?" |

**Note on `checkin.date`:** This is the most dangerous field. It looks like a single date but is actually a comma-separated string of multiple timestamps in one document field. A query that filters `WHERE date > '2013-01-01'` on the raw field will fail or return wrong results. The agent must split the string into individual timestamps before any date filtering or count aggregation.

**Note on `user.elite`:** Stored as a comma-separated string `"2010,2011,2012,2013"`, not an array. `WHERE elite LIKE '%2015%'` will work for simple year presence checks but will false-positive on `"2015"` appearing inside `"20150"` — use `LIKE '%,2015,%' OR elite LIKE '2015,%' OR elite LIKE '%,2015'` for exact year matching, or split and unnest.

---

## General Extraction Patterns

**Sentiment classification:** Use a secondary LLM call or a lightweight classifier. Do not use keyword matching alone — "not bad" is positive, "wait was fine" may be neutral. The extraction result should be a label (`positive`, `negative`, `neutral`) stored as a structured intermediate before counting.

**Topic detection:** Extract whether a specific topic (e.g. "wait time", "staff friendliness") is mentioned. Return a boolean per review, then count the trues.

**Keyword normalisation:** Some fields contain inconsistent spellings or abbreviations. Normalise before comparing (e.g. `"NY"` vs `"New York"` in location fields).

---

**Drivers:** When a query fails because the agent aggregated over raw text, add the field here and log the failure in `kb/corrections/corrections_log.md`.

---

## Injection Test

**Test question:** A query asks for the number of check-ins business `businessid_5` had in 2013. Which field requires extraction, what is the extraction step, and why does a simple date filter fail?

**Expected answer:** `checkin.date` in MongoDB requires splitting — it is a single comma-separated string of multiple timestamps, not a single date value. A simple `WHERE date > '2013-01-01'` filter on the raw field compares the entire multi-timestamp string as one value, which fails or returns wrong results. The agent must split the string on `","`, parse each individual timestamp with `dateutil.parser`, then filter and count.

**Test question 2:** A query asks "how many reviews for Italian restaurants mention slow service negatively?" An agent runs `SELECT COUNT(*) FROM review WHERE LOWER(text) LIKE '%slow%'`. What is wrong with this approach, and what extraction step should the agent use instead?

**Expected answer:** The LIKE approach over-counts — reviews saying "not slow", "surprisingly fast, not slow at all", or "wait was short" all match the keyword but are neutral or positive. `review.text` is listed in this inventory as requiring sentiment classification before aggregation. The correct approach: use `response_synthesizer.extract_from_text()` to classify each matching review as positive/negative/neutral on the "slow service" topic, then count only the negative-classified rows. Keyword matching alone on any field in this inventory produces wrong results.
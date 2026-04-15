# Yelp Anti-Pattern Reference

**KB v2 — Domain Layer | Oracle Forge**
**Status:** CONFIRMED — all patterns observed in live benchmark runs 2026-04-14.
**Load when:** Diagnosing a wrong answer or reviewing a generated query before execution.

---

## Quick Reference Table

| # | Wrong Pattern | Why It Fails | Correct Pattern | Queries Affected |
|---|--------------|--------------|-----------------|-----------------|
| AP-01 | `AVG(review_count)` used as rating | `review_count` is total reviews written, not a star score. Returns values like 45.2 instead of 3.5 | `AVG(rating)` from DuckDB `review` table | Q1, Q2, Q4, Q5, Q6 |
| AP-02 | State extracted via `$indexOfBytes` on description | Finds first `", "` which may be inside the street address. Returns wrong position for cities like "St. Louis, MO" | Split on `", this"`, take last 2 chars of left part | Q2, Q5 |
| AP-03 | State extracted via `$regexFind` | Returns an object `{match, idx, captures}`, not a string. Crashes `$split` with type error | `$substr` + `$strLenCP` after split-on-", this" | Q2, Q5 |
| AP-04 | DuckDB queried for state/city/category | DuckDB tables (`review`, `tip`, `user`) have no location or category columns | MongoDB `business.description` is the only source | Q2, Q4, Q5 |
| AP-05 | DuckDB `business` table referenced | Table does not exist. Fails with `Catalog Error: Table with name business does not exist` | MongoDB `business` collection for all business metadata | Q3, Q4, Q6, Q7 |
| AP-06 | MongoDB parking filter without DuckDB ref filter | DuckDB counts all 2018 reviews (67) instead of only parking businesses (35) | DuckDB must include `WHERE business_ref IN (parking refs from MongoDB)` | Q3 |
| AP-07 | Category extracted from DuckDB `tip.text` or `review.text` | Free text — unreliable. "I love their Restaurants" is not a category tag | MongoDB `business.description` split on "offers " then ", " | Q4, Q7 |
| AP-08 | `$lookup` used in MongoDB pipeline | Yelp has only 2 collections (`business`, `checkin`). DuckDB tables are unreachable from MongoDB | Run MongoDB and DuckDB as separate queries, join in agent | Q2, Q3, Q5 |
| AP-09 | `business_ref` returned as the final answer | `"businessref_9"` is an internal key. Validate.py checks for the business name string | Reverse-lookup MongoDB `business.name` using `businessid_9` | Q6 |
| AP-10 | Single `strptime` format on date fields | Date columns have 3 mixed formats. Single format fails on ~30% of rows with `Invalid Input Error` | `COALESCE(TRY_STRPTIME(col, fmt1), TRY_STRPTIME(col, fmt2), TRY_STRPTIME(col, fmt3))` | Q3, Q6, Q7 |
| AP-11 | MongoDB `review_count` used for review count ranking | Denormalized count may differ from actual DuckDB review rows. Also ignores date filters | `COUNT(*) FROM review WHERE business_ref IN (...)` in DuckDB | Q2, Q7 |
| AP-12 | Top-k category from MongoDB count only | MongoDB has 100 docs (sample). Category ranking from sample ≠ full dataset ranking | Use DuckDB review counts to rank, MongoDB only for category name lookup | Q4, Q7 |
| AP-13 | WiFi filter using boolean `true` | `attributes.WiFi` is a string. `{$match: {"attributes.WiFi": true}}` returns zero results | `{$match: {"attributes.WiFi": {$nin: [null, "u'no'", "no", "None", "'no'"]}}}` | Q5 |
| AP-14 | Credit card filter using boolean `true` | `attributes.BusinessAcceptsCreditCards` is string `"True"` or `"False"` | `{$match: {"attributes.BusinessAcceptsCreditCards": "True"}}` | Q4 |
| AP-15 | `$split` on `$description` without `$ifNull` | Some documents have `description: null`. `$split` on null crashes with `NoneType` error | `{"$split": [{"$ifNull": ["$description", ""]}, "offers "]}` | Q2, Q4, Q5, Q7 |

---

## Detailed Explanations for High-Impact Patterns

### AP-01: review_count ≠ rating

This is the most common wrong-answer pattern. Two different fields share similar names:

- `MongoDB business.review_count` = `81` — how many reviews this business has ever received (a count)
- `DuckDB user.review_count` = `376` — how many reviews this user has ever written (a count)
- `DuckDB review.rating` = `4` — the actual 1–5 star score for one review

`AVG(review_count)` returns something like `45.2`. The correct answer for "average rating" is always `AVG(rating)` from the `review` table.

### AP-06: Missing ref filter in DuckDB (Q3 pattern)

The parking filter lives in MongoDB. DuckDB has no parking data. The correct flow is:

1. MongoDB returns 49 parking business_ids
2. Convert to 49 business_refs
3. DuckDB: `COUNT(DISTINCT business_ref) WHERE business_ref IN (49 refs) AND year = 2018`

If step 3 omits the `IN (...)` filter, DuckDB counts all businesses with 2018 reviews = 67. The correct answer is 35. This pattern applies to any query where MongoDB provides an attribute filter and DuckDB provides a date/rating filter.

### AP-09: business_ref as final answer (Q6 pattern)

DuckDB returns `businessref_9`. The validate.py for Q6 checks for `"Coffee House Too Cafe"` in the answer string. Returning `businessref_9` fails validation even though the underlying data is correct. Always do the reverse MongoDB lookup to get the human-readable name before synthesizing the answer.

### AP-12: Top-k category mismatch (Q4/Q7 pattern)

Our MongoDB sample has 100 documents. The full DAB dataset has more. Category rankings from the 100-doc sample may not match the full dataset. For Q4, our sample shows "Shopping" as top category but the ground truth is "Restaurant". The correct approach is to use DuckDB review counts (which cover all reviews) to rank, and MongoDB only to resolve category names.

---

## Injection Test

**Question:** An agent returns `"businessref_9"` as the answer to "which business had the highest rating?" and the validate.py fails. Which anti-pattern is this, and what should the agent have done?

**Expected answer:** AP-09 — `business_ref` returned as final answer. The agent should have converted `businessref_9` → `businessid_9` and done a MongoDB lookup to retrieve `business.name = "Coffee House Too Cafe"`. The final answer must contain the human-readable business name, not the internal key.

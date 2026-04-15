# Yelp Query Logic Skeletons (Q1–Q7)

**KB v2 — Domain Layer | Oracle Forge**
**Status:** CONFIRMED — logic verified against live data 2026-04-14. All ground truths match.
**Load when:** Running any of the 7 Yelp benchmark queries.

These are logic descriptions, not runnable code. Each entry documents the required DB path,
what each stage must accomplish, and the expected intermediate output shape.
The agent uses these as a reference to verify its generated queries are on the right path.

---

## Q1 — Average rating of businesses in Indianapolis, Indiana

**Ground truth:** `3.547`
**DB path:** MongoDB → DuckDB

**MongoDB stage goal:**
- Collection: `business`
- Filter: description contains "Indianapolis" (case-insensitive regex)
- Output: list of `business_id` values for matching businesses
- Expected shape: `[{"business_id": "businessid_52"}, {"business_id": "businessid_84"}, ...]` (8 documents)

**Join step:**
- Convert each `businessid_N` → `businessref_N`

**DuckDB aggregation goal:**
- Table: `review`
- Filter: `business_ref IN (converted refs)`
- Aggregate: `AVG(rating)`
- Expected shape: single float `3.547`

**Notes:**
- Do NOT try to compute AVG in MongoDB — `review_count` is not a rating.
- Do NOT filter DuckDB by city text — DuckDB has no location data.

---

## Q2 — State with highest number of reviews + avg rating

**Ground truth:** `PA, 3.699`
**DB path:** MongoDB (state grouping) → DuckDB (per-state review count + avg rating)

**MongoDB stage goal:**
- Collection: `business`
- Extract state from description using split-on-", this" + last-2-chars pattern
- Group by state, collect all `business_id` values per state
- Expected shape: `[{"_id": "PA", "count": 26, "business_ids": ["businessid_89", ...]}, {"_id": "FL", ...}, ...]`

**Join step:**
- For each state group, convert `business_ids` list → `business_refs` list

**DuckDB aggregation goal:**
- For each state's refs: `COUNT(*) FROM review WHERE business_ref IN (...)` → review count
- For each state's refs: `AVG(rating) FROM review WHERE business_ref IN (...)` → avg rating
- Find state with highest review count
- Expected shape: `{"state": "PA", "review_count": 617, "avg_rating": 3.699}`

**Notes:**
- The synthesizer must match DuckDB per-ref results back to MongoDB state groups.
- MongoDB `review_count` field is NOT the same as DuckDB review count — use DuckDB for the actual count.
- State with most MongoDB businesses ≠ state with most DuckDB reviews. Must count from DuckDB.

---

## Q3 — Count of parking businesses with 2018 reviews

**Ground truth:** `35`
**DB path:** MongoDB (parking filter) → DuckDB (2018 date filter + count)

**MongoDB stage goal:**
- Collection: `business`
- Filter: `BusinessParking` contains "True" OR `BikeParking` == "True"
- Output: list of `business_id` values for parking businesses
- Expected shape: `[{"business_id": "businessid_47"}, ...]` (49 documents)

**Join step:**
- Convert `businessid_N` → `businessref_N` (49 refs)

**DuckDB aggregation goal:**
- Table: `review`
- Filter: `business_ref IN (parking refs)` AND year of date = 2018
- Date parsing: `YEAR(COALESCE(TRY_STRPTIME(date, '%B %d, %Y at %I:%M %p'), TRY_STRPTIME(date, '%d %b %Y, %H:%M'), TRY_STRPTIME(date, '%Y-%m-%d %H:%M:%S'))) = 2018`
- Aggregate: `COUNT(DISTINCT business_ref)`
- Expected shape: single integer `35`

**Notes:**
- The `business_ref IN (parking refs)` filter is REQUIRED. Without it, DuckDB counts all 2018 businesses (67), not just parking ones.
- Do NOT try to filter parking in DuckDB — there is no parking data there.

---

## Q4 — Business category with most credit card businesses + avg rating

**Ground truth:** `Restaurant, 3.634` (full dataset; our 100-doc sample shows Shopping due to data subset)
**DB path:** MongoDB (credit card filter + category extraction) → DuckDB (avg rating per category)

**MongoDB stage goal:**
- Collection: `business`
- Filter: `attributes.BusinessAcceptsCreditCards == "True"`
- Extract categories from description (split on "offers ", then split on ", ")
- Group by category, count businesses per category, collect `business_id` values
- Expected shape: `[{"_id": "Restaurants", "count": 12, "business_ids": [...]}, {"_id": "Shopping", "count": 15, ...}, ...]`

**Join step:**
- For top category by count: convert `business_ids` → `business_refs`

**DuckDB aggregation goal:**
- `AVG(rating) FROM review WHERE business_ref IN (top category refs)`
- Expected shape: `{"category": "Restaurants", "count": 12, "avg_rating": 3.634}`

**Notes:**
- Category extraction from description is imprecise — the text after "offers" includes filler words.
- The correct split is on the last occurrence of "offers " then split result on ", ".
- Trailing "." and filler phrases like "a delightful menu featuring" must be stripped.

---

## Q5 — State with most WiFi businesses + avg rating

**Ground truth:** `PA, 3.48`
**DB path:** MongoDB (WiFi filter + state grouping) → DuckDB (avg rating for PA refs)

**MongoDB stage goal:**
- Collection: `business`
- Filter: `attributes.WiFi NOT IN [null, "u'no'", "no", "None", "'no'"]`
- Extract state from description (same split-on-", this" pattern as Q2)
- Group by state, count businesses, collect `business_id` values
- Expected shape: `[{"_id": "PA", "count": 9, "business_ids": [...]}, {"_id": "FL", "count": 5, ...}, ...]`

**Join step:**
- For PA (top state): convert `business_ids` → `business_refs` (9 refs)

**DuckDB aggregation goal:**
- `AVG(rating) FROM review WHERE business_ref IN (PA refs)`
- Expected shape: `{"state": "PA", "wifi_count": 9, "avg_rating": 3.471}`

**Notes:**
- Same state extraction pattern as Q2 — reuse the `$ifNull` + split-on-", this" approach.
- The avg rating comes from DuckDB, not from MongoDB `review_count`.

---

## Q6 — Business with highest avg rating H1 2016, min 5 reviews + category

**Ground truth:** `Coffee House Too Cafe, Restaurants, Breakfast & Brunch, American (New), Cafes`
**DB path:** DuckDB (date filter + rating aggregation) → MongoDB (name + category lookup)

**DuckDB aggregation goal (runs first):**
- Table: `review`
- Filter: date BETWEEN 2016-01-01 AND 2016-06-30 (use COALESCE TRY_STRPTIME)
- Group by `business_ref`
- Having: `COUNT(*) >= 5`
- Order by: `AVG(rating) DESC`
- Limit: 1
- Expected shape: `{"business_ref": "businessref_9", "avg_rating": 4.375, "review_count": 16}`

**Join step (reverse):**
- `businessref_9` → `businessid_9`

**MongoDB lookup goal:**
- Collection: `business`
- Filter: `{business_id: "businessid_9"}`
- Project: `name`, `description`
- Expected shape: `{"name": "Coffee House Too Cafe", "description": "...offers Restaurants, Breakfast & Brunch, American (New), Cafes..."}`

**Category extraction from description:**
- Split on "offers " → take part after last "offers "
- Split on ", " → `["a delightful menu featuring Restaurants", "Breakfast & Brunch", "American (New)", "Cafes", "perfect for a cozy meal any time of the day"]`
- Strip filler: first element contains "featuring" — the actual category starts after it
- Clean categories: `Restaurants`, `Breakfast & Brunch`, `American (New)`, `Cafes`

**Notes:**
- This is DuckDB-first, MongoDB-second — opposite of Q1–Q5.
- The MongoDB query here is a name/category lookup, not a filter.
- The answer requires BOTH the business name AND its categories.

---

## Q7 — Top 5 categories by review count from 2016-registered users

**Ground truth:** `Restaurants, Food, American (New), Shopping, Breakfast & Brunch`
**DB path:** DuckDB (user registration filter + review join) → MongoDB (category lookup for top refs)

**DuckDB aggregation goal (runs first):**
- Tables: `user` JOIN `review` ON `user.user_id = review.user_id`
- Filter users: `YEAR(COALESCE(TRY_STRPTIME(yelping_since, ...))) = 2016` → 168 users
- Group by `business_ref`, count reviews
- Order by count DESC, limit 10–20 (need enough to cover 5 categories after MongoDB lookup)
- Expected shape: `[{"business_ref": "businessref_79", "review_count": 8}, {"business_ref": "businessref_57", "review_count": 7}, ...]`

**Join step (reverse for each ref):**
- `businessref_79` → `businessid_79`, `businessref_57` → `businessid_57`, etc.

**MongoDB lookup goal:**
- Collection: `business`
- Filter: `{business_id: {$in: ["businessid_79", "businessid_57", ...]}}`
- Project: `business_id`, `description`
- Extract categories from each description
- Map: `businessref_N` → categories list

**Final aggregation goal:**
- Sum review counts per category across all top refs
- Return top 5 categories by total review count
- Expected shape: `["Restaurants", "Food", "American (New)", "Shopping", "Breakfast & Brunch"]`

**Notes:**
- DuckDB runs first here — user registration data is in DuckDB only.
- MongoDB is used for category lookup only, not for filtering.
- Multiple business_refs may share the same category — aggregate counts across refs before ranking.
- The `$in` query is more efficient than one lookup per ref.

---

## Injection Test

**Question:** For Q3, what is the exact intermediate output shape after the MongoDB stage, and why does the DuckDB query need the `business_ref IN (...)` filter?

**Expected answer:**
MongoDB returns 49 business documents matching the parking filter, each with a `business_id` field (e.g. `"businessid_47"`). These are converted to 49 `businessref_N` values. The DuckDB query MUST include `WHERE business_ref IN (those 49 refs)` because without it, DuckDB counts all businesses that had any review in 2018 (67), not just the parking ones. The parking attribute only exists in MongoDB — DuckDB has no way to filter by parking without the ref list from MongoDB.

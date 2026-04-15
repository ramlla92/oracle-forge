# Yelp Field Map — Source of Truth

**KB v2 — Domain Layer | Oracle Forge**
**Status:** CONFIRMED — verified against live data 2026-04-14.
**Load when:** Any Yelp query. This is the authoritative field reference.

---

## How to Use This Document

For every concept a Yelp query needs, this document tells you:
- Which database and exact field/path to use
- What the value looks like in the actual data
- What NOT to use (anti-patterns that produce wrong answers)

---

## Concept: Rating (star score for a business)

**Source:** DuckDB `yelp_user` → table `review` → column `rating`
**Type:** BIGINT, values 1–5
**Sample:** `2`, `5`, `4`, `1`
**Aggregation:** `AVG(rating)` grouped by `business_ref`

**Anti-pattern — NEVER use `review_count` as rating:**
- MongoDB `business.review_count` = total number of reviews ever written (e.g. `81`)
- DuckDB `user.review_count` = total reviews written by that user (e.g. `376`)
- Neither is a star rating. `AVG(review_count)` returns a meaningless large number.
- Correct: `AVG(r.rating) FROM review r WHERE r.business_ref = ...`
- Wrong: `AVG(b.review_count)` or `AVG(u.review_count)`

---

## Concept: Review Count (how many reviews a business has)

**Source:** MongoDB `yelp_db` → collection `business` → field `review_count`
**Type:** int, e.g. `8`, `81`, `39`
**Note:** This is a denormalized count stored on the business document.
It is NOT the same as `COUNT(*) FROM review` — the two may differ slightly.
Use MongoDB `review_count` for quick filters (e.g. `{$match: {review_count: {$gte: 5}}}`).
Use DuckDB `COUNT(*) FROM review` when you need exact counts tied to a date range.

---

## Concept: State / City (business location)

**Source:** MongoDB `yelp_db` → collection `business` → field `description` (unstructured)
**There is NO separate `state` or `city` column.** Location is embedded in the description text.

**Description format (always):**
```
"Located at [address] in [City], [STATE_ABBR], this [type] offers ... [categories]."
```

**City extraction:** `{$match: {description: {$regex: "Indianapolis", $options: "i"}}}`

**State extraction (correct — split on ", this"):**
```json
{"$addFields": {"addr_part": {"$arrayElemAt": [{"$split": [{"$ifNull": ["$description", ""]}, ", this"]}, 0]}}},
{"$addFields": {"state": {"$substr": ["$addr_part", {"$subtract": [{"$strLenCP": "$addr_part"}, 2]}, 2]}}}
```
This takes the last 2 characters of the address portion (before ", this"), which is always the 2-letter state abbreviation.

**Anti-pattern — `$indexOfBytes` on description:**
- `$indexOfBytes` finds the first ", " which may be inside the street address (e.g. "9916 Clayton Rd, Suite 4 in St. Louis, MO").
- This returns the wrong position and extracts the wrong 2 characters.
- Correct: split on `", this"` and take last 2 chars of the left part.

**Anti-pattern — `$regexFind` for state:**
- `$regexFind` returns an object `{match, idx, captures}`, not a string.
- Passing that object to `$split` or `$substr` crashes with `$split requires a string`.
- Correct: use `$substr` + `$strLenCP` as shown above.

**Anti-pattern — querying DuckDB for state:**
- DuckDB tables (`review`, `tip`, `user`) have NO location columns.
- State/city data only exists in MongoDB `business.description`.

---

## Concept: Categories (business type)

**Source:** MongoDB `yelp_db` → collection `business` → field `description` (unstructured)
**There is NO separate `categories` column.** Categories are at the end of the description.

**Extraction pattern:**
```json
{"$addFields": {"categories": {"$split": [{"$arrayElemAt": [{"$split": [{"$ifNull": ["$description", ""]}, "offers "]}, 1]}, ", "]}}}
```
Split on `"offers "` to get everything after it, then split on `", "` to get individual categories.

**Sample output:**
- Description: `"...offers Restaurants, Breakfast & Brunch, American (New), Cafes."`
- After split: `["Restaurants", "Breakfast & Brunch", "American (New)", "Cafes."]`
- Note: last element may have a trailing `.` — strip it.

**Anti-pattern — parsing categories from DuckDB:**
- DuckDB has no category data. Do not attempt to extract categories from `review.text` or `tip.text`.
- Correct: always get categories from MongoDB `business.description`.

---

## Concept: WiFi

**Source:** MongoDB `yelp_db` → collection `business` → field `attributes.WiFi`
**Type:** string (NOT boolean)
**Values in data:** `"u'free'"`, `"u'no'"`, `"u'paid'"`, `"'free'"`, `"'no'"`, `null`

**Has WiFi filter:**
```json
{"$match": {"attributes.WiFi": {"$nin": [null, "u'no'", "no", "None", "'no'"]}}}
```

**Anti-pattern — boolean comparison:**
- `{$match: {"attributes.WiFi": true}}` returns zero results — values are strings not booleans.

---

## Concept: Parking (business or bike)

**Source:** MongoDB `yelp_db` → collection `business` → fields `attributes.BusinessParking` and `attributes.BikeParking`

**BusinessParking** — stored as Python repr string of a dict:
```
"{'garage': False, 'street': False, 'validated': False, 'lot': True, 'valet': False}"
```
Filter for ANY parking available: `{$match: {"attributes.BusinessParking": {$regex: "True"}}}`

**BikeParking** — stored as string `"True"` or `"False"`:
Filter: `{$match: {"attributes.BikeParking": "True"}}`

**Combined parking filter (either type):**
```json
{"$match": {"$or": [
  {"attributes.BusinessParking": {"$regex": "True"}},
  {"attributes.BikeParking": "True"}
]}}
```

**Anti-pattern — JSON parsing BusinessParking:**
- `JSON.parse(attributes.BusinessParking)` fails — it uses Python single-quote repr, not JSON.
- Correct: use `$regex: "True"` to detect any True value in the string.

---

## Concept: Credit Card Acceptance

**Source:** MongoDB `yelp_db` → collection `business` → field `attributes.BusinessAcceptsCreditCards`
**Type:** string `"True"` or `"False"` (NOT boolean)

**Filter:** `{$match: {"attributes.BusinessAcceptsCreditCards": "True"}}`

**Anti-pattern:** `{$match: {"attributes.BusinessAcceptsCreditCards": true}}` — boolean, returns zero results.

---

## Concept: Business Name (human-readable, for "which business" answers)

**Source:** MongoDB `yelp_db` → collection `business` → field `name`
**Type:** string, e.g. `"Coffee House Too Cafe"`, `"Breeze Blow Dry Bar"`

**When needed:** Q6-type queries ("which business received the highest rating") require the business name in the answer. DuckDB returns `business_ref` (e.g. `"businessref_9"`), not the name.

**Resolution path:**
1. DuckDB returns top `business_ref` (e.g. `businessref_9`)
2. Convert: `business_id = "businessid_" + ref.split("businessref_")[1]` → `"businessid_9"`
3. MongoDB lookup: `{$match: {business_id: "businessid_9"}}`, project `name` and `description`
4. Extract name from result: `"Coffee House Too Cafe"`

**Anti-pattern — returning business_ref as the answer:**
- `"businessref_9"` is an internal key, not a human-readable name.
- The validate.py for Q6 checks for the business name string — returning the ref fails validation.

---

## Injection Test

**Question:** A query asks "which business had the highest average rating in H1 2016 with at least 5 reviews?" What are the exact fields and databases needed, and what is the resolution path for the business name?

**Expected answer:**
1. DuckDB `review`: filter by date range using `COALESCE(TRY_STRPTIME(...))`, group by `business_ref`, `HAVING COUNT(*) >= 5`, order by `AVG(rating) DESC`, take top 1 → returns `businessref_9`
2. Convert: `businessref_9` → `businessid_9`
3. MongoDB `business`: `{$match: {business_id: "businessid_9"}}`, project `name` + `description` → returns `"Coffee House Too Cafe"` and categories from description
4. Answer: "Coffee House Too Cafe — Restaurants, Breakfast & Brunch, American (New), Cafes"

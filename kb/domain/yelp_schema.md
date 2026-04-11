# Yelp Dataset Schema (DAB Starting Dataset)

Here is how this works.

The Yelp dataset is the recommended starting point in DAB because it contains multi-source data,
nested JSON, missing values, and entity resolution challenges that mirror the full DAB problem
space in a contained form.

**Status:** CONFIRMED — schema verified by schema_introspector.py run on 2026-04-11 15:17 UTC.
All column names, types, and sample values below are from actual loaded data.

---

## yelp_businessinfo (MongoDB)

### business (~100 documents)

| Column | Type | Sample Values |
|--------|------|---------------|
| _id | ObjectId | 6859a000fe8b31cd7362e2ab |
| business_id | str | businessid_49, businessid_47, businessid_88 |
| name | str | Steps to Learning Montessori Preschool, Breeze Blow Dry Bar, Impact Guns |
| review_count | int | 8, 81, 39 |
| is_open | int | 1, 0 |
| attributes | dict | {'BusinessAcceptsCreditCards': 'True', 'WiFi': "u'no'"} |
| hours | dict | {'Monday': '0:0-0:0', 'Tuesday': '8:0-17:0'} |
| description | str | Free-text business description (unstructured field) |

**Critical:** `business_id` format is `"businessid_N"` (e.g. `"businessid_49"`). This is the
join key to DuckDB `review.business_ref` and `tip.business_ref`, which use format `"businessref_N"`.
The numeric suffix is the same — only the prefix differs. See join_keys_glossary.md.

**attributes field parsing (string values, not booleans):**
- `WiFi`: `"u'free'"` or `"u'yes'"` = has WiFi; `"u'no'"` = no WiFi; `null` = unknown
  - Filter for WiFi: `{$match: {"attributes.WiFi": {$nin: [null, "u'no'", "no", "None"]}}}`
- `BusinessParking`: stored as Python repr string e.g. `"{'garage': False, 'lot': True}"` — use regex, not JSON parse
  - Filter for any parking: `{$match: {"attributes.BusinessParking": {$regex: "True"}}}`
- `BikeParking`: string `"True"` or `"False"` — filter: `{$match: {"attributes.BikeParking": "True"}}`
- `BusinessAcceptsCreditCards`: string `"True"` or `"False"`

**description field parsing:**
Always follows: `"Located at [address] in [City], [STATE_ABBR], this [type] offers ... [Cat1], [Cat2]."`
- City filter: `{$match: {description: {$regex: "CityName", $options: "i"}}}`
- State filter: `{$match: {description: {$regex: ", PA,"}}}` (use 2-letter abbr with commas)
- Category extraction: split on `"offers "` then split on `", "`

### checkin (~90 documents)

| Column | Type | Sample Values |
|--------|------|---------------|
| _id | ObjectId | 6859a032fe8b31cd7362e310 |
| business_id | str | businessid_2, businessid_5, businessid_6 |
| date | str | Multiple ISO timestamps in a single string, comma-separated: "2011-03-18 21:32:32, 2011-07-03 19:19:32, ..." |

**Critical:** `checkin.date` is a single comma-separated string of multiple timestamps, not an
array and not a single date. Counting check-ins requires splitting this string before aggregating.

**Extraction rule for checkin.date:**
```python
timestamps = [t.strip() for t in doc["date"].split(",")]
# Then parse each with dateutil.parser.parse(t)
```
A `WHERE date > '2013-01-01'` filter on the raw field compares the entire multi-timestamp
string as one value — it will not work. Always split first.

---

## yelp_user (DuckDB)

### review (~2000 rows)

| Column | Type | Sample Values |
|--------|------|---------------|
| review_id | VARCHAR | reviewid_135, reviewid_1067, reviewid_871 |
| user_id | VARCHAR | userid_548, userid_213, userid_616 |
| business_ref | VARCHAR | businessref_34, businessref_89, businessref_82 |
| rating | BIGINT | 2, 5, 4 |
| useful | BIGINT | 0, 2, 0 |
| funny | BIGINT | 0, 0, 0 |
| cool | BIGINT | 0, 0, 0 |
| text | VARCHAR | Free-form review text (unstructured field) |
| date | VARCHAR | Mixed formats: "August 01, 2016 at 03:44 AM", "June 14, 2021 at 11:39 AM", "29 May 2013, 23:01" |

**Critical:** `review.date` is VARCHAR with at least two distinct formats:
- `"August 01, 2016 at 03:44 AM"` → matches `strptime('%B %d, %Y at %I:%M %p')`
- `"29 May 2013, 23:01"` → does NOT match the above format

Use `dateutil.parser.parse()` for all date parsing — never a fixed strptime format.
For DuckDB SQL: use `LIKE '%2018%'` for year-only checks, or `TRY_STRPTIME` with multiple formats.

### tip (~784 rows)

| Column | Type | Sample Values |
|--------|------|---------------|
| user_id | VARCHAR | None, userid_965, userid_909 |
| business_ref | VARCHAR | businessref_85, businessref_12, businessref_96 |
| text | VARCHAR | Free-form tip text (unstructured field) |
| date | VARCHAR | Mixed formats: "28 Apr 2016, 19:31", "2013-12-04 02:46:01", "23 Jun 2015, 00:22" |
| compliment_count | BIGINT | 0, 0, 0 |

**Critical:** `tip.user_id` contains NULL values (sample shows `None`). Always filter
`WHERE user_id IS NOT NULL` before joining on user_id.

### user (~1999 rows)

| Column | Type | Sample Values |
|--------|------|---------------|
| user_id | VARCHAR | userid_286, userid_1331, userid_1880 |
| name | VARCHAR | Todd, Patt, Norma |
| review_count | BIGINT | 376, 1028, 57 |
| yelping_since | VARCHAR | Mixed formats: "15 Jan 2009, 16:40", "13 Jul 2010, 15:42", "2010-09-07 23:24:36" |
| useful | BIGINT | 1373, 9050, 217 |
| funny | BIGINT | 723, 3249, 57 |
| cool | BIGINT | 639, 5929, 115 |
| elite | VARCHAR | Comma-separated year list: "2010,2011,2012,2013,2014" |

**Critical:** `user.yelping_since` is VARCHAR with mixed date formats. Use `dateutil.parser`.
`user.elite` is a comma-separated string, not an array — split before filtering or counting.

---

## Cross-Database Join Map

| Join | MongoDB field | DuckDB field | Format rule |
|------|--------------|--------------|-------------|
| Business → Reviews | `business.business_id` = `"businessid_N"` | `review.business_ref` = `"businessref_N"` | Strip prefix, match on integer N |
| Business → Tips | `business.business_id` = `"businessid_N"` | `tip.business_ref` = `"businessref_N"` | Strip prefix, match on integer N |
| Business → Checkins | `business.business_id` | `checkin.business_id` | Same collection — no cross-DB join needed |
| User → Reviews | `(no user collection in MongoDB)` | `user.user_id` = `review.user_id` = `"userid_N"` | Same DB, same format — direct join |

**There is no user table in MongoDB.** User data lives entirely in DuckDB (`yelp_user`).
The MongoDB database (`yelp_businessinfo`) contains only `business` and `checkin`.

---

## Unstructured Fields Requiring Extraction

| Field | Table | Issue |
|-------|-------|-------|
| `review.text` | DuckDB review | Free-form prose — sentiment/topic extraction required before aggregation |
| `tip.text` | DuckDB tip | Free-form prose — same as review.text |
| `business.description` | MongoDB business | Free-form prose — extract structured attributes if needed |
| `checkin.date` | MongoDB checkin | Comma-separated multi-timestamp string — split before counting check-ins |
| `user.elite` | DuckDB user | Comma-separated year string — split before filtering or counting elite years |

---

**Injection test question:** What is the join key format between MongoDB `business.business_id`
and DuckDB `review.business_ref`, and what transformation is required?

**Expected answer:** MongoDB stores it as `"businessid_N"` (prefix `businessid_`). DuckDB stores
it as `"businessref_N"` (prefix `businessref_`). The numeric suffix N is the same in both.
The agent must strip both prefixes, match on the integer N, and cannot do a direct string equality
join. Use `utils/join_key_resolver.py` with the `("mongodb", "duckdb")` rule.

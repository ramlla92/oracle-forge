# Oracle Forge — Domain Knowledge (Context Layer 2)

Here is how this works.

This is the file loaded by `ContextManager` as Layer 2 at every agent session start.
Path: `kb/domain/domain_knowledge.md`

It consolidates all domain knowledge the agent needs to answer DAB queries correctly:
business term definitions, attribute parsing rules, and dataset-specific conventions.
Without this file, the agent falls back to naive proxy definitions and fails DAB
Failure Category 4 (domain knowledge gap) silently.

---

## Yelp Dataset — Business Term Definitions

**Active business**
- Naive (wrong): any row in the `business` collection
- Correct: `is_open == 1` AND at least one review in the last 12 months
- Query: JOIN `business` → `review` on business_ref, filter `review.date` within 12 months

**High-rated business**
- Naive (wrong): `rating >= 4` on any review
- Correct: business with average `rating >= 4` across reviews AND `review_count >= 10`
- Query: GROUP BY business_ref, HAVING AVG(rating) >= 4 AND COUNT(*) >= 10

**Recent review**
- Naive (wrong): any row in the `review` table
- Correct: review with `date` within the last 90 days relative to query date
- Query: parse `review.date` with dateutil.parser, filter to last 90 days

**Repeat customer**
- Naive (wrong): user with more than one review total
- Correct: user who reviewed businesses in the same category more than once
- Query: requires category extraction from `business.description`, then GROUP BY user_id + category

---

## Yelp Dataset — MongoDB Attribute Parsing Rules

The `business.attributes` field is a dict stored as a MongoDB document.
Values are strings, not booleans. Parse them as follows:

**WiFi**
- Has WiFi: `attributes.WiFi` is NOT in `[null, "u'no'", "no", "None"]`
- Has free WiFi: `attributes.WiFi` == `"u'free'"` or `"u'yes'"`
- No WiFi: `attributes.WiFi` == `"u'no'"`
- MongoDB filter: `{$match: {"attributes.WiFi": {$nin: [null, "u'no'", "no", "None"]}}}`

**BusinessParking**
- Stored as a string representation of a dict: `"{'garage': False, 'lot': True, 'street': False}"`
- To find ANY parking available: `{$match: {"attributes.BusinessParking": {$regex: "True"}}}`
- Do NOT attempt to parse as JSON — it uses Python repr format with single quotes

**BikeParking**
- Stored as string `"True"` or `"False"` (not boolean)
- Filter: `{$match: {"attributes.BikeParking": "True"}}`

**BusinessAcceptsCreditCards**
- Stored as string `"True"` or `"False"`
- Filter: `{$match: {"attributes.BusinessAcceptsCreditCards": "True"}}`

---

## Yelp Dataset — Description Field Parsing Rules

`business.description` is a free-text field that always follows this pattern:
`"Located at [address] in [City], [STATE_ABBR], this [type] offers ... [Category1], [Category2]."`

**City filtering** (e.g. "businesses in Indianapolis"):
```
{$match: {description: {$regex: "Indianapolis", $options: "i"}}}
```

**State filtering** (e.g. "businesses in Pennsylvania"):
```
{$match: {description: {$regex: ", PA,"}}}
```
Use the 2-letter state abbreviation with surrounding commas to avoid partial matches.

**Category extraction:**
Categories are listed at the end of the description after "offers".
Extract with:
```
{"$addFields": {"categories": {"$split": [{"$arrayElemAt": [{"$split": ["$description", "offers "]}, 1]}, ", "]}}}
```

---

## Yelp Dataset — Date Parsing Rules

All date fields in this dataset are VARCHAR with mixed formats. Never use strptime
with a fixed format string — it will fail on at least one format variant.

| Field | Database | Known formats | Rule |
|-------|----------|---------------|------|
| `review.date` | DuckDB | `"August 01, 2016 at 03:44 AM"`, `"29 May 2013, 23:01"` | `dateutil.parser.parse()` |
| `tip.date` | DuckDB | `"28 Apr 2016, 19:31"`, `"2013-12-04 02:46:01"` | `dateutil.parser.parse()` |
| `user.yelping_since` | DuckDB | `"15 Jan 2009, 16:40"`, `"2010-09-07 23:24:36"` | `dateutil.parser.parse()` |
| `checkin.date` | MongoDB | `"2011-03-18 21:32:32, 2011-07-03 19:19:32, ..."` | Split on `","` first, then parse each |

For DuckDB SQL year extraction use: `EXTRACT(year FROM strptime(date, '%B %d, %Y at %I:%M %p'))`
or safer: `CAST(SPLIT_PART(date, ' ', -1) AS INTEGER)` for year-only queries,
or use `LIKE '%2018%'` for simple year presence checks.

---

## General Cross-Dataset Terms

**Churn** (retail, telecom)
- Correct: customer has not purchased/used service within inactivity window
- Retail default: 90 days. Telecom default: 30 days.
- Never defined by account closure or status field alone — status fields are stale

**Active account** (finance, telecom)
- Correct: account with at least one transaction in the last 30 days
- NOT equivalent to `status == "active"` — status fields are frequently not updated

**Fiscal quarter**
- Do NOT assume calendar quarters (Jan–Mar = Q1) unless schema confirms it
- Check for a `fiscal_calendar` table or dataset README before assuming

---

## Yelp Dataset — Live Join Resolution (How the Agent Actually Does It)

The agent resolves the `businessid_N` ↔ `businessref_N` join inline in `agent_core._extract_business_refs()`:

```python
# MongoDB returns: business_id = "businessid_49"
# DuckDB expects:  business_ref = "businessref_49"
if bid.startswith("businessid_"):
    n = bid.split("businessid_", 1)[1]
    refs.append(f"businessref_{n}")
```

This is the live implementation. `utils/join_key_resolver.py` provides the same
logic as a reusable utility for testing and manual use — but the agent uses the
inline version in `agent_core.py`. Both must stay in sync.

---

**Injection test question:** A query asks for "active businesses in Las Vegas with WiFi."
What are the three domain rules the agent must apply, and which fields/collections are involved?

**Expected answer:**
1. "Active" = `is_open == 1` AND reviewed in last 12 months — requires JOIN to DuckDB review table
2. "Las Vegas" filter = `{$match: {description: {$regex: "Las Vegas", $options: "i"}}}` on MongoDB business.description
3. "WiFi" = `attributes.WiFi` NOT IN `[null, "u'no'", "no", "None"]` on MongoDB business.attributes
All three filters apply to the MongoDB `business` collection before the cross-DB join to DuckDB.

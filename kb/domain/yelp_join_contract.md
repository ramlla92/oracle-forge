# Yelp Join Key Contract

**KB v2 — Domain Layer | Oracle Forge**
**Status:** CONFIRMED — verified against live data 2026-04-14.
**Load when:** Any Yelp query that crosses MongoDB and DuckDB.

---

## Canonical Mapping

| MongoDB field | DuckDB field | Format | Normalization rule |
|---------------|-------------|--------|--------------------|
| `business.business_id` | `review.business_ref` | `"businessid_N"` ↔ `"businessref_N"` | Strip prefix, match on integer N, rebuild target prefix |
| `business.business_id` | `tip.business_ref` | `"businessid_N"` ↔ `"businessref_N"` | Same rule |
| *(no user in MongoDB)* | `review.user_id` | `"userid_N"` | DuckDB-only — no cross-DB join needed |
| *(no user in MongoDB)* | `user.user_id` | `"userid_N"` | DuckDB-only — no cross-DB join needed |

**There is no PostgreSQL in the Yelp dataset.** MongoDB + DuckDB only.

---

## Normalization Rules

**MongoDB → DuckDB (forward direction):**
```
"businessid_49" → strip "businessid_" → "49" → prepend "businessref_" → "businessref_49"
```

**DuckDB → MongoDB (reverse direction):**
```
"businessref_49" → strip "businessref_" → "49" → prepend "businessid_" → "businessid_49"
```

**Key property:** The integer suffix N is identical in both systems. Only the prefix differs.

**Direct string equality always returns zero rows:**
```
"businessid_49" == "businessref_49"  →  FALSE
```

---

## Good Join vs Bad Join Examples

### Good Join — MongoDB first, DuckDB filtered by refs

**Step 1 — MongoDB returns business_ids:**
```json
[
  {"$collection": "business"},
  {"$match": {"description": {"$regex": "Indianapolis", "$options": "i"}}},
  {"$project": {"business_id": 1}}
]
```
Returns: `[{"business_id": "businessid_52"}, {"business_id": "businessid_84"}, ...]`

**Step 2 — Convert in agent_core._extract_business_refs():**
```python
"businessid_52" → "businessref_52"
"businessid_84" → "businessref_84"
```

**Step 3 — DuckDB filtered to those refs:**
```sql
SELECT AVG(rating)
FROM review
WHERE business_ref IN ('businessref_52', 'businessref_84', 'businessref_76', ...)
```
Result: `3.547` ✓

---

### Bad Join — raw string equality (always zero rows)

```sql
-- WRONG: direct join on mismatched prefixes
SELECT AVG(r.rating)
FROM review r
JOIN business b ON r.business_ref = b.business_id
WHERE b.description LIKE '%Indianapolis%'
```
This fails because `"businessref_52" != "businessid_52"`. Zero rows returned.

---

### Good Join — DuckDB first, MongoDB reverse lookup

**Step 1 — DuckDB returns top business_ref:**
```sql
SELECT business_ref, AVG(rating) AS avg_r, COUNT(*) AS cnt
FROM review
WHERE COALESCE(TRY_STRPTIME(date, '%B %d, %Y at %I:%M %p'),
               TRY_STRPTIME(date, '%d %b %Y, %H:%M'),
               TRY_STRPTIME(date, '%Y-%m-%d %H:%M:%S'))
      BETWEEN '2016-01-01' AND '2016-06-30'
GROUP BY business_ref
HAVING COUNT(*) >= 5
ORDER BY avg_r DESC
LIMIT 1
```
Returns: `[{"business_ref": "businessref_9", "avg_r": 4.375, "cnt": 16}]`

**Step 2 — Convert reverse:**
```python
"businessref_9" → "businessid_9"
```

**Step 3 — MongoDB name lookup:**
```json
[
  {"$collection": "business"},
  {"$match": {"business_id": "businessid_9"}},
  {"$project": {"name": 1, "description": 1}}
]
```
Returns: `{"name": "Coffee House Too Cafe", "description": "...offers Restaurants, Breakfast & Brunch, American (New), Cafes."}` ✓

---

### Bad Join — attempting cross-DB SQL JOIN

```sql
-- WRONG: DuckDB cannot reach MongoDB
SELECT r.business_ref, b.name
FROM review r
JOIN business b ON r.business_ref = b.business_id
```
DuckDB has no `business` table. This fails with `Catalog Error: Table with name business does not exist`.

---

## Null / Edge Cases

- `tip.user_id` is nullable — always add `WHERE user_id IS NOT NULL` before joining tip to user.
- Some business documents have `description = null` — always wrap with `{"$ifNull": ["$description", ""]}` before any `$split` or `$substr` operation.
- The integer suffix N can be any positive integer — do not assume sequential or bounded range.

---

## Injection Test

**Question:** An agent has DuckDB result `business_ref = "businessref_37"` and needs the business name. What are the exact steps?

**Expected answer:**
1. Convert: strip `"businessref_"` → `"37"` → prepend `"businessid_"` → `"businessid_37"`
2. MongoDB query: `[{"$collection": "business"}, {"$match": {"business_id": "businessid_37"}}, {"$project": {"name": 1}}]`
3. Returns the business name from the `name` field.
Direct string equality join would return zero rows because `"businessref_37" != "businessid_37"`.

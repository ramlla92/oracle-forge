# kb/domain/ — KB v2: Domain Knowledge

Dataset-specific schemas, join key contracts, field maps, query patterns, and anti-patterns. Injected as Context Layer 2 at session start.

## Documents

| File | Contents | Injection Test |
|------|----------|---------------|
| `yelp_schema.md` | Complete Yelp dataset schema from `schema_introspector.py` (confirmed 2026-04-11) | ✓ verified |
| `yelp_field_map.md` | Per-concept field map (rating, review_count, state, categories, WiFi, parking, credit cards) with anti-patterns | ✓ verified |
| `yelp_join_contract.md` | Canonical join key mapping `businessid_N ↔ businessref_N` with bidirectional join examples | ✓ verified |
| `yelp_query_skeletons.md` | Per-query logic for Q1–Q7 with expected intermediate outputs | ✓ verified |
| `yelp_antipatterns.md` | 15 entries (AP-01 through AP-15) — wrong query pattern → correct approach | ✓ verified |
| `join_keys_glossary.md` | Zero-padding rules, prefix conventions, bidirectional resolution across all datasets | ✓ verified |
| `schema_overview.md` | All 12 DAB datasets mapped to DB type (PostgreSQL / MongoDB / SQLite / DuckDB) | ✓ verified |
| `domain_knowledge.md` | Yelp domain terms: active business, high-rated, WiFi/parking attribute parsing | ✓ verified |
| `domain_terms.md` | Formal definitions of cross-dataset terms (churn, fiscal quarter, campaign) | ✓ verified |
| `unstructured_fields_inventory.md` | Free-text field extraction patterns (review.text, business.description, checkin.date) | ✓ verified |
| `github_repos_schema.md` | GITHUB_REPOS dataset schema (MongoDB collections: metadata, language, content, commits) | ✓ verified |
| `injection_tests.md` | Verified test query + expected answer for each document above | — |
| `CHANGELOG.md` | Version history for this KB layer | — |

## Cross-Database Entity Resolution

The critical join key mismatch in the Yelp dataset:
- MongoDB stores business IDs as `"businessid_42"` (prefix: `businessid_`)
- DuckDB stores business references as `"businessref_42"` (prefix: `businessref_`)
- Resolution: strip the prefix, reattach the correct one before joining

See `yelp_join_contract.md` for the bidirectional resolution logic and `join_keys_glossary.md` for the FORMAT_REGISTRY.

## How This Layer Is Used

`agent/context_manager.py` loads `domain_knowledge.md`, `join_keys_glossary.md`, and `schema_overview.md` by default. Dataset-specific files are loaded on demand based on `analyze_intent()` output. Token budget for this layer: 3,000 tokens.

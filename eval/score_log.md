# Score Log — Oracle Forge (Team Falcon)

Dataset: Yelp (MongoDB + DuckDB) | 7 queries | Metric: pass@1

---

## Score Progression

| Run | Date | Queries Passed | pass@1 | What Changed |
|-----|------|---------------|--------|--------------|
| Baseline | 2026-04-11 | 0/7 | 0% | First end-to-end run. All queries failing with code fence errors (SQL wrapped in ```sql```) and MongoDB pipeline sent as JSON string instead of array. |
| After Pattern A fix | 2026-04-11 | 1/7 | 14% | Added "Return raw SQL only, no markdown code fences" to `nl_to_sql()` prompt. One query now passing. |
| After Pattern B fix | 2026-04-14 | 4/7 | 57% | Added "Return pipeline as raw JSON array starting with `[`" to `nl_to_mongodb()` prompt. MongoDB pipelines now parse correctly. |
| After Pattern C fix | 2026-04-14 | 5/7 | 71% | Added "DuckDB only has review, user, tip tables — business data is in MongoDB" to AGENT.md. Agent stopped querying non-existent DuckDB business table. |
| After Pattern D fix | 2026-04-14 | 6/7 | 86% | Added "Never use strptime with fixed format on date fields; use `LIKE '%2018%'` for year filtering" to `nl_to_sql()` prompt. Mixed date format errors resolved. |
| Python post-processing | 2026-04-14 | 7/7 | 100% | Replaced unreliable MongoDB `$split`/`$addFields` for text extraction with Python regex in `agent_core.py`. State and category extraction now handled in Python after raw document retrieval. |

---

## Failure Pattern Reference

| Pattern | Error | Root Cause | Fix Location |
|---------|-------|-----------|--------------|
| A | `syntax error at or near "```"` | SQL wrapped in markdown code fence | `prompt_library.nl_to_sql()` |
| B | `pipeline must be a list, not <class 'str'>` | MongoDB pipeline serialized as string | `prompt_library.nl_to_mongodb()` |
| C | `Table with name business does not exist` | Agent queried DuckDB for MongoDB-only data | `agent/AGENT.md` Critical Rules |
| D | `Could not parse string "29 May 2013, 23:01"` | Fixed strptime format on mixed-format date field | `prompt_library.nl_to_sql()` |

All 32 failure instances documented in `kb/corrections/corrections_log.md`.

---

## How to Run

```bash
# Single dataset
python eval/run_benchmark.py --dataset yelp --trials 5

# Check score
python eval/score.py --results eval/run_logs/benchmark_yelp_<timestamp>.json
```

---

## All Runs

| Timestamp | Dataset | Passed | pass@1 |
|-----------|---------|--------|--------|
| 20260411_142058 | yelp | 0/7 | 0% |
| 20260411_142724 | yelp | 0/7 | 0% |
| 20260411_143810 | yelp | 1/7 | 14% |
| 20260411_144040 | yelp | 0/7 | 0% |
| 20260411_144221 | yelp | 0/7 | 0% |
| 20260413_142407 | yelp | 0/7 | 0% |
| 20260413_204424 | yelp | 0/7 | 0% |
| 20260413_205007 | yelp | 0/7 | 0% |
| 20260414_044753 | yelp | 1/7 | 14% |
| 20260414_121131 | yelp | 0/7 | 0% |
| 20260414_121741 | yelp | 0/7 | 0% |
| 20260414_122656 | yelp | 0/7 | 0% |
| 20260414_123006 | yelp | 1/7 | 14% |
| 20260414_123714 | yelp | 1/7 | 14% |
| 20260414_125716 | yelp | 1/7 | 14% |
| 20260414_153138 | yelp | 1/7 | 14% |
| 20260414_155651 | yelp | 4/7 | 57% |
| 20260414_173700 | yelp | 4/7 | 57% |
| 20260414_174530 | yelp | 4/7 | 57% |
| 20260414_175755 | yelp | 5/7 | 71% |
| 20260414_201357 | yelp | 6/7 | 86% |
| 20260414_201705 | yelp | 7/7 | 100% |
| 20260414_203704 | yelp | 6/7 | 86% |
| 20260414_204206 | yelp | 7/7 | 100% |
| 20260414_205611 | yelp | 6/7 | 86% |
| 20260414_205915 | yelp | 7/7 | 100% |
| 20260414_210933 | yelp | 7/7 | 100% |
| 20260415_063051 | yelp | 7/7 | 100% |
| 20260415_064930 | bookreview | 0/3 | 0% |
| 20260415_071452 | bookreview | 1/3 | 33% |
| 20260415_072246 | bookreview | 1/3 | 33% |
| 20260415_072948 | bookreview | 1/3 | 33% |
| 20260415_073956 | bookreview | 0/3 | 0% |
| 20260415_074335 | bookreview | 1/3 | 33% |
| 20260415_120543 | yelp | 4/7 | 57% | query-pass@1 | — |
| 20260415_120552 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_122804 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_123424 | yelp | 6/7 | 86% | query-pass@1 | — |
| 20260415_125206 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_125609 | yelp | 7/7 | 100% | query-pass@1 | — |
| 20260415_125802 | yelp | 7/7 | 100% | query-pass@3 | — |
| 20260415_150044 | yelp | 7/7 | 100% | query-pass@1 | — |
| 20260415_150704 | bookreview | 0/3 | 0% | query-pass@1 | — |
| 20260415_151751 | bookreview | 1/3 | 33% | query-pass@1 | — |
| 20260415_152410 | bookreview | 1/3 | 33% | query-pass@1 | — |
| 20260415_152534 | bookreview | 1/3 | 33% | query-pass@1 | — |
| 20260415_152758 | bookreview | 2/3 | 67% | query-pass@1 | — |
| 20260415_153224 | bookreview | 3/3 | 100% | query-pass@1 | — |
| 20260415_153418 | yelp | 3/7 | 43% | query-pass@1 | — |
| 20260415_153530 | yelp | 3/7 | 43% | query-pass@1 | — |
| 20260415_153918 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_154108 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_154208 | bookreview | 3/3 | 100% | query-pass@1 | — |
| 20260415_162300 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_162649 | yelp | 4/7 | 57% | query-pass@1 | — |
| 20260415_162955 | yelp | 5/7 | 71% | query-pass@1 | — |
| 20260415_163317 | yelp | 7/7 | 100% | query-pass@1 | — |
| 20260415_163356 | bookreview | 3/3 | 100% | query-pass@1 | — |
| 20260415_163833 | yelp | 6/7 | 86% | query-pass@1 | — |
| 20260415_163944 | bookreview | 3/3 | 100% | query-pass@1 | — |
